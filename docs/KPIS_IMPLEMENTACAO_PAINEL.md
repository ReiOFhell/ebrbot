# Implementação de Instrumentação de KPIs do Painel

Implementado no `bot.py`:

- Tabela `panel_events` para telemetria de painel.
- Eventos registrados:
  - `panel_open` ao executar `!dominio`.
  - `panel_action` para botões (`resgatar`, `treinar`, `construcoes`, `militar`, `operacoes`, `rank`).
  - `panel_error` para erro de uso no painel (ex.: interação de usuário não-dono).
- Índices para leitura operacional (`idx_panel_events_user`, `idx_panel_events_name`).
- Comando admin `!painel_kpis` com consolidação de 7 dias:
  - % de usuários que usam `!dominio` ao menos 3x/dia;
  - adoção do painel;
  - taxa de erro;
  - taxa de erro por requisito ausente;
  - ações por sessão;
  - tempo médio entre abrir painel e concluir 1 ação;
  - retenção D1/D7;
  - distribuição de cliques por botão.

Isso atende o Norte do Produto orientado a dados e viabiliza acompanhamento semanal.
