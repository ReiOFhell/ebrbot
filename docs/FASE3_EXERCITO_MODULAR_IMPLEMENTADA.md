# Fase 3 — Exército modular e composição (implementada)

## Núcleo militar
Implementado com:
- tropa (massa) em `army.troops`
- doutrina (`cerco`, `choque`, `furtivo`, `arcano`) em `army.doctrine`
- slot de general em `army.general_id`
- slot de estrategista em `army.strategist_id`
- cálculo de poder do feudo centralizado em `core/economy.py`

## Regras de desbloqueio
Para equipar/recrutar estrategista:
- Casernas T3+
- mínimo de 200.000 ouro
- ao menos 1 operação registrada

Sem requisitos, o comando retorna erro claro de requisito.

## Comandos adicionados
- `!doutrina <cerco|choque|furtivo|arcano>`
- `!recrutar_general <nome>`
- `!equipar_general <id>`
- `!recrutar_estrategista <nome>`
- `!equipar_estrategista <id>`
- `!simular_operacao <tumba_sultao|ruinas_muralha|estrada_cinzas>`

## Critério de pronto
Mudança de doutrina e de slots altera `power` e impacta o resultado esperado da simulação (`!simular_operacao`).
