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

AI-driven video editor: a Claude Code plugin that runs locally on your Mac.

> Named after Tyler Durden (*Fight Club*), the projectionist who tampered with films frame by frame.

## Goal

Edit videos by asking Claude Code in plain language, for example:

- "make this video vertical, following the person"
- "blur every face and license plate"
- "download this YouTube video"
- "cut from 1:30 to 2:45"
- "put my logo in the lower right corner"

## Installation

1. Install the programs Tyler relies on:

   ```bash
   brew install uv ffmpeg deno
   ```

2. Install the plugin in [Claude Code](https://code.claude.com):

   ```bash
   claude plugin marketplace add https://git.gilderlan.com/Gilderlan/tyler.git
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

Requirements: macOS (Apple Silicon), [uv](https://docs.astral.sh/uv/) with Python 3.12, ffmpeg and deno
(used by yt-dlp to download from YouTube). If any is missing, Tyler says so and how to install it.

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

The panel footer shows CPU and RAM usage (Tyler plus the ffmpeg processes it starts), the Mac's thermal state,
the AI models in use (inferences and average time) and the command being run. `--no-stats` hides the footer.

To run cooler, use `--eco`: Tyler and ffmpeg run in the background on the efficiency cores. It is about 3x slower.

## AI models

| Use | Model | Location |
|---|---|---|
| Faces | YuNet (OpenCV Zoo) | `models/` |
| Plates | YOLOv9 from [open-image-models](https://github.com/ankandrew/open-image-models) | `~/.cache/open-image-models/` |

They are downloaded automatically on first use.

## Roadmap

- [x] `vertical` — horizontal → 9:16 with smart framing
- [x] `blur` — automatic blurring of faces and plates
- [x] `cut` — cut a segment between two timestamps
- [x] `watermark` — image watermark
- [x] `download` — download video or audio from YouTube and other sites
- [ ] Finder Quick Actions
- [ ] Web interface

## License

[MIT](LICENSE) © 2026 Gilderlan Braz
