# Tyler

Editor de vídeo comandado por IA. Veja a arquitetura no README.md.

## Regras

- Toda lógica de vídeo fica em `src/tyler/ops/` (um módulo por operação) e é exposta como subcomando da CLI `tyler`.
- Skills em `skills/` (o repositório é um plugin do Claude Code) só orquestram: chamam `uv run --project "${CLAUDE_PLUGIN_ROOT}" tyler <comando>`, nunca reimplementam lógica.
- Operações nunca imprimem direto: recebem um `Reporter` (`src/tyler/report.py`) e reportam etapas (`reporter.step`), estatísticas e prévias (função que devolve o quadro com as detecções desenhadas).
- Use ffmpeg para codificação/decodificação; preserve o áudio original sempre que possível.
- Nunca sobrescreva o vídeo de entrada: a saída padrão é `<nome>_tyler_<operacao>.<ext>` ao lado do original.
- Python 3.12 gerenciado com `uv` (o Python 3.14 do sistema ainda não é suportado por várias libs de IA).
- Textos para o usuário, mensagens da CLI e documentação em português.
