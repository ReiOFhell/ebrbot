# Reset de Estrutura — Núcleo C

Este projeto foi reiniciado para remover a estrutura antiga baseada em comandos legados (`!iniciar`, `!classe`, `!juramento` e afins).

## Estado atual
- `bot.py` foi reescrito em formato limpo com foco no loop jogável do Núcleo C.
- O fluxo foi simplificado para comandos centrais:
  - `!dominio`
  - `!coletar`
  - `!treinar`
  - `!melhorar <celeiros|casernas|forja>`
  - `!rank`
  - `!guia`
  - `!diagnostico`

## Banco de dados
- Novo banco dedicado: `data/nucleoc.db`.
- Nova tabela base: `domains`.

## Objetivo do reset
- Sair de um bot com muitos comandos narrativos e baixa jogabilidade.
- Entrar em um núcleo com progressão clara e competitiva, pronto para evoluir por fases.
