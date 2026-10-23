from pathlib import Path

from tyler import system
from tyler.video import FrameWriter


def test_thermal_state_is_known_or_none():
    assert system.thermal_state() in (*system.THERMAL_STATES, None)


def test_monitor_reports_this_process():
    sample = system.Monitor().sample()
    assert sample.cpu >= 0 and sample.ram > 0 and sample.cores >= 1


def test_threads_limit_reaches_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(system, "THREADS", 2)
    seen = []
    with FrameWriter(tmp_path / "x.mp4", 64, 64, 30, on_start=seen.append):
        pass
    assert "-threads" in seen[0] and seen[0][seen[0].index("-threads") + 1] == "2"
