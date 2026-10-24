from pathlib import Path

import pytest

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


def test_require_explains_how_to_install(monkeypatch):
    monkeypatch.setattr(system.sys, "platform", "darwin")
    monkeypatch.setattr(system.shutil, "which", lambda p: None if p in ("ffmpeg", "ffprobe") else f"/bin/{p}")
    system.require("deno")
    with pytest.raises(system.MissingTool, match=r"^O Tyler precisa do ffmpeg, que não está instalado\. "
                                                  r"Instale com: brew install ffmpeg$"):
        system.require(*system.VIDEO_TOOLS)


def test_require_lists_every_missing_tool(monkeypatch):
    monkeypatch.setattr(system.sys, "platform", "darwin")
    monkeypatch.setattr(system.shutil, "which", lambda p: None)
    with pytest.raises(system.MissingTool, match=r"^Para baixar do YouTube, o Tyler precisa do ffmpeg e do deno, "
                                                  r"que não estão instalados\. Instale com: brew install ffmpeg deno$"):
        system.require("ffmpeg", "deno", purpose="baixar do YouTube")


@pytest.mark.parametrize("installed, packages, hint", [
    ({"apt-get"}, ["ffmpeg"], "sudo apt install ffmpeg"),
    ({"dnf"}, ["ffmpeg"], "sudo dnf install ffmpeg"),
    ({"pacman", "apt-get"}, ["ffmpeg"], "sudo apt install ffmpeg"),  # apt tem prioridade
    (set(), ["ffmpeg"], "o gerenciador de pacotes do seu sistema (ffmpeg)"),
    ({"apt-get"}, ["deno"], system.DENO_INSTALL),
    ({"apt-get"}, ["ffmpeg", "deno"], f"sudo apt install ffmpeg e {system.DENO_INSTALL}"),
])
def test_install_hint_on_linux(monkeypatch, installed, packages, hint):
    monkeypatch.setattr(system.sys, "platform", "linux")
    monkeypatch.setattr(system.shutil, "which", lambda p: f"/usr/bin/{p}" if p in installed else None)
    assert system.install_hint(packages) == hint
