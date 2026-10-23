---
name: watermark
description: Coloca uma imagem (logo, marca d'água, selo) sobre um vídeo, em um canto ou no centro. Use quando o usuário pedir para colocar marca d'água, logo, logotipo ou assinatura visual em um vídeo.
argument-hint: <vídeo> <imagem> [posição] [tamanho%] [opacidade]
---

# /watermark

Aplica uma marca d'água usando a CLI do Tyler. Argumentos recebidos: `$ARGUMENTS`

## Como executar

1. Identifique o vídeo e a imagem. Se faltar algum, pergunte. Resolva `~` e caminhos relativos e confirme que os dois existem. PNG com fundo transparente dá o melhor resultado.
2. Escolha a posição a partir do pedido (padrão `bottom-right`): `top-left`, `top`, `top-right`, `left`, `center`, `right`, `bottom-left`, `bottom`, `bottom-right`. "Canto inferior direito" → `bottom-right`, "em cima no meio" → `top`.
3. Ajustes opcionais:
   - `--size` — largura da marca em % do lado menor do vídeo (padrão 20; "pequena" ≈ 10, "grande" ≈ 35).
   - `--opacity` — de 0.1 a 1 (padrão 1; "discreta"/"semitransparente" ≈ 0.5).
   - `--margin` — distância da borda em % (padrão 3).
4. Rode:

   ```bash
   uv run --project "$CLAUDE_PROJECT_DIR" tyler watermark "<vídeo>" "<imagem>" -p <posição> [--size N] [--opacity N] [-o "<saída>"]
   ```

5. A última linha impressa é o caminho do vídeo gerado; a linha `marca:` mostra o tamanho final da marca em pixels. Informe os dois ao usuário (o original nunca é alterado).
