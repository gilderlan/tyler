import subprocess
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest

from tyler.ops import blur, vertical
from tyler.report import PlainReporter, Reporter, Step, draw_boxes, thumbnail


class FakeReporter(Reporter):
    """Registra o que as operações reportam, chamando as prévias para garantir que funcionam."""

    def __init__(self):
        super().__init__()
        self.planned: list[str] = []
        self.steps: list[str] = []
        self.previews = 0

    def plan(self, steps):
        self.planned = list(steps)

    def _new_step(self, name, total):
        self.steps.append(name)
        reporter = self

        class _Step(Step):
            def update(self, done, stats=None, preview=None):
                super().update(done, stats)
                if preview is not None:
                    assert preview().ndim == 3
                    reporter.previews += 1

        return _Step(name, total)


def test_thumbnail_fits_limits_and_keeps_aspect():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    lines = thumbnail(frame, max_cols=72, max_rows=22).plain.split("\n")
    assert len(lines) == 20 and all(len(line) == 72 for line in lines)

    tall = np.zeros((1920, 1080, 3), dtype=np.uint8)
    lines = thumbnail(tall, max_cols=72, max_rows=22).plain.split("\n")
    assert len(lines) == 22 and len(lines[0]) == 25


def test_draw_boxes_returns_reduced_copy():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    out = draw_boxes(frame, [(100, 100, 400, 400, (0, 255, 0))])
    assert out.shape == (270, 480, 3) and out.any() and not frame.any()


def test_plain_reporter_prints_steps_and_summary(capsys, tmp_path):
    reporter = PlainReporter()
    with reporter.step("Etapa", 100) as step:
        for i in range(1, 101):
            step.update(i, stats={"rostos": i})
    out = tmp_path / "x.mp4"
    out.write_bytes(b"0" * 2048)
    reporter.done(out, 3.0)
    err = capsys.readouterr().err
    assert "Etapa: 25%" in err and "Etapa: 100%" in err
    assert "rostos: 100" in err and "2.0 KB" in err


@pytest.fixture(scope="module")
def video(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("v") / "in.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:d=1:r=30",
         "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )
    return path


def test_vertical_auto_reports_steps_and_previews(video, tmp_path):
    reporter = FakeReporter()
    vertical.run(video, tmp_path / "out.mp4", size=(270, 480), reporter=reporter)
    assert reporter.steps == reporter.planned == [vertical.ANALYZE_STEP, vertical.RENDER_STEP]
    assert "cortes de cena" in reporter.stats and reporter.previews > 0


def test_blur_reports_detection_stats(video, tmp_path):
    reporter = FakeReporter()
    blur.run(video, tmp_path / "out.mp4", targets="faces", reporter=reporter)
    assert reporter.steps == reporter.planned == ["Detectando rostos", blur.APPLY_STEP]
    assert reporter.stats == {"quadros com rosto": 0}


def test_inference_counts_calls_and_time():
    reporter = Reporter()
    for _ in range(3):
        with reporter.inference("modelo"):
            pass
    count, total = reporter.models["modelo"]
    assert count == 3 and total >= 0 and reporter.active_model == "modelo"


def test_shell_command_shortens_paths_but_not_filters():
    from tyler.report import shell_command

    cmd = ["ffmpeg", "-i", "/Users/x/Downloads/v.mp4", "-vf", "crop=trunc(ih*0.56/2)*2:ih", "/tmp/out.mp4"]
    assert shell_command(cmd) == "$ ffmpeg -i v.mp4 -vf 'crop=trunc(ih*0.56/2)*2:ih' out.mp4"


def test_system_footer_shows_cpu_as_share_of_whole_mac():
    import io

    from rich.console import Console

    from tyler.report import RichReporter
    from tyler.system import Sample

    reporter = RichReporter()
    reporter.monitor.sample = lambda: Sample(cpu=776, ram=475 * 1024**2, cores=10, thermal="normal")
    console = Console(file=io.StringIO(), width=120)
    console.print(reporter._render_system())
    text = console.file.getvalue()
    assert "78% do Mac" in text and "7.8 de 10 núcleos" in text
