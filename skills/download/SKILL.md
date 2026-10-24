---
name: download
description: Baixa um vídeo (mp4) ou só o áudio (m4a/mp3) do YouTube e de outros sites (Instagram, TikTok, Vimeo...). Use quando o usuário pedir para baixar, salvar ou pegar um vídeo ou áudio a partir de um link.
argument-hint: <link> [áudio] [mp3] [pasta ou arquivo de saída]
---

# /tyler:download

Baixa vídeo ou áudio usando a CLI do Tyler. Argumentos recebidos: `$ARGUMENTS`

## Como executar

1. Identifique o link. Se nenhum foi informado, pergunte qual é. Se for link de playlist, peça o link de um vídeo só.
2. Decida o que baixar a partir do pedido:
   - vídeo (padrão) — mp4, pronto para as outras operações do Tyler.
   - só o áudio (`--only-audio`) — m4a, sem perder qualidade. Use `--audio-format mp3` só se o usuário pedir mp3.
3. Destino: se o usuário indicar uma pasta ou arquivo, passe em `-o` (pasta terminada em `/`). Sem isso, o arquivo vai para a pasta atual com o título do vídeo.
4. Rode:

   ```bash
   uv run --project "${CLAUDE_PLUGIN_ROOT}" tyler download "<link>" [--only-audio] [--audio-format mp3] [-o "<saída>"]
   ```

5. A última linha impressa é o caminho do arquivo baixado. Informe ao usuário. Se aparecer `arquivo: já existia`, avise que nada foi baixado de novo (o Tyler nunca sobrescreve).
6. Se o download falhar por restrição de idade ou login, explique que o vídeo exige uma conta e não pode ser baixado assim.
7. Se for vídeo, ofereça os próximos passos: `/tyler:vertical` ou `/tyler:blur` sobre o arquivo baixado.
