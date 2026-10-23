"""Exibição do andamento das operações.

As operações não imprimem nada direto: elas avisam um Reporter sobre etapas, progresso,
estatísticas e o quadro que estão vendo. Cada interface exibe isso do seu jeito:
- PlainReporter: linhas simples (Claude/skills, pipes, `--plain`)
- RichReporter: painel ao vivo no terminal, com miniatura do quadro atual
"""

import shlex
import sys
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

import cv2
import numpy as np
from rich.color import Color
from rich.console import Console, Group
from rich.live import Live
from rich.progress_bar import ProgressBar
from rich.rule import Rule
from rich.style import Style
from rich.table import Table
from rich.text import Text

from tyler import system
from tyler.system import Monitor

Preview = Callable[[], np.ndarray]

FACE_MODEL = "YuNet (rostos)"

GREEN = (80, 220, 80)  # BGR
YELLOW = (0, 220, 255)


class Step:
    """Uma etapa em andamento. `preview` é uma função: só é chamada quando a tela vai ser redesenhada.

    `unit` é o que está sendo contado: "q" (quadros), "B" (bytes, mostra a velocidade de download)
    ou "" (etapa sem progresso mensurável, sem velocidade nem tempo restante).
    """

    def __init__(self, name: str, total: int):
        self.name, self.total = name, max(total, 1)
        self.unit = "q"
        self.done = 0
        self.stats: dict[str, object] = {}
        self.started = time.monotonic()
        self.elapsed: float | None = None

    def update(self, done: int, stats: dict | None = None, preview: Preview | None = None) -> None:
        self.done = done
        if stats:
            self.stats.update(stats)


class Reporter:
    """Base: guarda as estatísticas para o resumo final; subclasses decidem como exibir."""

    def __init__(self):
        self.stats: dict[str, object] = {}
        self.models: dict[str, list[float]] = {}  # nome -> [inferências, segundos totais]
        self.active_model: str | None = None
        self.current_command: str | None = None

    def __enter__(self) -> "Reporter":
        return self

    def __exit__(self, *exc) -> None:
        pass

    def header(self, title: str, details: str) -> None:
        pass

    def plan(self, steps: list[str]) -> None:
        pass

    @contextmanager
    def step(self, name: str, total: int, unit: str = "q"):
        self.active_model = None
        step = self._new_step(name, total)
        step.unit = unit
        try:
            yield step
        finally:
            step.elapsed = time.monotonic() - step.started
            self.stats.update(step.stats)
        self._step_finished(step)

    def command(self, text: str) -> None:
        """O que está rodando agora (comando externo ou descrição)."""
        self.current_command = text

    @contextmanager
    def inference(self, model: str):
        """Cronometra uma chamada de modelo de IA."""
        self.active_model = model
        started = time.perf_counter()
        try:
            yield
        finally:
            usage = self.models.setdefault(model, [0, 0.0])
            usage[0] += 1
            usage[1] += time.perf_counter() - started

    def done(self, output: Path, elapsed: float) -> None:
        pass

    def _new_step(self, name: str, total: int) -> Step:
        return Step(name, total)

    def _step_finished(self, step: Step) -> None:
        pass


class _PlainStep(Step):
    def __init__(self, name: str, total: int):
        super().__init__(name, total)
        self._last = -1

    def update(self, done: int, stats: dict | None = None, preview: Preview | None = None) -> None:
        super().update(done, stats)
        pct = min(99, done * 100 // self.total)
        if pct // 25 > self._last // 25:
            print(f"{self.name}: {pct}%", file=sys.stderr)
        self._last = pct


class PlainReporter(Reporter):
    """Linhas simples a cada 25%, para quando a saída não é um terminal."""

    def header(self, title: str, details: str) -> None:
        eco = f" · modo eco ({system.THREADS} threads)" if system.ECO else ""
        print(f"Tyler · {title} ({details}){eco}", file=sys.stderr)

    def _new_step(self, name: str, total: int) -> Step:
        return _PlainStep(name, total)

    def _step_finished(self, step: Step) -> None:
        print(f"{step.name}: 100% ({_duration(step.elapsed)})", file=sys.stderr)

    def done(self, output: Path, elapsed: float) -> None:
        for label, value in self.stats.items():
            print(f"{label}: {value}", file=sys.stderr)
        for line in _model_lines(self.models):
            print(line, file=sys.stderr)
        print(f"Pronto em {_duration(elapsed)}: {output} ({_size(output)})", file=sys.stderr)


class _LiveStep(Step):
    def __init__(self, name: str, total: int, reporter: "RichReporter"):
        super().__init__(name, total)
        self._reporter = reporter

    def update(self, done: int, stats: dict | None = None, preview: Preview | None = None) -> None:
        super().update(done, stats)
        self._reporter._maybe_preview(preview)


class RichReporter(Reporter):
    """Painel ao vivo: etapas, barra, ETA, estatísticas e miniatura do quadro atual."""

    PREVIEW_INTERVAL = 0.25  # segundos entre miniaturas
    PREVIEW_MAX_COLS = 72
    PREVIEW_MAX_ROWS = 22

    def __init__(self, show_preview: bool = True, show_system: bool = True):
        super().__init__()
        self.console = Console(stderr=True)
        self.show_preview = show_preview
        self.monitor = Monitor() if show_system else None
        self._title = self._details = ""
        self._pending: list[str] = []
        self._steps: list[Step] = []
        self._preview: Text | None = None
        self._preview_at = 0.0
        self._live = Live(console=self.console, get_renderable=self._render, refresh_per_second=8, transient=True)

    def __enter__(self) -> "RichReporter":
        self._live.start()
        return self

    def __exit__(self, *exc) -> None:
        self._live.stop()

    def header(self, title: str, details: str) -> None:
        self._title, self._details = title, details

    def plan(self, steps: list[str]) -> None:
        self._pending = list(steps)

    def _new_step(self, name: str, total: int) -> Step:
        if name in self._pending:
            self._pending.remove(name)
        self._preview = None
        step = _LiveStep(name, total, self)
        self._steps.append(step)
        return step

    def _maybe_preview(self, preview: Preview | None) -> None:
        if preview is None or not self.show_preview:
            return
        now = time.monotonic()
        if now - self._preview_at < self.PREVIEW_INTERVAL:
            return
        self._preview_at = now
        cols = min(self.PREVIEW_MAX_COLS, self.console.width - 4)
        self._preview = thumbnail(preview(), cols, self.PREVIEW_MAX_ROWS)

    def done(self, output: Path, elapsed: float) -> None:
        self._live.stop()
        self.console.print(self._render_steps(final=True))
        if self.stats:
            self.console.print("  " + _format_stats(self.stats), style="dim")
        for line in _model_lines(self.models):
            self.console.print("  " + line, style="dim")
        self.console.print(
            f"[bold green]✔ Pronto em {_duration(elapsed)}[/] → [bold]{output}[/] [dim]({_size(output)})[/]"
        )

    def _render(self):
        parts = [self._render_steps(final=False)]
        current = self._steps[-1] if self._steps and self._steps[-1].elapsed is None else None
        stats = {**self.stats, **(current.stats if current else {})}
        if stats:
            parts.append(Text("  " + _format_stats(stats), style="cyan"))
        if self._preview is not None:
            parts += [Text(""), self._preview]
        if self.monitor is not None:
            parts.append(self._render_system())
        return Group(*parts)

    def _render_system(self):
        sample = self.monitor.sample()
        heat_style = {"normal": "green", "morno": "yellow", "quente": "bold red", "crítico": "bold red"}
        # psutil soma 100% por núcleo (como o `top`); aqui vira % do Mac inteiro
        mac_pct = min(100.0, sample.cpu / sample.cores)
        cpu_color = "green" if mac_pct <= 50 else "yellow" if mac_pct <= 80 else "red"
        details = Text.assemble(
            f"{mac_pct:3.0f}% do Mac ", (f"({sample.cpu / 100:.1f} de {sample.cores} núcleos)", "dim"),
            " · ", ("RAM ", "bold"), _bytes(sample.ram),
        )
        if sample.thermal:
            details.append_text(Text.assemble(" · ", ("Mac ", "bold"), (sample.thermal, heat_style[sample.thermal])))
        if system.ECO:
            details.append(f" · modo eco: núcleos de eficiência, {system.THREADS} threads", style="green")
        sys_line = Table.grid(padding=(0, 1))
        sys_line.add_row(
            Text(" CPU", style="bold"),
            ProgressBar(total=100, completed=mac_pct, width=10, complete_style=cpu_color, finished_style=cpu_color),
            details,
        )

        ai_line = Text(" IA  ", style="bold")
        if not self.models:
            ai_line.append("nenhum modelo em uso", style="dim")
        for i, (name, (count, total)) in enumerate(self.models.items()):
            if i:
                ai_line.append(" · ")
            style = "bold cyan" if name == self.active_model else "cyan"
            ai_line.append(name, style=style)
            ai_line.append(f" {int(count)} inferências, {total / count * 1000:.1f} ms cada", style="dim")

        cmd_line = Text.assemble((" ⚙   ", "bold"), (self.current_command or "-", "dim"))
        cmd_line.no_wrap, cmd_line.overflow = True, "ellipsis"
        return Group(Rule(style="dim"), sys_line, ai_line, cmd_line)

    def _render_steps(self, final: bool):
        title = Text.assemble(("Tyler", "bold magenta"), " · ", (self._title, "bold"), "  ", (self._details, "dim"))
        table = Table.grid(padding=(0, 1))
        for step in self._steps:
            if step.elapsed is not None:
                table.add_row(Text("✔", style="green"), step.name, Text(_duration(step.elapsed), style="dim"))
            else:
                table.add_row(Text("▶", style="yellow"), Text(step.name, style="bold"), _progress_line(step))
        if not final:
            for name in self._pending:
                table.add_row(Text("·", style="dim"), Text(name, style="dim"), "")
        return Group(title, Text(""), table, Text(""))


def _progress_line(step: Step) -> Table:
    elapsed = time.monotonic() - step.started
    done = min(step.done, step.total)
    rate = done / elapsed if elapsed > 0 else 0
    eta = (step.total - done) / rate if rate > 0 and step.unit else None
    if step.unit == "B":
        speed = f"{_bytes(rate)}/s"
    else:
        speed = f"{rate:5.1f} {step.unit}/s" if step.unit else ""
    line = Table.grid(padding=(0, 1))
    line.add_row(
        ProgressBar(total=step.total, completed=done, width=30),
        f"{done * 100 // step.total:3d}%",
        Text(speed, style="dim"),
        Text(f"faltam {_duration(eta)}" if eta is not None else "", style="dim"),
    )
    return line


def thumbnail(frame: np.ndarray, max_cols: int, max_rows: int) -> Text:
    """Miniatura do quadro com caracteres '▀': cada caractere mostra 2 pixels (cima = cor do texto, baixo = fundo)."""
    h, w = frame.shape[:2]
    cols = max(1, max_cols)
    rows = max(1, round(cols * h / w / 2))
    if rows > max_rows:
        rows = max_rows
        cols = max(1, round(rows * 2 * w / h))
    small = cv2.resize(frame, (cols, rows * 2), interpolation=cv2.INTER_AREA)[:, :, ::-1]
    text = Text()
    for r in range(rows):
        top, bottom = small[2 * r], small[2 * r + 1]
        for c in range(cols):
            text.append("▀", Style(color=Color.from_rgb(*top[c]), bgcolor=Color.from_rgb(*bottom[c])))
        if r < rows - 1:
            text.append("\n")
    return text


def draw_boxes(frame: np.ndarray, boxes: list[tuple[float, float, float, float, tuple[int, int, int]]],
               width: int = 480) -> np.ndarray:
    """Cópia reduzida do quadro com caixas (x1, y1, x2, y2, cor BGR) grossas o bastante para aparecer na miniatura."""
    scale = width / frame.shape[1]
    out = cv2.resize(frame, (width, round(frame.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    thickness = max(2, width // 70)
    for x1, y1, x2, y2, color in boxes:
        cv2.rectangle(out, (int(x1 * scale), int(y1 * scale)), (int(x2 * scale), int(y2 * scale)), color, thickness)
    return out


def shell_command(cmd: list[str]) -> str:
    """Comando como seria digitado no terminal, com caminhos encurtados para o nome do arquivo."""
    def short(arg: str) -> str:
        looks_like_path = "/" in arg and not any(ch in arg for ch in "=:;[]()")  # filtros do ffmpeg têm esses
        return Path(arg).name if looks_like_path else arg

    shown, skip = [], 0
    for i, arg in enumerate(cmd):
        if skip:
            skip -= 1
        elif arg in ("-y", "-hide_banner", "-nostats"):
            continue
        elif arg in ("-loglevel", "-progress"):  # opções internas, sem interesse para quem lê
            skip = 1
        else:
            shown.append(short(arg))
    return "$ " + shlex.join(shown)


def decoding(path: Path, info) -> str:
    return f"OpenCV decodificando {path.name} ({info.codec} {info.width}x{info.height})"


def _model_lines(models: dict[str, list[float]]) -> list[str]:
    return [f"{name}: {int(count)} inferências, {total / count * 1000:.1f} ms cada"
            for name, (count, total) in models.items() if count]


def _bytes(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def _format_stats(stats: dict) -> str:
    return " · ".join(f"{k}: {v}" for k, v in stats.items())


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def _size(path: Path) -> str:
    try:
        return _bytes(path.stat().st_size)
    except OSError:
        return "?"
