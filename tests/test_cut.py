import subprocess
from pathlib import Path

import pytest

from tyler.ops import cut
from tyler.video import probe


@pytest.mark.parametrize("text, seconds", [
    ("90", 90), ("1:30", 90), ("01:02:03", 3723), ("1:30.5", 90.5), ("0,25", 0.25), (" 2:00 ", 120),
])
def test_parse_time(text, seconds):
    assert cut.parse_time(text) == seconds


@pytest.mark.parametrize("text", ["", "abc", "1:75", "1:60:00", "-5", "1::30"])
def test_parse_time_rejects_invalid(text):
    with pytest.raises(ValueError):
        cut.parse_time(text)


def test_format_time():
    assert cut.format_time(90) == "1:30"
    assert cut.format_time(3723.5) == "1:02:03.50"


@pytest.fixture(scope="module")
def video(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("v") / "in.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=320x240:d=6:r=30",
         "-f", "lavfi", "-i", "sine=d=6", "-pix_fmt", "yuv420p", "-shortest", str(path)],
        check=True,
    )
    return path


def test_cut_is_exact_and_keeps_audio(video, tmp_path):
    out = cut.run(video, tmp_path / "out.mp4", start=1.5, end=4)
    info = probe(out)
    assert info.has_audio and info.duration == pytest.approx(2.5, abs=0.05)


def test_cut_until_end(video, tmp_path):
    out = cut.run(video, tmp_path / "out.mp4", start=5)
    assert probe(out).duration == pytest.approx(1, abs=0.05)


def test_cut_copy(video, tmp_path):
    out = cut.run(video, tmp_path / "out.mp4", start=0, end=3, copy=True)
    assert probe(out).duration == pytest.approx(3, abs=0.1)


@pytest.mark.parametrize("start, end", [(4, 2), (10, None), (-1, 2)])
def test_cut_rejects_invalid_range(video, tmp_path, start, end):
    with pytest.raises(cut.InvalidRange):
        cut.run(video, tmp_path / "out.mp4", start=start, end=end)
    assert not (tmp_path / "out.mp4").exists()
