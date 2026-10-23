"""Baixa vídeo ou só o áudio do YouTube (e de outros sites suportados pelo yt-dlp).

O vídeo sai em mp4 (H.264 + AAC quando o site oferece), pronto para as outras operações.
O áudio sai em m4a sem recodificar, ou em mp3 se pedido. O yt-dlp usa o ffmpeg do sistema
para juntar as faixas de vídeo e áudio, que o YouTube entrega separadas.
"""

import os
import re
import time
from glob import escape
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from tyler.report import PlainReporter, Reporter, _bytes, shell_command

AUDIO_FORMATS = ("m4a", "mp3")

VIDEO_FORMAT = "bv*[vcodec^=avc1]+ba[ext=m4a]/bv*+ba/b"  # prefere H.264 + AAC; senão, o melhor disponível
AUDIO_FORMAT = "ba[ext=m4a]/ba"
MP3_QUALITY = "192"  # kbps

VIDEO_STEP = "Baixando vídeo"
AUDIO_STEP = "Baixando áudio"
MERGE_STEP = "Juntando faixas"
TITLE_TEMPLATE = "%(title)s.%(ext)s"


class DownloadFailed(RuntimeError):
    """Erro esperado (vídeo indisponível, privado, link de playlist...), com mensagem para o usuário."""


def run(url: str, output: Path | str | None = None, only_audio: bool = False, audio_format: str = "m4a",
        reporter: Reporter | None = None) -> Path:
    """Baixa `url` e devolve o caminho do arquivo gerado.

    `output` pode ser uma pasta (existente ou terminada em "/"; o arquivo recebe o título do vídeo)
    ou um arquivo (a extensão é trocada pela do formato baixado). Sem `output`, salva na pasta atual com o título do vídeo.
    Arquivos existentes nunca são sobrescritos.
    """
    if audio_format not in AUDIO_FORMATS:
        raise ValueError(f"Formato de áudio inválido: {audio_format}. Use um de: {', '.join(AUDIO_FORMATS)}")
    reporter = reporter or PlainReporter()
    progress = _Progress(reporter, audio_format)
    opts = options(output, only_audio, audio_format)
    cmd = shell_command(command_line(url, opts))  # antes do YoutubeDL, que altera `opts`
    opts |= {"progress_hooks": [progress.on_download], "postprocessor_hooks": [progress.on_postprocess]}

    started = time.time()
    with YoutubeDL(opts) as ydl:
        reporter.command(f"yt-dlp lendo {url}")
        info = _call(ydl.extract_info, url, download=False)
        if info.get("_type") == "playlist":
            raise DownloadFailed("Esse link é de uma playlist; passe o link de um vídeo só.")
        reporter.header(f"download · {info.get('title', url)}", _describe(info, only_audio))
        reporter.plan(_plan(info, only_audio, audio_format))
        reporter.command(cmd)
        try:
            info = _call(ydl.process_ie_result, info, download=True)
        except BaseException:
            progress.cleanup()  # não deixa .part e faixas soltas para trás
            raise
        progress.finish()

    path = Path(info["requested_downloads"][0]["filepath"]).resolve()
    if not progress.downloaded and path.stat().st_mtime < started:
        reporter.stats["arquivo"] = "já existia, nada foi baixado"
    return path


def options(output: Path | str | None, only_audio: bool, audio_format: str) -> dict:
    """Opções do YoutubeDL para o pedido (sem os hooks de progresso)."""
    opts = {
        "outtmpl": _template(output),
        "noplaylist": True,
        "extract_flat": "in_playlist",  # link de playlist: não resolve cada vídeo só para recusar depois
        "overwrites": False,
        "windowsfilenames": True,  # tira caracteres que dão problema em nomes de arquivo
        "quiet": True,
        "noprogress": True,
        "logger": _Silent(),
    }
    if only_audio:
        pp = {"key": "FFmpegExtractAudio", "preferredcodec": audio_format}
        if audio_format == "mp3":
            pp["preferredquality"] = MP3_QUALITY
        opts |= {"format": AUDIO_FORMAT, "postprocessors": [pp]}
    else:
        opts |= {
            "format": VIDEO_FORMAT,
            "merge_output_format": "mp4",
            "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        }
    return opts


def command_line(url: str, opts: dict) -> list[str]:
    """Comando `yt-dlp` equivalente, para exibir no painel."""
    cmd = ["yt-dlp", "-f", opts["format"]]
    if "merge_output_format" in opts:
        cmd += ["--merge-output-format", opts["merge_output_format"]]
    for pp in opts["postprocessors"]:
        if pp["key"] == "FFmpegExtractAudio":
            cmd += ["-x", "--audio-format", pp["preferredcodec"]]
    return [*cmd, "-o", opts["outtmpl"], url]


def _template(output: Path | str | None) -> str:
    if output is None:
        return TITLE_TEMPLATE
    path = Path(output).expanduser()  # Path() perde a "/" final, por isso olha o texto original
    if path.is_dir() or str(output).endswith(os.sep):
        return str(path / TITLE_TEMPLATE)
    return str(path.with_suffix("")) + ".%(ext)s"


def _describe(info: dict, only_audio: bool) -> str:
    parts = [info.get("uploader") or info.get("channel") or info.get("extractor_key", "")]
    if info.get("duration"):
        m, s = divmod(int(info["duration"]), 60)
        parts.append(f"{m}:{s:02d}")
    if only_audio:
        abr = info.get("abr")
        parts.append(f"áudio {info.get('acodec', '?')}" + (f" {abr:.0f}k" if abr else ""))
    elif info.get("height"):
        parts.append(f"{info.get('width', '?')}x{info['height']}")
    return " · ".join(p for p in parts if p)


def _plan(info: dict, only_audio: bool, audio_format: str) -> list[str]:
    if only_audio:
        return [AUDIO_STEP, _extract_step(audio_format)]
    if info.get("requested_formats"):  # vídeo e áudio separados: baixa os dois e junta
        return [VIDEO_STEP, AUDIO_STEP, MERGE_STEP]
    return [VIDEO_STEP]


def _extract_step(audio_format: str) -> str:
    return "Convertendo para mp3" if audio_format == "mp3" else "Extraindo áudio"


def _call(fn, *args, **kwargs):
    """Chama o yt-dlp trocando os erros dele por uma mensagem em português."""
    try:
        return fn(*args, **kwargs)
    except DownloadError as e:
        msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).removeprefix("ERROR: ")
        raise DownloadFailed(f"Não foi possível baixar: {msg}") from None


class _Silent:
    """Logger do yt-dlp que não imprime nada: o andamento vai para o Reporter e os erros viram exceção."""

    def debug(self, msg: str) -> None:
        pass

    info = warning = error = debug


class _Progress:
    """Converte os hooks do yt-dlp em etapas do Reporter."""

    def __init__(self, reporter: Reporter, audio_format: str):
        self.reporter = reporter
        self.audio_format = audio_format
        self.downloaded = False
        self.partial: set[Path] = set()  # arquivos temporários, apagados se o download falhar
        self._name: str | None = None
        self._cm = self._step = None

    def on_download(self, d: dict) -> None:
        fmt = d.get("info_dict", {})
        name = VIDEO_STEP if fmt.get("vcodec") not in (None, "none") else AUDIO_STEP
        if d["status"] == "downloading":  # só o que está sendo baixado agora; nunca um arquivo que já existia
            self.downloaded = True
            self.partial |= {Path(d[k]) for k in ("tmpfilename", "filename") if d.get(k)}
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            step = self._start(name, total, "B")
            step.total = max(int(total), 1)  # a estimativa do tamanho muda durante o download
            step.update(d.get("downloaded_bytes", 0), stats={_size_label(name): _bytes(total)})
        elif d["status"] == "finished" and self._name == name:
            self._step.update(self._step.total)
            self.finish()

    def on_postprocess(self, d: dict) -> None:
        name = {
            "Merger": MERGE_STEP,
            "ExtractAudio": _extract_step(self.audio_format),
        }.get(d.get("postprocessor"))
        if name is None:
            return
        if d["status"] == "started":
            self.reporter.command(f"ffmpeg: {name.lower()}")
            self._start(name, 1, "")
        elif d["status"] == "finished" and self._name == name:
            self.finish()

    def _start(self, name: str, total: float, unit: str):
        if self._name != name:
            self.finish()
            self._name = name
            self._cm = self.reporter.step(name, int(total), unit)
            self._step = self._cm.__enter__()
        return self._step

    def finish(self) -> None:
        if self._cm is not None:
            self._cm.__exit__(None, None, None)
        self._name = self._cm = self._step = None

    def cleanup(self) -> None:
        for path in self.partial:
            for leftover in (path, *path.parent.glob(f"{escape(path.name)}.*"),
                             *path.parent.glob(f"{escape(path.name)}-Frag*")):
                leftover.unlink(missing_ok=True)


def _size_label(step_name: str) -> str:
    return "vídeo" if step_name == VIDEO_STEP else "áudio"
