# Tyler

Editor de vídeo comandado por IA. Veja a arquitetura no README.md.

## Regras

- Toda lógica de vídeo fica em `src/tyler/ops/` (um módulo por operação) e é exposta como subcomando da CLI `tyler`.
- Skills em `skills/` (o repositório é um plugin do Claude Code) só orquestram: chamam `uv run --project "${CLAUDE_PLUGIN_ROOT}" tyler <comando>`, nunca reimplementam lógica.
- Operações nunca imprimem direto: recebem um `Reporter` (`src/tyler/report.py`) e reportam etapas (`reporter.step`), estatísticas e prévias (função que devolve o quadro com as detecções desenhadas).
- Use ffmpeg para codificação/decodificação; preserve o áudio original sempre que possível.
- Nunca sobrescreva o vídeo de entrada: a saída padrão é `<nome>_tyler_<operacao>.<ext>` ao lado do original.
- Python 3.12 gerenciado com `uv` (o Python 3.14 do sistema ainda não é suportado por várias libs de IA).
- Idiomas: skills (`skills/`), manifestos (`.claude-plugin/`) e `README.md` em inglês, para quem instala o plugin; as skills mandam o Claude responder no idioma do usuário. Mensagens da CLI, comentários e `README.pt-BR.md` em português. Ao mudar o README, atualize as duas versões. Se mudar um rótulo que a CLI imprime (ex.: `trecho:`), atualize as skills que o citam.
