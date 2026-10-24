"""Aplica uma imagem (logo, marca d'água) sobre o vídeo inteiro.

O tamanho é relativo ao lado menor do vídeo, para a marca ficar proporcional tanto em
vídeo horizontal quanto vertical. A transparência do PNG é preservada; `opacity` deixa
a imagem toda mais transparente.
"""

from pathlib import Path

import cv2

from tyler import system
from tyler.report import PlainReporter, Reporter, shell_command
from tyler.video import default_output, encode_args, probe, run_ffmpeg

POSITIONS = ("top-left", "top", "top-right", "left", "center", "right", "bottom-left", "bottom", "bottom-right")

STEP = "Aplicando marca d'água"

# sinônimos aceitos na posição, em qualquer ordem: "right-down", "down-right", "bottom-right"...
_VERTICAL = {"top": "top", "up": "top", "bottom": "bottom", "down": "bottom"}
_HORIZONTAL = {"left": "left", "right": "right"}


class InvalidWatermark(ValueError):
    """Imagem ilegível ou opções fora do intervalo, com mensagem para o usuário."""


def parse_position(text: str) -> str:
    """Normaliza a posição: "right-down" → "bottom-right", "centro"/"middle" → "center"."""
    parts = text.lower().replace("_", "-").replace(" ", "-").split("-")
    if parts in (["center"], ["middle"]):
        return "center"
    vertical = [_VERTICAL[p] for p in parts if p in _VERTICAL]
    horizontal = [_HORIZONTAL[p] for p in parts if p in _HORIZONTAL]
    if len(vertical) + len(horizontal) != len(parts) or len(vertical) > 1 or len(horizontal) > 1:
        raise ValueError(f"Posição inválida: {text!r}. Use uma de: {', '.join(POSITIONS)}")
    return "-".join(vertical + horizontal)


def run(input_path: Path, image: Path, output: Path | None = None, position: str = "bottom-right",
        size: float = 20, opacity: float = 1.0, margin: float = 3, reporter: Reporter | None = None) -> Path:
    """`size` e `margin` são porcentagens do lado menor do vídeo; `opacity` vai de 0 a 1."""
    system.require(*system.VIDEO_TOOLS)
    position = parse_position(position)
    if not 0 < size <= 100:
        raise InvalidWatermark(f"Tamanho inválido: {size}. Use uma porcentagem entre 1 e 100")
    if not 0 < opacity <= 1:
        raise InvalidWatermark(f"Opacidade inválida: {opacity}. Use um valor entre 0.1 e 1")
    if not 0 <= margin <= 40:
        raise InvalidWatermark(f"Margem inválida: {margin}. Use uma porcentagem entre 0 e 40")
    logo = cv2.imread(str(image), cv2.IMREAD_UNCHANGED)
    if logo is None:
        raise InvalidWatermark(f"Não foi possível ler a imagem {image} (use PNG, JPG ou WebP)")
    output = output or default_output(input_path, "watermark")
    reporter = reporter or PlainReporter()
    info = probe(input_path)

    short_side = min(info.width, info.height)
    logo_w = max(2, round(short_side * size / 100 / 2) * 2)
    logo_h = max(2, round(logo_w * logo.shape[0] / logo.shape[1] / 2) * 2)
    pad = round(short_side * margin / 100)

    reporter.header(f"watermark ({position}) · {input_path.name}", info.describe())
    reporter.stats["marca"] = f"{image.name} {logo_w}x{logo_h}" + (f" · {opacity:.0%}" if opacity < 1 else "")
    args = ["-i", str(input_path), "-loop", "1", "-i", str(image),
            "-filter_complex", overlay_filter(position, logo_w, logo_h, pad, opacity),
            "-map", "[v]", "-map", "0:a?", *encode_args(output)]
    with reporter.step(STEP, round(info.duration * info.fps)) as step:
        run_ffmpeg(args, on_frame=step.update, on_start=lambda cmd: reporter.command(shell_command(cmd)))
    return output


def overlay_filter(position: str, width: int, height: int, pad: int, opacity: float) -> str:
    """Filtro do ffmpeg: redimensiona a imagem, aplica a opacidade e sobrepõe na posição pedida."""
    x = {"left": f"{pad}", "right": f"W-w-{pad}"}.get(_side(position, _HORIZONTAL), "(W-w)/2")
    y = {"top": f"{pad}", "bottom": f"H-h-{pad}"}.get(_side(position, _VERTICAL), "(H-h)/2")
    logo = f"[1:v]scale={width}:{height},format=rgba"
    if opacity < 1:
        logo += f",colorchannelmixer=aa={opacity:g}"
    return f"{logo}[wm];[0:v][wm]overlay=x={x}:y={y}:shortest=1:format=auto[v]"


def _side(position: str, names: dict[str, str]) -> str | None:
    return next((p for p in position.split("-") if p in names.values()), None)
