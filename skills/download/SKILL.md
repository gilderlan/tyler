---
name: download
description: Downloads a video (mp4) or just the audio (m4a/mp3) from YouTube and other sites (Instagram, TikTok, Facebook, Vimeo...). Use when the user asks to download, save or grab a video or audio from a link (in any language, e.g. "baixa esse vídeo").
argument-hint: <link> [audio] [mp3] [output folder or file]
---

# /tyler:download

Downloads video or audio with the Tyler CLI. Arguments received: `$ARGUMENTS`

Reply to the user in the language they wrote in. The CLI prints in Portuguese; translate what you report.

## Steps

1. Identify the link. If none was given, ask for it. If it is a playlist link, ask for a single video link.
2. Decide what to download from the request:
   - video (default) — mp4, ready for Tyler's other operations.
   - audio only (`--only-audio`) — m4a, no quality loss. Use `--audio-format mp3` only if the user asks for mp3.
3. Destination: if the user names a folder or file, pass it in `-o` (folders end with `/`). Otherwise the file goes to the current folder, named after the video title.
4. Run:

   ```bash
   uv run --project "${CLAUDE_PLUGIN_ROOT}" tyler download "<link>" [--only-audio] [--audio-format mp3] [-o "<output>"]
   ```

5. The last printed line is the path of the downloaded file. Tell the user. If `arquivo: já existia` appears, say nothing was downloaded again (Tyler never overwrites files).
6. If the download fails because of age restriction or login, explain that the video requires an account and can't be downloaded this way.
7. For a video, offer next steps: `/tyler:vertical` or `/tyler:blur` on the downloaded file.
