---
name: vertical
description: Converte um vídeo horizontal para vertical (9:16, Reels/TikTok/Shorts), seguindo os rostos automaticamente. Use quando o usuário pedir para deixar um vídeo vertical, em pé, 9:16, para stories/reels/tiktok/shorts.
argument-hint: <vídeo> [auto|center|fit] [LARGURAxALTURA]
---

# /vertical

Converte o vídeo para vertical usando a CLI do Tyler. Argumentos recebidos: `$ARGUMENTS`

## Como executar

1. Identifique o vídeo de entrada. Se nenhum foi informado, pergunte qual é. Se o caminho tiver `~` ou for relativo, resolva-o; confirme que o arquivo existe.
2. Escolha o modo a partir do pedido (padrão `auto`):
   - `auto` — recorta 9:16 seguindo os rostos (pessoas falando, entrevistas, vlogs).
   - `center` — recorte fixo no centro (assunto sempre no meio, sem pessoas).
   - `fit` — mostra o quadro inteiro com fundo desfocado (paisagens, telas, quando nada pode ser cortado).
3. Rode a partir da raiz deste projeto (pode levar alguns minutos em vídeos longos; use timeout alto):

   ```bash
   uv run --project "$CLAUDE_PROJECT_DIR" tyler vertical "<vídeo>" --mode <modo> [--size 1080x1920] [-o "<saída>"]
   ```

4. A última linha impressa é o caminho do vídeo gerado. Informe-o ao usuário (o original nunca é alterado).
5. Se falhar, mostre o erro e sugira o modo `fit` ou `center` como alternativa quando o problema for a detecção de rostos.
