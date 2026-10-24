import subprocess
from pathlib import Path

import pytest

from tyler import agent
from tyler.report import PlainReporter
from tyler.video import probe


@pytest.fixture
def video(tmp_path) -> Path:
    path = tmp_path / "praia.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=320x240:d=4:r=30",
         "-f", "lavfi", "-i", "sine=d=4", "-pix_fmt", "yuv420p", "-shortest", str(path)],
        check=True,
    )
    return path


def run(name: str, args: dict) -> str:
    return agent.run_tool(name, args, new_reporter=PlainReporter)


def test_every_tool_has_a_handler():
    assert {t["name"] for t in agent.TOOLS} == set(agent._HANDLERS)


def test_listar_videos(video):
    (video.parent / "notas.txt").write_text("x")
    text = run("listar_videos", {"pasta": str(video.parent)})
    assert "praia.mp4" in text and "notas.txt" not in text


def test_info_video(video):
    assert "320x240" in run("info_video", {"video": str(video)})


def test_cortar_writes_next_to_original(video):
    text = run("cortar", {"video": str(video), "inicio": "1", "fim": "3"})
    output = video.with_name("praia_tyler_cut.mp4")
    assert f"Arquivo gerado: {output}" in text
    assert abs(probe(output).duration - 2) < 0.1


@pytest.mark.parametrize("name, args, message", [
    ("cortar", {"video": "/nao/existe.mp4", "inicio": "0"}, "Arquivo não encontrado"),
    ("cortar", {"video": "VIDEO", "inicio": "9"}, "precisa estar dentro do vídeo"),
    ("cortar", {"video": "VIDEO", "inicio": "abc"}, "Tempo inválido"),
    ("cortar", {"video": "VIDEO"}, "Falta o parâmetro"),
    ("baixar", {"url": "youtube.com/x"}, "Link inválido"),
    ("girar", {}, "Ferramenta desconhecida"),
])
def test_errors_become_tool_errors(video, name, args, message):
    args = {k: str(video) if v == "VIDEO" else v for k, v in args.items()}
    with pytest.raises(agent.ToolError, match=message):
        run(name, args)
    assert not video.with_name("praia_tyler_cut.mp4").exists()  # nada pela metade para trás


def test_usage_counts_tokens_and_cost():
    from types import SimpleNamespace
    usage = agent.Usage()
    before = agent.replace(usage)
    usage.add("claude-opus-5-5", SimpleNamespace(input_tokens=1000, output_tokens=500,
                                                 cache_read_input_tokens=9000, cache_creation_input_tokens=0))
    assert usage.cost == pytest.approx((1000 * 4 + 500 * 20 + 9000 * 0.2) / 1_000_000)
    assert usage.context == 10_500 and not usage.estimated
    assert "contexto 10,5 mil de 1 mi" in usage.toolbar() and "cache 90%" in usage.toolbar()
    assert usage.since(before) == "↑ 10 mil  ↓ 500  ·  US$ 0,016"
    usage.add("outro-modelo", SimpleNamespace(input_tokens=10, output_tokens=0,
                                              cache_read_input_tokens=None, cache_creation_input_tokens=None))
    assert usage.estimated and "≈ US$" in usage.toolbar()


def test_missing_ffmpeg_becomes_tool_error(video, monkeypatch):
    from tyler import system
    monkeypatch.setattr(system.shutil, "which", lambda p: None)
    with pytest.raises(agent.ToolError, match="brew install ffmpeg"):
        run("cortar", {"video": str(video), "inicio": "0"})
