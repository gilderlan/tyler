import subprocess
from pathlib import Path

import numpy as np
import pytest

from tyler.ops import vertical
from tyler.video import probe


def test_subject_center_frames_all_faces_when_they_fit():
    boxes = [(100, 0, 50, 50), (300, 0, 50, 50)]
    assert vertical.subject_center(boxes, crop_w=600) == 225


def test_subject_center_picks_largest_face_when_they_do_not_fit():
    boxes = [(0, 0, 50, 50), (1500, 0, 200, 200)]
    assert vertical.subject_center(boxes, crop_w=600) == 1600


def test_subject_center_without_faces():
    assert vertical.subject_center([], crop_w=600) is None


def test_camera_path_stays_inside_frame_and_jumps_on_scene_cut():
    sample_frames = list(range(0, 60, 6))
    centers = [100.0] * 5 + [1800.0] * 5  # rosto à esquerda, corte, rosto à direita
    scenes = [0] * 5 + [1] * 5
    xs = vertical.camera_path(sample_frames, centers, scenes, total=60, frame_w=1920, crop_w=606)
    assert len(xs) == 60
    assert xs.min() >= 0 and xs.max() <= 1920 - 606
    assert xs[29] == 0 and xs[30] == 1920 - 606  # sem deslizar através do corte


def test_camera_path_centers_when_no_face():
    xs = vertical.camera_path([0, 10], [None, None], [0, 0], total=20, frame_w=1920, crop_w=606)
    assert np.all(xs == (1920 - 606) // 2)


@pytest.fixture(scope="module")
def horizontal_video(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("v") / "in.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:d=1:r=30",
         "-f", "lavfi", "-i", "sine=d=1", "-shortest", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )
    return path


@pytest.mark.parametrize("mode", vertical.MODES)
def test_run_produces_vertical_video_with_audio(horizontal_video, tmp_path, mode):
    out = vertical.run(horizontal_video, tmp_path / f"{mode}.mp4", mode=mode, size=(270, 480))
    info = probe(out)
    assert (info.width, info.height) == (270, 480)
    assert info.has_audio
    assert info.duration == pytest.approx(1, abs=0.1)


def test_camera_path_ignores_isolated_false_positive():
    sample_frames = list(range(0, 300, 6))
    centers = [None] * 50
    centers[25] = 1800.0  # uma detecção solta no canto
    xs = vertical.camera_path(sample_frames, centers, [0] * 50, total=300, frame_w=1920, crop_w=606)
    assert np.all(xs == (1920 - 606) // 2)


def test_camera_path_returns_to_center_after_long_gap():
    sample_frames = list(range(0, 300, 6))
    centers = [300.0] * 5 + [None] * 45  # rosto à esquerda só no começo
    xs = vertical.camera_path(sample_frames, centers, [0] * 50, total=300, frame_w=1920, crop_w=606)
    assert xs[0] < 20  # começa no rosto (a suavização da volta ao centro puxa só alguns pixels)
    assert xs[-1] == (1920 - 606) // 2


def test_camera_path_bridges_short_gap():
    sample_frames = list(range(0, 60, 6))
    centers = [300.0, 300.0, 300.0, None, None, 300.0, 300.0, 300.0, 300.0, 300.0]
    xs = vertical.camera_path(sample_frames, centers, [0] * 10, total=60, frame_w=1920, crop_w=606)
    assert np.all(xs == 0)
