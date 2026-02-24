# Implementação de Instrumentação de KPIs do Painel

Implementado no `bot.py`:

- Tabela `panel_events` para telemetria de painel.
- Eventos registrados:
  - `panel_open` ao executar `!dominio`.
  - `panel_action` para botões (`resgatar`, `treinar`, `construcoes`, `militar`, `operacoes`, `rank`).
  - `panel_error` para erro de uso no painel (ex.: interação de usuário não-dono).
- Índices para leitura operacional (`idx_panel_events_user`, `idx_panel_events_name`).
- Comando admin `!painel_kpis` com consolidação de 7 dias:
  - adoção do painel;
  - taxa de erro;
  - ações por sessão;
  - distribuição de cliques por botão.

Isso atende o Norte do Produto orientado a dados e viabiliza acompanhamento semanal.
