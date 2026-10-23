"""Download e cache dos modelos de IA usados pelas operações."""

import os
import sys
import urllib.request
from pathlib import Path

MODELS_DIR = Path(os.environ.get("TYLER_MODELS_DIR", Path(__file__).resolve().parents[2] / "models"))


def ensure(filename: str, url: str) -> Path:
    """Retorna o caminho do modelo, baixando-o na primeira vez."""
    path = MODELS_DIR / filename
    if path.exists():
        return path
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Baixando modelo {filename}...", file=sys.stderr)
    tmp = path.with_suffix(path.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(path)
    return path


def yunet() -> Path:
    """Detector de rostos YuNet (OpenCV Zoo, ~230 KB)."""
    name = "face_detection_yunet_2023mar.onnx"
    return ensure(name, "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/" + name)
