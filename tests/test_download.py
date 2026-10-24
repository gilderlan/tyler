from pathlib import Path

import pytest

from tyler.ops import download
from tyler.report import Reporter
from tyler.video import probe

ZOO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo", 19s, primeiro vídeo do YouTube


def test_options_video_prefers_h264_mp4():
    opts = download.options(None, only_audio=False, audio_format="m4a")
    assert opts["format"].startswith("bv*[vcodec^=avc1]+ba[ext=m4a]")
    assert opts["merge_output_format"] == "mp4"
    assert opts["outtmpl"] == "%(title)s.%(ext)s"
    assert opts["overwrites"] is False and opts["noplaylist"] is True


def test_options_audio_keeps_m4a_or_converts_to_mp3():
    m4a = download.options(None, only_audio=True, audio_format="m4a")
    assert m4a["format"] == "ba[ext=m4a]/ba"
    assert m4a["postprocessors"] == [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}]
    mp3 = download.options(None, only_audio=True, audio_format="mp3")
    assert mp3["postprocessors"] == [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                                      "preferredquality": "192"}]


def test_output_template_for_folder_and_file(tmp_path):
    assert download.options(tmp_path, False, "m4a")["outtmpl"] == str(tmp_path / "%(title)s.%(ext)s")
    assert download.options("nova/", False, "m4a")["outtmpl"] == "nova/%(title)s.%(ext)s"
    assert download.options(tmp_path / "clip.mkv", False, "m4a")["outtmpl"] == str(tmp_path / "clip.%(ext)s")


def test_command_line_shows_equivalent_yt_dlp():
    cmd = download.command_line(ZOO, download.options(None, True, "mp3"))
    assert cmd == ["yt-dlp", "-f", "ba[ext=m4a]/ba", "-x", "--audio-format", "mp3",
                   "-o", "%(title)s.%(ext)s", ZOO]


def test_invalid_audio_format():
    with pytest.raises(ValueError):
        download.run(ZOO, audio_format="flac")


def test_progress_hooks_become_steps(tmp_path):
    reporter = Reporter()
    progress = download._Progress(reporter, "m4a")
    video = {"vcodec": "avc1", "acodec": "none"}
    part = tmp_path / "x.f1.mp4.part"
    for done in (0, 500, 1000):
        progress.on_download({"status": "downloading", "info_dict": video, "downloaded_bytes": done,
                              "total_bytes": 1000, "tmpfilename": str(part), "filename": str(tmp_path / "x.f1.mp4")})
    assert progress._step.unit == "B" and progress._step.done == 1000
    progress.on_download({"status": "finished", "info_dict": video, "filename": str(tmp_path / "x.f1.mp4")})
    progress.on_postprocess({"status": "started", "postprocessor": "Merger"})
    assert progress._name == download.MERGE_STEP
    progress.on_postprocess({"status": "finished", "postprocessor": "Merger"})
    assert progress._step is None and progress.downloaded
    assert reporter.stats["vídeo"] == "1000 B"

    part.write_bytes(b"0")
    (tmp_path / "x.f1.mp4.part-Frag1").write_bytes(b"0")
    (tmp_path / "outro.mp4").write_bytes(b"0")
    progress.cleanup()
    assert [p.name for p in tmp_path.iterdir()] == ["outro.mp4"]


@pytest.fixture
def online():
    """Pula os testes de rede quando não há internet ou o YouTube recusa."""
    def run(*args, **kwargs):
        try:
            return download.run(*args, **kwargs)
        except download.DownloadFailed as e:
            pytest.skip(f"sem acesso ao YouTube: {e}")
    return run


def test_download_video_mp4(online, tmp_path):
    path = online(ZOO, tmp_path)
    assert path.parent == tmp_path and path.suffix == ".mp4"
    info = probe(path)
    assert info.has_audio and info.codec == "h264" and info.duration > 15


def test_download_only_audio_m4a(online, tmp_path):
    path = online(ZOO, tmp_path / "zoo", only_audio=True)
    assert path == tmp_path / "zoo.m4a"
    assert not any(p.suffix == ".part" for p in tmp_path.iterdir())


def test_youtube_needs_deno(monkeypatch):
    from tyler import system
    monkeypatch.setattr(system.sys, "platform", "darwin")
    monkeypatch.setattr(system.shutil, "which", lambda p: None if p == "deno" else f"/bin/{p}")
    with pytest.raises(system.MissingTool, match="Para baixar do YouTube.*brew install deno"):
        download.run("https://youtu.be/jNQXAC9IVRw")


def test_youtube_lists_ffmpeg_and_deno_together(monkeypatch):
    from tyler import system
    monkeypatch.setattr(system.sys, "platform", "darwin")
    monkeypatch.setattr(system.shutil, "which", lambda p: None)
    with pytest.raises(system.MissingTool, match="precisa do ffmpeg e do deno.*brew install ffmpeg deno"):
        download.run("https://youtu.be/jNQXAC9IVRw")
