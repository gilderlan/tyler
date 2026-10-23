import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from tyler.ops import watermark
from tyler.video import frames, probe


@pytest.mark.parametrize("text, expected", [
    ("bottom-right", "bottom-right"), ("right-down", "bottom-right"), ("down_right", "bottom-right"),
    ("Left Up", "top-left"), ("top", "top"), ("right", "right"), ("middle", "center"),
])
def test_parse_position(text, expected):
    assert watermark.parse_position(text) == expected


@pytest.mark.parametrize("text", ["diagonal", "left-right", "top-bottom", "top-left-top", ""])
def test_parse_position_rejects_invalid(text):
    with pytest.raises(ValueError):
        watermark.parse_position(text)


def test_all_positions_are_valid():
    assert all(watermark.parse_position(p) == p for p in watermark.POSITIONS)


def test_overlay_filter():
    f = watermark.overlay_filter("bottom-right", 200, 100, 30, 1.0)
    assert f == "[1:v]scale=200:100,format=rgba[wm];[0:v][wm]overlay=x=W-w-30:y=H-h-30:shortest=1:format=auto[v]"
    f = watermark.overlay_filter("top", 200, 100, 30, 0.5)
    assert "colorchannelmixer=aa=0.5" in f and "x=(W-w)/2:y=30" in f


@pytest.fixture(scope="module")
def video(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("v") / "in.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=640x360:d=1:r=30",
         "-f", "lavfi", "-i", "sine=d=1", "-pix_fmt", "yuv420p", "-shortest", str(path)],
        check=True,
    )
    return path


@pytest.fixture
def logo(tmp_path) -> Path:
    """Logo branco 100x50 com transparência."""
    path = tmp_path / "logo.png"
    cv2.imwrite(str(path), np.full((50, 100, 4), 255, dtype=np.uint8))
    return path


def test_watermark_bottom_right_keeps_duration_and_audio(video, logo, tmp_path):
    out = watermark.run(video, logo, tmp_path / "out.mp4", position="right-down", size=25, margin=5)
    info = probe(out)
    assert info.has_audio and info.duration == pytest.approx(1, abs=0.05)
    frame = next(frames(out))
    # 25% de 360 = 90x45, a 18px da borda: canto inferior direito branco, resto preto
    assert frame[360 - 18 - 20, 640 - 18 - 40].mean() > 200
    assert frame[20, 20].mean() < 30 and frame[360 - 5, 640 - 5].mean() < 30


def test_watermark_opacity(video, logo, tmp_path):
    out = watermark.run(video, logo, tmp_path / "out.mp4", position="center", opacity=0.5)
    assert 90 < next(frames(out))[180, 320].mean() < 170


def test_watermark_rejects_invalid_image(video, tmp_path):
    bad = tmp_path / "x.png"
    bad.write_text("não é imagem")
    with pytest.raises(watermark.InvalidWatermark):
        watermark.run(video, bad, tmp_path / "out.mp4")
    assert not (tmp_path / "out.mp4").exists()
