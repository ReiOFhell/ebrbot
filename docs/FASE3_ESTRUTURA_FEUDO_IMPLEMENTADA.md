# Fase 3 — Estrutura de Feudo (3 prédios oficiais)

Implementação aplicada no núcleo do bot com foco em clareza:

## 3.1 Celeiros de Guerra (Economia)
- Gera ouro ao longo do tempo via `!coletar`.
- Escala por tier com `!melhorar celeiros` (T1 até T10).

## 3.2 Casernas Imperiais (Militar)
- Gera tropas por ciclo via `!treinar`.
- Escala por tier com `!melhorar casernas` (T1 até T10).

## 3.3 Forja Relicária (Equipamento/Achados)
- Gera chance de achados via `!forjar`.
- Aumenta ganho de incursão e chance de achado em simulação.
- Escala por tier com `!melhorar forja` (T1 até T10).

## Dependências implementadas
- Sem ouro: progresso trava em upgrades e forja.
- Sem tropas: não há incursão (`!simular_operacao` bloqueia).
- Sem forja: crescimento segue comum (menos bônus e menos achados).

## Observações técnicas
- Limite de edifícios em T10 aplicado no comando `!melhorar`.
- `!dominio` mostra o estado das 3 estruturas e do núcleo militar.
