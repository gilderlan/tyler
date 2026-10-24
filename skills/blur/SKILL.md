---
name: blur
description: Anonymizes a video by automatically blurring faces and/or vehicle license plates. Use when the user asks to blur, pixelate, censor, hide or anonymize faces, people, plates or cars in a video (in any language, e.g. "borra os rostos").
argument-hint: <video> [all|faces|plates] [blur|pixel|black]
---

# /tyler:blur

Blurs faces and plates with the Tyler CLI. Arguments received: `$ARGUMENTS`

Reply to the user in the language they wrote in. The CLI prints in Portuguese; translate what you report.

## Steps

1. Identify the input video. If none was given, ask for it. Resolve `~` and relative paths; confirm the file exists.
2. Pick the target from the request (default `all`):
   - `all` — faces and plates
   - `faces` — faces only
   - `plates` — plates only
3. Pick the style (default `blur`):
   - `blur` — soft blur
   - `pixel` — mosaic/pixelated
   - `black` — black box
4. Run (takes about 2x the video length; use a high timeout or run in the background for long videos):

   ```bash
   uv run --project "${CLAUDE_PLUGIN_ROOT}" tyler blur "<video>" --targets <target> --style <style> [-o "<output>"]
   ```

5. The last printed line is the path of the new video; the `quadros com rosto:` and `quadros com placa:` lines say in how many frames faces and plates were found. Tell the user both (the original is never changed).
6. Remind the user to watch the result before publishing: detection is automatic and can miss faces in profile, very small ones or partly covered ones.
