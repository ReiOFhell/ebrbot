# Fase 1 — Fundação de dados e fórmulas (implementada)

## Schema mínimo criado
Tabelas criadas em `init_db()`:
- `domains`
- `domain_buildings`
- `resources`
- `army`
- `generals`
- `strategists`
- `operations`
- `operation_runs`
- `items`
- `inventories`
- `season_state`
- `season_scores`

## Serviço central de cálculo
As fórmulas foram centralizadas em `core/economy.py`:
- custo de upgrade por tier
- produção por tier
- manutenção de estruturas por tier
- manutenção militar por faixa de tropas
- cap de coleta (overflow 24h)
- tempo de upgrade por tier alvo
- saldo líquido por janela de tempo

## Critério de pronto validável
O comando admin `!economia_teste` calcula para jogador fake:
- produção/h
- manutenção (edifícios, militar, total)
- custo de upgrade
- saldo líquido em janela de tempo (6h)
