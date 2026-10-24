---
name: blur
description: Anonimiza um vídeo borrando automaticamente rostos e/ou placas de veículos. Use quando o usuário pedir para borrar, desfocar, censurar, esconder ou anonimizar rostos, pessoas, placas ou carros em um vídeo.
argument-hint: <vídeo> [all|faces|plates] [blur|pixel|black]
---

# /tyler:blur

Borra rostos e placas usando a CLI do Tyler. Argumentos recebidos: `$ARGUMENTS`

## Como executar

1. Identifique o vídeo de entrada. Se nenhum foi informado, pergunte qual é. Resolva `~` e caminhos relativos; confirme que o arquivo existe.
2. Escolha o alvo a partir do pedido (padrão `all`):
   - `all` — rostos e placas
   - `faces` — só rostos
   - `plates` — só placas
3. Escolha o estilo (padrão `blur`):
   - `blur` — desfoque
   - `pixel` — mosaico/pixelado
   - `black` — tarja preta
4. Rode (leva cerca de 2x a duração do vídeo; use timeout alto ou rode em segundo plano para vídeos longos):

   ```bash
   uv run --project "${CLAUDE_PLUGIN_ROOT}" tyler blur "<vídeo>" --targets <alvo> --style <estilo> [-o "<saída>"]
   ```

5. A última linha impressa é o caminho do vídeo gerado; a anterior diz em quantos quadros algo foi encontrado. Informe os dois ao usuário (o original nunca é alterado).
6. Lembre o usuário de assistir ao resultado antes de publicar: a detecção é automática e pode deixar escapar rostos de perfil, muito pequenos ou parcialmente cobertos.
