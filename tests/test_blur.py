import subprocess
from pathlib import Path

import numpy as np
import pytest

from tyler.ops import blur
from tyler.video import frames, probe


def test_anonymize_only_changes_inside_boxes():
    rng = np.random.default_rng(0)
    frame = rng.integers(0, 256, (360, 640, 3), dtype=np.uint8)
    out = blur.anonymize(frame, [(100, 100, 200, 200, "plate")], "blur")
    assert not np.array_equal(out[100:200, 100:200], frame[100:200, 100:200])
    out[100:200, 100:200] = frame[100:200, 100:200]
    assert np.array_equal(out, frame)


def test_anonymize_face_is_ellipse():
    frame = np.full((200, 200, 3), 255, dtype=np.uint8)
    out = blur.anonymize(frame, [(0, 0, 200, 200, "face")], "black")
    assert out[100, 100].sum() == 0  # centro da elipse
    assert out[0, 0].sum() == 255 * 3  # canto fora da elipse


def test_anonymize_without_boxes_returns_same_frame():
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    assert blur.anonymize(frame, [], "pixel") is frame


@pytest.fixture(scope="module")
def street_video(tmp_path_factory) -> Path:
    """Vídeo com uma foto de carro (placa visível) se movendo, se a imagem de exemplo existir."""
    car = Path(__file__).parents[1] / "samples" / "car.png"
    if not car.exists():
        pytest.skip("samples/car.png não encontrado")
    path = tmp_path_factory.mktemp("v") / "rua.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=gray:s=1280x720:d=1:r=30",
         "-f", "lavfi", "-i", "sine=d=1", "-loop", "1", "-i", str(car),
         "-filter_complex", "[2:v]scale=800:-2[c];[0:v][c]overlay=x='100+t*100':y=150:shortest=1[v]",
         "-map", "[v]", "-map", "1:a", "-pix_fmt", "yuv420p", "-t", "1", str(path)],
        check=True,
    )
    return path


def test_run_blurs_plate(street_video, tmp_path):
    out = blur.run(street_video, tmp_path / "out.mp4", targets="plates")
    info = probe(out)
    assert (info.width, info.height) == (1280, 720) and info.has_audio
    changed = [not np.allclose(a, b, atol=25) for a, b in zip(frames(street_video), frames(out))]
    assert all(changed)  # placa borrada em todos os quadros
