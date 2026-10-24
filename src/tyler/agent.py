"""Modo conversa: o Tyler como agente.

`tyler` sem subcomando abre um chat no terminal. O Claude entende o pedido em português,
chama as operações de `tyler.ops` como ferramentas (com o mesmo painel ao vivo da CLI)
e abre o resultado para o usuário ver. Nenhuma lógica de vídeo mora aqui: este módulo
só traduz conversa em chamadas às operações.
"""

import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

import anthropic
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.rule import Rule

from tyler import __version__, system
from tyler.ops import blur, cut, download, vertical, watermark
from tyler.report import PlainReporter, Reporter, RichReporter, _bytes
from tyler.video import default_output, probe

MODEL = "claude-opus-5-5"
MODEL_LABEL = "Opus 5.5"
CONTEXT_WINDOW = 1_000_000
# US$ por milhão de tokens: entrada, saída, leitura de cache, escrita de cache (5 min)
PRICES = {"claude-opus-5-5": (4.00, 20.00, 0.20, 5.00)}
BETAS = ["server-side-fallback-2026-07-01", "thinking-display-updates-2026-08-18"]
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
MAX_LISTED = 40
EXIT_WORDS = {"sair", "tchau", "exit", "quit"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
HISTORY_FILE = Path.home() / ".cache" / "tyler" / "historico"

SYSTEM = """Você é o Tyler, um editor de vídeo que roda no Mac do usuário e conversa em português.
O usuário pede edições em linguagem natural e você as executa com as ferramentas.

Pasta atual do usuário: {cwd}

Como trabalhar:
- Cada operação gera um arquivo novo ao lado do original; o original nunca é alterado.
- Quando o usuário encadeia pedidos ("agora coloca na vertical", "borra os rostos também"), aplique
  sobre o último arquivo gerado, não sobre o original, a menos que ele diga o contrário.
- Se ele citar um vídeo pelo nome ou de forma vaga ("o vídeo da praia", "o último que baixei"),
  use listar_videos para achar o arquivo. Se houver mais de um candidato plausível, pergunte qual.
- Para tempos relativos ("os últimos 10 segundos", "corta a metade"), use info_video para saber a duração.
- Quando ele quiser ver ou ouvir o resultado ("quero ver como ficou"), use abrir.
- As operações podem levar minutos; o usuário acompanha o progresso num painel. Depois de cada uma,
  diga em uma ou duas frases o que foi gerado e o caminho do arquivo.
- Se o pedido for ambíguo de um jeito que muda o resultado, pergunte antes de rodar. Senão, faça.
- Se pedirem algo que nenhuma ferramenta faz, diga isso e o que dá para fazer hoje.
- Responda curto e sem markdown pesado: a conversa acontece num terminal."""

TOOLS = [
    {
        "name": "listar_videos",
        "description": "Lista os vídeos e áudios de uma pasta, do mais recente para o mais antigo, "
                       "com tamanho e data. Use para achar o arquivo que o usuário mencionou.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pasta": {"type": "string", "description": "pasta a listar (padrão: a pasta atual); aceita ~"},
            },
        },
    },
    {
        "name": "info_video",
        "description": "Mostra resolução, codec, duração, fps e se o vídeo tem áudio.",
        "input_schema": {
            "type": "object",
            "properties": {"video": {"type": "string", "description": "caminho do vídeo"}},
            "required": ["video"],
        },
    },
    {
        "name": "cortar",
        "description": "Corta um trecho do vídeo entre dois tempos. O corte é exato (recodifica); "
                       "use copiar=true só se o usuário pedir rapidez e aceitar que o início pode "
                       "adiantar alguns segundos (quadro-chave anterior).",
        "input_schema": {
            "type": "object",
            "properties": {
                "video": {"type": "string", "description": "caminho do vídeo"},
                "inicio": {"type": "string", "description": "segundos (90), MM:SS (1:30) ou HH:MM:SS (1:02:03)"},
                "fim": {"type": "string", "description": "mesmo formato; omita para ir até o final"},
                "copiar": {"type": "boolean", "description": "não recodifica (padrão: false)"},
            },
            "required": ["video", "inicio"],
        },
    },
    {
        "name": "vertical",
        "description": "Converte um vídeo horizontal para vertical 9:16 (Reels, TikTok, Shorts).",
        "input_schema": {
            "type": "object",
            "properties": {
                "video": {"type": "string", "description": "caminho do vídeo"},
                "modo": {"type": "string", "enum": list(vertical.MODES),
                         "description": "auto: segue os rostos (padrão) | center: corte fixo no centro | "
                                        "fit: vídeo inteiro com fundo desfocado"},
            },
            "required": ["video"],
        },
    },
    {
        "name": "borrar",
        "description": "Anonimiza o vídeo borrando rostos e/ou placas de veículos detectados automaticamente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "video": {"type": "string", "description": "caminho do vídeo"},
                "alvos": {"type": "string", "enum": list(blur.TARGETS),
                          "description": "all: rostos e placas (padrão) | faces: só rostos | plates: só placas"},
                "estilo": {"type": "string", "enum": list(blur.STYLES),
                           "description": "blur: desfoque (padrão) | pixel: mosaico | black: tarja preta"},
            },
            "required": ["video"],
        },
    },
    {
        "name": "marca_dagua",
        "description": "Coloca uma imagem (logo, selo) sobre o vídeo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "video": {"type": "string", "description": "caminho do vídeo"},
                "imagem": {"type": "string", "description": "caminho da imagem (PNG com transparência, JPG ou WebP)"},
                "posicao": {"type": "string", "enum": list(watermark.POSITIONS),
                            "description": "padrão: bottom-right"},
                "tamanho": {"type": "number", "description": "largura em % do lado menor do vídeo (padrão: 20)"},
                "opacidade": {"type": "number", "description": "de 0.1 a 1 (padrão: 1)"},
            },
            "required": ["video", "imagem"],
        },
    },
    {
        "name": "baixar",
        "description": "Baixa um vídeo (mp4) ou só o áudio do YouTube, Instagram, TikTok, Vimeo e outros sites "
                       "para a pasta atual. Só para vídeos do usuário, com licença livre ou com autorização.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "link completo, com https://"},
                "so_audio": {"type": "boolean", "description": "baixa só o áudio (padrão: false)"},
                "formato_audio": {"type": "string", "enum": list(download.AUDIO_FORMATS),
                                  "description": "m4a: original, sem recodificar (padrão) | mp3"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "abrir",
        "description": "Abre um vídeo, áudio ou imagem no player padrão do Mac para o usuário ver.",
        "input_schema": {
            "type": "object",
            "properties": {"caminho": {"type": "string", "description": "arquivo a abrir"}},
            "required": ["caminho"],
        },
    },
]


class ToolError(Exception):
    """Falha de ferramenta com mensagem para o modelo (vira tool_result com is_error)."""


class Cancelled(ToolError):
    """O usuário apertou Ctrl+C durante uma operação."""


ReporterFactory = Callable[[], Reporter]


def _default_reporter() -> Reporter:
    return RichReporter() if sys.stderr.isatty() else PlainReporter()


def run_tool(name: str, args: dict, new_reporter: ReporterFactory = _default_reporter) -> str:
    """Executa a ferramenta `name` e devolve o texto do resultado; falhas viram ToolError."""
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ToolError(f"Ferramenta desconhecida: {name}")
    try:
        return handler(args, new_reporter)
    except KeyError as e:
        raise ToolError(f"Falta o parâmetro {e}")
    except (ValueError, download.DownloadFailed, system.MissingTool, subprocess.CalledProcessError, OSError) as e:
        # InvalidRange etc. são ValueError; OSError cobre arquivos sem permissão e afins
        raise ToolError(str(e))


def _existing(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.exists():
        raise ToolError(f"Arquivo não encontrado: {p}")
    return p.resolve()


def _run_op(new_reporter: ReporterFactory, partial: Path | None, op: Callable[[Reporter], Path]) -> str:
    """Roda a operação com o painel ao vivo e resume o resultado (caminho + estatísticas) para o modelo."""
    started = time.monotonic()
    try:
        with new_reporter() as reporter:
            output = op(reporter)
            reporter.done(output, time.monotonic() - started)
    except BaseException as e:
        if partial:
            partial.unlink(missing_ok=True)  # não deixa vídeo pela metade para trás
        if isinstance(e, KeyboardInterrupt):
            raise Cancelled("Cancelado pelo usuário (Ctrl+C). Nenhum arquivo foi gerado.") from None
        raise
    lines = [f"Arquivo gerado: {output}"]
    lines += [f"{label}: {value}" for label, value in reporter.stats.items()]
    try:
        lines.append(f"Formato: {probe(output).describe()}")
    except (ValueError, subprocess.CalledProcessError):
        pass  # só áudio
    return "\n".join(lines)


def _output_for(video: Path, operation: str) -> Path:
    output = default_output(video, operation)
    if output.resolve() == video:
        raise ToolError("A saída não pode ser o próprio vídeo de entrada.")
    return output


def _listar_videos(args: dict, new_reporter: ReporterFactory) -> str:
    folder = Path(args.get("pasta") or ".").expanduser().resolve()
    if not folder.is_dir():
        raise ToolError(f"Pasta não encontrada: {folder}")
    media = VIDEO_EXTENSIONS | {f".{fmt}" for fmt in download.AUDIO_FORMATS}
    files = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in media),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return f"Nenhum vídeo ou áudio em {folder}"
    lines = [f"{folder} ({len(files)} arquivos):"]
    for p in files[:MAX_LISTED]:
        st = p.stat()
        lines.append(f"- {p.name} · {_bytes(st.st_size)} · {datetime.fromtimestamp(st.st_mtime):%d/%m %H:%M}")
    if len(files) > MAX_LISTED:
        lines.append(f"... e mais {len(files) - MAX_LISTED}")
    return "\n".join(lines)


def _info_video(args: dict, new_reporter: ReporterFactory) -> str:
    video = _existing(args["video"])
    info = probe(video)
    return f"{video}: {info.describe()} · {'com' if info.has_audio else 'sem'} áudio · {info.duration:.2f}s"


def _cortar(args: dict, new_reporter: ReporterFactory) -> str:
    video = _existing(args["video"])
    start = cut.parse_time(args["inicio"])
    end = cut.parse_time(args["fim"]) if args.get("fim") else None
    output = _output_for(video, "cut")
    return _run_op(new_reporter, output,
                   lambda r: cut.run(video, output, start, end, bool(args.get("copiar")), r))


def _vertical(args: dict, new_reporter: ReporterFactory) -> str:
    video = _existing(args["video"])
    output = _output_for(video, "vertical")
    return _run_op(new_reporter, output,
                   lambda r: vertical.run(video, output, args.get("modo") or "auto", reporter=r))


def _borrar(args: dict, new_reporter: ReporterFactory) -> str:
    video = _existing(args["video"])
    output = _output_for(video, "blur")
    return _run_op(new_reporter, output,
                   lambda r: blur.run(video, output, args.get("alvos") or "all", args.get("estilo") or "blur", r))


def _marca_dagua(args: dict, new_reporter: ReporterFactory) -> str:
    video, image = _existing(args["video"]), _existing(args["imagem"])
    output = _output_for(video, "watermark")
    return _run_op(new_reporter, output, lambda r: watermark.run(
        video, image, output, args.get("posicao") or "bottom-right", args.get("tamanho") or 20,
        args.get("opacidade") or 1.0, reporter=r))


def _baixar(args: dict, new_reporter: ReporterFactory) -> str:
    url = args["url"]
    if not url.startswith(("http://", "https://")):
        raise ToolError(f"Link inválido: {url} (use o endereço completo, com https://)")
    # o nome só é conhecido depois do download, que limpa os próprios temporários
    return _run_op(new_reporter, None, lambda r: download.run(
        url, None, bool(args.get("so_audio")), args.get("formato_audio") or "m4a", r))


def _abrir(args: dict, new_reporter: ReporterFactory) -> str:
    path = _existing(args["caminho"])
    subprocess.run(["open", str(path)], check=True)
    return f"Aberto no player: {path}"


_HANDLERS = {
    "listar_videos": _listar_videos,
    "info_video": _info_video,
    "cortar": _cortar,
    "vertical": _vertical,
    "borrar": _borrar,
    "marca_dagua": _marca_dagua,
    "baixar": _baixar,
    "abrir": _abrir,
}


@dataclass
class Usage:
    """Tokens e custo acumulados na conversa (o que a API cobrou, chamada a chamada)."""

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost: float = 0.0
    context: int = 0  # tamanho da conversa na última chamada
    estimated: bool = False  # alguma resposta veio de outro modelo (reserva), com preço estimado

    def add(self, model: str, usage) -> None:
        cache_read = usage.cache_read_input_tokens or 0
        cache_write = usage.cache_creation_input_tokens or 0
        price = PRICES.get(model)
        if price is None:
            price, self.estimated = PRICES[MODEL], True
        self.input += usage.input_tokens
        self.output += usage.output_tokens
        self.cache_read += cache_read
        self.cache_write += cache_write
        self.cost += (usage.input_tokens * price[0] + usage.output_tokens * price[1]
                      + cache_read * price[2] + cache_write * price[3]) / 1_000_000
        self.context = usage.input_tokens + cache_read + cache_write + usage.output_tokens

    @property
    def sent(self) -> int:
        return self.input + self.cache_read + self.cache_write

    def toolbar(self) -> str:
        cache = f"{self.cache_read * 100 // self.sent}%" if self.sent else "-"
        return (f" {MODEL_LABEL} · {Path.cwd().name}/  │  contexto {_tokens(self.context)} de "
                f"{_tokens(CONTEXT_WINDOW)} ({self.context * 100 // CONTEXT_WINDOW}%)  │  "
                f"↑ {_tokens(self.sent)}  ↓ {_tokens(self.output)}  │  cache {cache}  │  "
                f"{'≈ ' if self.estimated else ''}{_money(self.cost)} ")

    def since(self, before: "Usage") -> str:
        return (f"↑ {_tokens(self.sent - before.sent)}  ↓ {_tokens(self.output - before.output)}  ·  "
                f"{_money(self.cost - before.cost)}")


def _tokens(n: int) -> str:
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f} mil".replace(".", ",").replace(",0 ", " ")
    return f"{n / 1_000_000:.1f} mi".replace(".", ",").replace(",0 ", " ")


def _money(value: float) -> str:
    return f"US$ {value:.3f}".replace(".", ",") if value < 1 else f"US$ {value:.2f}".replace(".", ",")


class Session:
    """Uma conversa: guarda o histórico (só acrescenta, nunca reescreve) e roda cada pedido até o fim."""

    def __init__(self, client: anthropic.Anthropic, console: Console):
        self.client, self.console = client, console
        self.system = SYSTEM.format(cwd=Path.cwd())
        self.history: list[dict] = []
        self.usage = Usage()

    def ask(self, text: str) -> None:
        checkpoint, before = len(self.history), replace(self.usage)
        self.history.append({"role": "user", "content": text})
        try:
            self._loop()
        except KeyboardInterrupt:
            # resposta interrompida no meio: descarta o pedido inteiro, como se não tivesse sido feito
            del self.history[checkpoint:]
            self.console.print("\n[dim]Interrompido.[/]")
        except Exception:
            del self.history[checkpoint:]  # o histórico nunca fica com uma ferramenta sem resultado
            raise
        finally:
            if self.usage.cost > before.cost:
                self.console.print(f"[dim]{self.usage.since(before)}[/]")

    def _loop(self) -> None:
        while True:
            message = self._stream()
            self.history.append({"role": "assistant", "content": message.content})
            if message.stop_reason == "refusal":
                raise ToolError("Não posso ajudar com esse pedido.")
            tool_uses = [b for b in message.content if b.type == "tool_use"]
            if message.stop_reason == "max_tokens" and tool_uses:
                raise ToolError("A resposta foi cortada no meio de uma ferramenta.")
            if not tool_uses:
                return
            results, cancelled = [], False
            for block in tool_uses:
                if cancelled:  # depois de um Ctrl+C, não roda o resto
                    results.append(_result(block.id, "Não executado: o usuário cancelou.", error=True))
                    continue
                try:
                    results.append(_result(block.id, run_tool(block.name, block.input)))
                except ToolError as e:
                    results.append(_result(block.id, str(e), error=True))
                    cancelled = isinstance(e, Cancelled)
            # todos os resultados numa única mensagem, como a API espera
            self.history.append({"role": "user", "content": results})
            if cancelled:
                self.console.print("[dim]Cancelado.[/]")
                return

    def _stream(self):
        in_text = in_note = False
        with self.client.beta.messages.stream(
            model=MODEL,
            max_tokens=64000,
            system=self.system,
            tools=TOOLS,
            messages=self.history,
            thinking={"type": "adaptive", "display": "updates"},  # notas curtas de progresso entre ferramentas
            output_config={"effort": "medium"},
            cache_control={"type": "ephemeral"},
            betas=BETAS,
            fallbacks="default",
        ) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    if event.content_block.type == "text" and not in_text:
                        self.console.print("[bold magenta]tyler›[/] ", end="")
                    in_text = event.content_block.type == "text"
                    in_note = event.content_block.type == "thinking"
                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        self.console.print(event.delta.text, end="", markup=False, highlight=False)
                    elif event.delta.type == "thinking_delta" and event.delta.thinking:
                        self.console.print(event.delta.thinking, end="", style="dim italic",
                                           markup=False, highlight=False)
                elif event.type == "content_block_stop" and (in_text or in_note):
                    self.console.print()
                    in_text = in_note = False
            message = stream.get_final_message()
        self.usage.add(message.model, message.usage)
        return message


def _result(tool_use_id: str, content: str, error: bool = False) -> dict:
    result = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if error:
        result["is_error"] = True
    return result


class _FileCompleter(Completer):
    """Tab completa nomes de vídeos, áudios e imagens da pasta atual."""

    EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS | {f".{fmt}" for fmt in download.AUDIO_FORMATS}

    def get_completions(self, document, complete_event):
        word = document.get_word_before_cursor(WORD=True)
        for p in sorted(Path.cwd().iterdir()):
            if p.suffix.lower() in self.EXTENSIONS and p.name.lower().startswith(word.lower()):
                yield Completion(p.name, start_position=-len(word))


def _input_area(usage: Usage) -> Callable[[], str]:
    """Área de digitação: edição completa, histórico (↑/↓) entre sessões, Tab completa arquivos
    e uma barra no rodapé com tokens e custo. Fora de um terminal, cai no input() simples."""
    if not sys.stdin.isatty():
        return lambda: input("você› ")
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    prompt = PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        completer=_FileCompleter(),
        complete_while_typing=False,
        bottom_toolbar=lambda: [("class:bar", usage.toolbar())],
        placeholder=[("class:placeholder", "peça uma edição…  (Tab completa arquivos · Ctrl+D sai)")],
        style=Style.from_dict({
            "prompt": "bold ansicyan",
            "placeholder": "ansibrightblack italic",
            "bottom-toolbar": "noreverse",
            "bar": "bg:ansimagenta ansiwhite",
        }),
    )
    return lambda: prompt.prompt([("class:prompt", "você› ")])


def main() -> None:
    console = Console()
    session = Session(anthropic.Anthropic(), console)
    read = _input_area(session.usage)
    console.print(f"[bold magenta]Tyler[/] {__version__} · editor de vídeo por conversa  "
                  f"[dim]({Path.cwd()} · Ctrl+C interrompe · 'sair' ou Ctrl+D encerra)[/]")
    console.print("[dim]Ex.: “pega o vira.mp4, corta do 0:10 ao 0:40 e deixa vertical”[/]")
    while True:
        console.print(Rule(style="dim"))
        try:
            text = read().strip()
        except KeyboardInterrupt:  # Ctrl+C na área de digitação só limpa a linha
            continue
        except EOFError:
            console.print(f"[dim]Até mais. {session.usage.toolbar().strip()}[/]")
            return
        if not text:
            continue
        if text.lower() in EXIT_WORDS:
            console.print(f"[dim]Até mais. {session.usage.toolbar().strip()}[/]")
            return
        try:
            session.ask(text)
        except ToolError as e:
            console.print(f"[red]{e}[/]")
        except anthropic.AuthenticationError:
            sys.exit("Chave da API inválida: confira ANTHROPIC_API_KEY.")
        except TypeError as e:
            if "authentication" not in str(e):  # o SDK só procura credenciais na primeira chamada
                raise
            sys.exit("Falta a chave da API: defina ANTHROPIC_API_KEY (crie em https://platform.claude.com).")
        except anthropic.RateLimitError:
            console.print("[yellow]Limite de uso da API atingido; espere um pouco e tente de novo.[/]")
        except anthropic.APIStatusError as e:
            console.print(f"[red]Erro da API ({e.status_code}): {e.message}[/]")
        except anthropic.APIConnectionError:
            console.print("[red]Sem conexão com a API. Confira a internet e tente de novo.[/]")
