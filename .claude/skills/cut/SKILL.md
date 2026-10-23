---
name: cut
description: Corta um trecho de um vídeo entre dois tempos (minutagem). Use quando o usuário pedir para cortar, recortar, aparar, extrair um trecho ou pegar "do minuto X ao Y" de um vídeo.
argument-hint: <vídeo> <início> [fim]
---

# /cut

Corta um trecho do vídeo usando a CLI do Tyler. Argumentos recebidos: `$ARGUMENTS`

## Como executar

1. Identifique o vídeo de entrada. Se nenhum foi informado, pergunte qual é. Resolva `~` e caminhos relativos; confirme que o arquivo existe.
2. Identifique o início e o fim. Formatos aceitos: segundos (`90`), `MM:SS` (`1:30`) ou `HH:MM:SS` (`1:02:03`), com fração opcional (`1:30.5`).
   - "do 1:30 até o fim" → só o início.
   - "os primeiros 30 segundos" → início `0`, fim `30`.
   - "2 minutos a partir de 1:00" → calcule o fim (`3:00`).
3. Por padrão o corte é exato (recodifica). Use `--copy` só se o usuário pedir rapidez ou "sem perder qualidade" e aceitar que o início pode adiantar alguns segundos (cai no quadro-chave anterior).
4. Rode:

   ```bash
   uv run --project "$CLAUDE_PROJECT_DIR" tyler cut "<vídeo>" <início> [fim] [--copy] [-o "<saída>"]
   ```

5. A última linha impressa é o caminho do vídeo gerado; a linha `trecho:` diz a duração do corte. Informe os dois ao usuário (o original nunca é alterado).
