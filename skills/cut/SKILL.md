---
name: cut
description: Cuts a segment out of a video between two timestamps. Use when the user asks to cut, trim, clip, extract a segment or keep "from minute X to Y" of a video (in any language, e.g. "corta do 1:30 ao 2:45").
argument-hint: <video> <start> [end]
---

# /tyler:cut

Cuts a segment of the video with the Tyler CLI. Arguments received: `$ARGUMENTS`

Reply to the user in the language they wrote in. The CLI prints in Portuguese; translate what you report.

## Steps

1. Identify the input video. If none was given, ask for it. Resolve `~` and relative paths; confirm the file exists.
2. Identify the start and end. Accepted formats: seconds (`90`), `MM:SS` (`1:30`) or `HH:MM:SS` (`1:02:03`), with optional fraction (`1:30.5`).
   - "from 1:30 to the end" → start only.
   - "the first 30 seconds" → start `0`, end `30`.
   - "2 minutes starting at 1:00" → compute the end (`3:00`).
3. The cut is frame-exact by default (re-encodes). Use `--copy` only if the user asks for speed or "no quality loss" and accepts that the start may move a few seconds earlier (it snaps to the previous keyframe).
4. Run:

   ```bash
   uv run --project "${CLAUDE_PLUGIN_ROOT}" tyler cut "<video>" <start> [end] [--copy] [-o "<output>"]
   ```

5. The last printed line is the path of the new video; the `trecho:` line gives the length of the cut. Tell the user both (the original is never changed).
