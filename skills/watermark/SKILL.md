---
name: watermark
description: Places an image (logo, watermark, badge) over a video, in a corner or in the center. Use when the user asks to add a watermark, logo or visual signature to a video (in any language, e.g. "coloca meu logo").
argument-hint: <video> <image> [position] [size%] [opacity]
---

# /tyler:watermark

Applies a watermark with the Tyler CLI. Arguments received: `$ARGUMENTS`

Reply to the user in the language they wrote in. The CLI prints in Portuguese; translate what you report.

## Steps

1. Identify the video and the image. If either is missing, ask. Resolve `~` and relative paths and confirm both exist. A PNG with a transparent background gives the best result.
2. Pick the position from the request (default `bottom-right`): `top-left`, `top`, `top-right`, `left`, `center`, `right`, `bottom-left`, `bottom`, `bottom-right`. "Lower right corner" → `bottom-right`, "top middle" → `top`.
3. Optional tweaks:
   - `--size` — watermark width as % of the video's shorter side (default 20; "small" ≈ 10, "large" ≈ 35).
   - `--opacity` — from 0.1 to 1 (default 1; "subtle"/"semi-transparent" ≈ 0.5).
   - `--margin` — distance from the edge in % (default 3).
4. Run:

   ```bash
   uv run --project "${CLAUDE_PLUGIN_ROOT}" tyler watermark "<video>" "<image>" -p <position> [--size N] [--opacity N] [-o "<output>"]
   ```

5. The last printed line is the path of the new video; the `marca:` line shows the final watermark size in pixels. Tell the user both (the original is never changed).
