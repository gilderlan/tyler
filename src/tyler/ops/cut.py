"""Corta um trecho do vídeo, entre dois tempos.

Por padrão recodifica o trecho, o que deixa o corte exato no quadro pedido. Com `copy=True`
copia as faixas sem recodificar: é quase instantâneo e não perde qualidade, mas o início
cai no quadro-chave mais próximo antes do tempo pedido (pode adiantar alguns segundos).
"""

import re
from pathlib import Path

from tyler.report import PlainReporter, Reporter, shell_command
from tyler.video import default_output, encode_args, probe, run_ffmpeg

STEP = "Cortando com ffmpeg"
COPY_STEP = "Copiando trecho (sem recodificar)"


class InvalidRange(ValueError):
    """Trecho fora do vídeo ou com o fim antes do início, com mensagem para o usuário."""


_TIME = re.compile(r"^(?:(?:(\d+):)?(\d+):)?(\d+(?:[.,]\d+)?)$")


def parse_time(text: str) -> float:
    """Converte "90", "1:30", "01:02:03" ou "1:30.5" em segundos."""
    match = _TIME.match(text.strip())
    if not match:
        raise ValueError(f"Tempo inválido: {text!r}. Use segundos (90), MM:SS (1:30) ou HH:MM:SS (1:02:03)")
    h, m, s = match.groups()
    if (h or m) and float(s.replace(",", ".")) >= 60 or h and int(m) >= 60:
        raise ValueError(f"Tempo inválido: {text!r}. Minutos e segundos vão até 59")
    return int(h or 0) * 3600 + int(m or 0) * 60 + float(s.replace(",", "."))


def format_time(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(int(m), 60)
    text = f"{m}:{s:05.2f}" if not h else f"{h}:{m:02d}:{s:05.2f}"
    return text.removesuffix(".00")


def run(input_path: Path, output: Path | None = None, start: float = 0.0, end: float | None = None,
        copy: bool = False, reporter: Reporter | None = None) -> Path:
    output = output or default_output(input_path, "cut")
    reporter = reporter or PlainReporter()
    info = probe(input_path)
    end = info.duration if end is None else end
    if start < 0 or start >= info.duration:
        raise InvalidRange(f"O início ({format_time(start)}) precisa estar dentro do vídeo "
                           f"(duração {format_time(info.duration)})")
    if end <= start:
        raise InvalidRange(f"O fim ({format_time(end)}) precisa ser depois do início ({format_time(start)})")
    end = min(end, info.duration)
    length = end - start

    reporter.header(f"cut {format_time(start)} → {format_time(end)} · {input_path.name}", info.describe())
    reporter.stats["trecho"] = format_time(length)
    if copy:
        codec = ["-map", "0:v:0", "-map", "0:a?", "-c", "copy", "-avoid_negative_ts", "make_zero",
                 "-movflags", "+faststart", str(output)]
    else:
        codec = ["-map", "0:v:0", "-map", "0:a?", *encode_args(output)]
    # -ss antes do -i: busca rápida; recodificando, o corte continua exato no quadro
    args = ["-ss", f"{start:.3f}", "-i", str(input_path), "-t", f"{length:.3f}", *codec]
    with reporter.step(COPY_STEP if copy else STEP, round(length * info.fps)) as step:
        run_ffmpeg(args, on_frame=step.update, on_start=lambda cmd: reporter.command(shell_command(cmd)))
    if copy:
        actual = probe(output).duration
        if actual - length > 0.5:  # começou no quadro-chave antes do início pedido
            reporter.stats["trecho"] = f"{format_time(actual)} (começa em {format_time(max(0.0, end - actual))}, quadro-chave)"
    return output
