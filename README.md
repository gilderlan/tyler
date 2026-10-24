# Tyler

**English** · [Português](README.pt-BR.md)

```text
████████╗██╗   ██╗██╗     ███████╗██████╗
╚══██╔══╝╚██╗ ██╔╝██║     ██╔════╝██╔══██╗
   ██║    ╚████╔╝ ██║     █████╗  ██████╔╝
   ██║     ╚██╔╝  ██║     ██╔══╝  ██╔══██╗
   ██║      ██║   ███████╗███████╗██║  ██║
   ╚═╝      ╚═╝   ╚══════╝╚══════╝╚═╝  ╚═╝
  the first rule of Tyler: you do not
  overwrite the original video.
```

AI-driven video editor: a Claude Code plugin that runs locally on macOS and Linux.

> Named after Tyler Durden (*Fight Club*), the projectionist who tampered with films frame by frame.

## Goal

Edit videos by asking Claude Code in plain language, for example:

- "make this video vertical, following the person"
- "blur every face and license plate"
- "download this YouTube video"
- "cut from 1:30 to 2:45"
- "put my logo in the lower right corner"

## Installation

1. Install the programs Tyler relies on: uv, ffmpeg (version 7 or newer recommended) and deno.

   macOS:

   ```bash
   brew install uv ffmpeg deno
   ```

   Linux (Debian/Ubuntu; on other distributions, use their package manager for ffmpeg):

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   sudo apt install ffmpeg
   curl -fsSL https://deno.land/install.sh | sh
   ```

   Some distributions ship an older ffmpeg (Debian 12 has 5.1, Ubuntu 24.04 has 6.1). It works, but quick cuts
   (`--copy`) can come out a few tenths of a second longer. For ffmpeg 7 there, use a
   [static build](https://johnvansickle.com/ffmpeg/).

2. Install the plugin in [Claude Code](https://code.claude.com):

   ```bash
   claude plugin marketplace add gilderlan/tyler
   claude plugin install tyler@tyler
   ```

The first operation takes longer, because `uv` builds the Python environment inside the plugin.
To get new versions: `claude plugin marketplace update tyler`.

## Usage

In any folder, ask Claude Code in any language ("make video.mp4 vertical", "blur the plates in street.mp4")
or call a skill directly:

| Skill | What it does |
|---|---|
| `/tyler:vertical ~/Movies/video.mp4` | Horizontal → 9:16 following faces (or a center crop, or the whole frame over a blurred background) |
| `/tyler:blur ~/Movies/street.mp4` | Blurs faces and/or plates, with blur, mosaic or black box |
| `/tyler:cut ~/Movies/video.mp4 1:30 2:45` | Cuts a segment between two timestamps |
| `/tyler:watermark ~/Movies/video.mp4 ~/logo.png` | Places a logo in a corner or in the center |
| `/tyler:download <link>` | Downloads video or audio from YouTube, Instagram, TikTok, Vimeo... |

Every operation writes a new file next to the original (`<name>_tyler_<operation>.<ext>`); the original is never changed.
`download` names the file after the video title and never overwrites an existing file. Video comes out as H.264 + AAC
when the site offers it, which caps YouTube at 1080p. Only download your own videos, freely licensed ones, or ones you
have the author's permission for.

## Architecture

```
 Claude Code ── skills/ (/tyler:cut, /tyler:vertical, ...)
                   │  orchestration only: they call the CLI
           ┌───────▼────────┐
           │   tyler CLI    │  src/tyler/cli.py
           └───────┬────────┘
           ┌───────▼────────┐
           │ src/tyler/ops  │  ← the single implementation of each operation
           └───────┬────────┘
          ┌────────┴────────┐
       ffmpeg            AI models
                     (faces, plates)
```

Every operation lives in `src/tyler/ops/` and is exposed by the `tyler` CLI, the engine the skills call with
`uv run --project "${CLAUDE_PLUGIN_ROOT}" tyler <command>`. No logic lives in the skills.

## Layout

| Path | Contents |
|---|---|
| `src/tyler/` | Python library and CLI |
| `src/tyler/ops/` | One operation per module (vertical, blur, ...) |
| `skills/` | Claude Code skills (`/tyler:vertical`, `/tyler:blur`, ...) |
| `.claude-plugin/` | Plugin and marketplace manifests |
| `models/` | Downloaded AI models (not in git) |
| `samples/` | Test videos (not in git) |
| `tests/` | Tests |

## Development

Load the plugin straight from this folder, without installing it: `claude --plugin-dir .` (after editing a skill,
run `/reload-plugins`). Before publishing, run `claude plugin validate .`. Tests: `uv run pytest`.

Requirements: macOS (Apple Silicon) or Linux, [uv](https://docs.astral.sh/uv/) with Python 3.12,
ffmpeg 7 or newer and deno (used by yt-dlp to download from YouTube). If any is missing, Tyler says so and how to install it.

### CLI

The skills call the CLI, which you can also run directly to test an operation. Its messages are in Portuguese.

```bash
uv sync
uv run tyler --help

# horizontal → vertical following faces
uv run tyler vertical video.mp4
# fixed center crop / whole frame over a blurred background
uv run tyler vertical video.mp4 --mode center
uv run tyler vertical video.mp4 --mode fit

# blur faces and plates (or just one of them) with blur, mosaic or black box
uv run tyler blur video.mp4
uv run tyler blur video.mp4 --targets plates --style pixel

# cut a segment: seconds, MM:SS or HH:MM:SS; without an end, goes to the end of the video
uv run tyler cut video.mp4 1:30 2:45
uv run tyler cut video.mp4 1:30 --copy   # instant, no re-encoding (starts at the previous keyframe)

# watermark: position, size (% of the video's shorter side) and opacity
uv run tyler watermark video.mp4 logo.png                      # lower right corner, 20%
uv run tyler watermark video.mp4 logo.png -p top-left --size 10 --opacity 0.6

# download from YouTube (and Instagram, TikTok, Vimeo...): mp4 video or audio only
uv run tyler download https://www.youtube.com/watch?v=jNQXAC9IVRw
uv run tyler download --only-audio <link>                      # m4a, no re-encoding
uv run tyler download --only-audio --audio-format mp3 <link> -o music/
```

`download` uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) and saves to the current folder (or the file/folder given
in `-o`).

In a terminal, the CLI shows a live panel with the steps, progress bar, time left, stats (faces, plates, scene cuts)
and a thumbnail of the frame being analyzed with the detections drawn on it. Use `--no-preview` to hide the thumbnail
and `--plain` for plain text output (used automatically when the output isn't a terminal, as in the skills).
Ctrl+C cancels and deletes the incomplete video.

The panel footer shows CPU and RAM usage (Tyler plus the ffmpeg processes it starts), the Mac's thermal state (macOS only),
the AI models in use (inferences and average time) and the command being run. `--no-stats` hides the footer.

To run cooler, use `--eco`: Tyler and ffmpeg run in the background on the efficiency cores (on Linux, at lower
priority). It is about 3x slower.

## AI models

| Use | Model | Location |
|---|---|---|
| Faces | YuNet (OpenCV Zoo) | `models/` |
| Plates | YOLOv9 from [open-image-models](https://github.com/ankandrew/open-image-models) | `~/.cache/open-image-models/` |

They are downloaded automatically on first use. On Apple chips the plate model runs on CoreML, about 6x faster;
on Linux it runs on the CPU, so blurring plates takes longer.

## Roadmap

- [x] `vertical` — horizontal → 9:16 with smart framing
- [x] `blur` — automatic blurring of faces and plates
- [x] `cut` — cut a segment between two timestamps
- [x] `watermark` — image watermark
- [x] `download` — download video or audio from YouTube and other sites
- [ ] Finder Quick Actions
- [ ] Web interface

## Contributing

Contributions are welcome: bug fixes, new operations, better skills or translations.

**Getting started** (with uv, ffmpeg and deno installed, as in [Installation](#installation)):

```bash
git clone https://github.com/gilderlan/tyler.git
cd tyler
uv sync
uv run pytest
claude --plugin-dir .   # Claude Code with your local copy of the plugin
```

**Project rules** (also in `CLAUDE.md`, which Claude Code reads automatically):

- Video logic lives only in `src/tyler/ops/`, one module per operation, exposed as a `tyler` CLI subcommand.
  Skills only orchestrate: they call the CLI and never reimplement logic.
- Operations never print directly: they receive a `Reporter` (`src/tyler/report.py`) and report steps, stats
  and previews through it.
- Use ffmpeg for encoding and decoding, keep the original audio whenever possible, and never overwrite the input:
  the default output is `<name>_tyler_<operation>.<ext>` next to the original.
- If the operation needs a system program, check for it with `system.require()` at the start, so a missing
  program becomes a clear message instead of a traceback.
- Languages: skills, manifests and `README.md` in English; CLI messages, code comments and `README.pt-BR.md` in
  Portuguese. When you change the README, update both versions.

**Adding an operation**

1. Create `src/tyler/ops/<operation>.py` with a `run(...)` function that receives a `Reporter`.
2. Add the subcommand in `src/tyler/cli.py`.
3. Write tests in `tests/test_<operation>.py`, generating small test videos with ffmpeg (see `tests/test_cut.py`).
4. Create `skills/<operation>/SKILL.md` calling `uv run --project "${CLAUDE_PLUGIN_ROOT}" tyler <operation>`.
5. Document it in both READMEs.

**Before opening a pull request**

- `uv run pytest` passes. Download tests need internet access and are skipped without it. The plate test with a real
  photo needs `samples/car.png` (any photo of a car with a visible plate; it isn't in git) and is skipped without it.
- `claude plugin validate .` passes.
- You tried the change in Claude Code with `claude --plugin-dir .`.
- One subject per pull request, describing what changed and how you tested it.

**Reporting a bug:** [open an issue](https://github.com/gilderlan/tyler/issues) with your system (macOS or Linux distribution), the output of
`ffmpeg -version | head -1`, the command or request you made, and the full error message.

## License

[MIT](LICENSE) © 2026 Gilderlan Braz
