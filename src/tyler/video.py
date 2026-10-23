"""Utilitários de vídeo compartilhados entre as operações: leitura de metadados,
leitura de quadros e escrita via ffmpeg."""

import json
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np

from tyler import system

cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)


@dataclass
class VideoInfo:
    width: int  # já considerando rotação (vídeos de celular)
    height: int
    fps: float
    duration: float
    has_audio: bool
    codec: str = "?"

    def describe(self) -> str:
        m, sec = divmod(int(round(self.duration)), 60)
        return f"{self.width}x{self.height} · {self.codec} · {m}:{sec:02d} · {self.fps:.2f} fps"


def probe(path: Path) -> VideoInfo:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(out.stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if video is None:
        raise ValueError(f"{path} não tem faixa de vídeo")
    width, height = video["width"], video["height"]
    rotation = 0
    for side in video.get("side_data_list", []):
        rotation = int(side.get("rotation", rotation))
    if abs(rotation) in (90, 270):
        width, height = height, width
    return VideoInfo(
        width=width,
        height=height,
        fps=float(Fraction(video.get("avg_frame_rate") or video["r_frame_rate"])) or 30.0,
        duration=float(data["format"].get("duration", 0)),
        has_audio=any(s["codec_type"] == "audio" for s in data["streams"]),
        codec=video.get("codec_name", "?"),
    )


def frames(path: Path) -> Iterator[np.ndarray]:
    """Lê os quadros (BGR) do vídeo em ordem."""
    params = [] if system.THREADS is None else [cv2.CAP_PROP_N_THREADS, system.THREADS]
    cap = cv2.VideoCapture(str(path), cv2.CAP_ANY, params)
    if not cap.isOpened():
        raise ValueError(f"Não foi possível abrir {path}")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield frame
    finally:
        cap.release()


def default_output(input_path: Path, operation: str) -> Path:
    return input_path.with_name(f"{input_path.stem}_tyler_{operation}.mp4")


def encode_args(output: Path) -> list[str]:
    """Parâmetros de codificação padrão: H.264 de alta qualidade + AAC, compatível com redes sociais."""
    return [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", *_threads(),
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output),
    ]


def _threads() -> list[str]:
    return [] if system.THREADS is None else ["-threads", str(system.THREADS)]


Command = Callable[[list[str]], None]


def run_ffmpeg(args: list[str], on_frame: Callable[[int], None] | None = None, on_start: Command | None = None) -> None:
    """Roda o ffmpeg; `on_start` recebe o comando, `on_frame` o número de quadros já processados."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1", *_threads(), *args]
    if on_start:
        on_start(cmd)
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True) as proc:
        for line in proc.stdout:
            if on_frame and line.startswith("frame="):
                on_frame(int(line.split("=", 1)[1]))
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg falhou ao converter o vídeo")


class FrameWriter:
    """Escreve quadros BGR num vídeo, copiando o áudio do vídeo original."""

    def __init__(self, output: Path, width: int, height: int, fps: float, audio_from: Path | None = None,
                 on_start: Command | None = None):
        args = ["-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", f"{fps}", "-i", "-"]
        if audio_from is not None:
            args += ["-i", str(audio_from), "-map", "0:v", "-map", "1:a?", "-shortest"]
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args, *encode_args(output)]
        if on_start:
            on_start(cmd)
        self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def write(self, frame: np.ndarray) -> None:
        self._proc.stdin.write(frame.tobytes())

    def close(self) -> None:
        self._proc.stdin.close()
        if self._proc.wait() != 0:
            raise RuntimeError("ffmpeg falhou ao gravar o vídeo")

    def __enter__(self) -> "FrameWriter":
        return self

    def __exit__(self, exc_type, *exc) -> None:
        if exc_type is None:
            self.close()
        else:  # interrompido (erro ou Ctrl+C): encerra o ffmpeg sem esperar o vídeo terminar
            self._proc.kill()
            self._proc.wait()
