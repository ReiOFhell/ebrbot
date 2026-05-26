# Fase 0 — Preparação Técnica do Núcleo C

Objetivo: cumprir os pré-requisitos da Fase 0 do roadmap para iniciar a implementação do Núcleo C sem quebrar comandos legados.

## 1) Congelamento do estado atual
- Tag interna criada: `nucleo-c-freeze-v1`.
- Uso recomendado:
  - rollback rápido se alguma migração falhar;
  - referência de comparação entre legado e Núcleo C.

## 2) Branch de evolução
- Branch recomendada para execução contínua: `feature/nucleo-c`.
- Estratégia:
  - PRs pequenos (PR-01..PR-07);
  - merge só com testes e checklist de fase completos.

## 3) Feature flag oficial
- Nome: `NUCLEO_C_ENABLED`
- Tipo: variável de ambiente booleana.
- Valor padrão: `False` (seguro para legado).

Valores aceitos como `true`:
- `1`, `true`, `yes`, `on`, `sim`.

## 4) Plano de migração incremental SQLite

## 4.1 Princípios
1. Nunca remover tabela legada em migração inicial.
2. Só adicionar novas tabelas/colunas (forward-only) nas primeiras fases.
3. Migração idempotente (rodar mais de uma vez sem quebrar).
4. Cada mudança de schema com versão explícita e checkpoint.

## 4.2 Ordem de migração (PR-01)
1. Criar tabela de controle de migração (`schema_migrations`).
2. Criar tabelas do Núcleo C sem alterar fluxo legado:
   - `domains`, `domain_buildings`, `resources`, `army`, `operations`, `operation_runs`, `items`, `inventories`, `season_state`, `season_scores`.
3. Inserir seeds mínimos (operações básicas e itens canônicos iniciais).
4. Adicionar índices de leitura crítica (`user_id`, `season_id`, `operation_id`).

## 4.3 Estratégia de compatibilidade
- Com `NUCLEO_C_ENABLED=False`:
  - somente comandos legados executam fluxo completo;
  - tabelas novas podem existir, mas não são usadas no gameplay.
- Com `NUCLEO_C_ENABLED=True`:
  - ativar gradualmente rotas do `!dominio` e módulos novos.

## 5) Critério de pronto da Fase 0
A Fase 0 só está concluída quando:
1. `NUCLEO_C_ENABLED=False` mantém comportamento legado sem regressão.
2. `!diagnostico` exibe estado da flag.
3. Log de inicialização mostra flags ativas.
4. Existe tag de congelamento para rollback rápido.
5. Plano de migração incremental está documentado e aprovado.

## 6) Checklist operacional (curto)
- [x] Criar tag de congelamento (`nucleo-c-freeze-v1`).
- [x] Introduzir feature flag com default seguro.
- [x] Expor flag em diagnóstico e logs de startup.
- [x] Documentar plano de migração incremental.
- [ ] Criar branch dedicada `feature/nucleo-c` (processo de equipe).
