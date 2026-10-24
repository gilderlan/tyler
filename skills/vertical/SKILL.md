---
name: vertical
description: Converts a horizontal video to vertical (9:16 for Reels, TikTok, Shorts, Stories), automatically following faces. Use when the user asks to make a video vertical, portrait, 9:16, or ready for reels/tiktok/shorts/stories (in any language, e.g. "deixa vertical").
argument-hint: <video> [auto|center|fit] [WIDTHxHEIGHT]
---

# /tyler:vertical

Converts the video to vertical with the Tyler CLI. Arguments received: `$ARGUMENTS`

Reply to the user in the language they wrote in. The CLI prints in Portuguese; translate what you report.

## Steps

1. Identify the input video. If none was given, ask for it. Resolve `~` and relative paths; confirm the file exists.
2. Pick the mode from the request (default `auto`):
   - `auto` — 9:16 crop that follows faces (people talking, interviews, vlogs).
   - `center` — fixed crop in the center (subject always in the middle, no people).
   - `fit` — shows the whole frame over a blurred background (landscapes, screen recordings, when nothing can be cropped out).
3. Run (long videos can take a few minutes; use a high timeout):

   ```bash
   uv run --project "${CLAUDE_PLUGIN_ROOT}" tyler vertical "<video>" --mode <mode> [--size 1080x1920] [-o "<output>"]
   ```

4. The last printed line is the path of the new video. Tell the user (the original is never changed).
5. If it fails, show the error and suggest `fit` or `center` as an alternative when the problem is face detection.
