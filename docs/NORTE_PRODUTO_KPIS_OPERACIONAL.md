# Norte do Produto — Operacionalização de KPIs (`!dominio`)

Este documento transforma o Norte do Produto em rotina semanal de acompanhamento.

## Meta principal
Ter **1 entrada central** (`!dominio`) que permita jogar o núcleo inteiro sem decorar sintaxe.

## Resultado esperado
- redução de comandos públicos para 3–4;
- aumento de uso diário do painel;
- queda de erros por comando inválido;
- sensação de progresso mais clara por clique.

---

## KPIs oficiais (alvos)
1. **Adoção do painel:** ≥ 70% dos jogadores ativos usando `!dominio` como primeira ação da sessão.
2. **Erro de uso:** ≤ 15% de mensagens de erro por uso incorreto.
3. **Engajamento por sessão:** ≥ 2,5 ações por sessão iniciada no painel.
4. **Retenção:** aumento de D1/D7 após migração para clique-first.

---

## Eventos mínimos para instrumentação
- `panel_open` — quando `!dominio` é acionado.
- `panel_action` — clique em botão (`resgatar`, `treinar`, `construcoes`, `militar`, `operacoes`, `rank`).
- `panel_error` — requisito ausente/uso inválido.

Campos recomendados para cada evento:
- `user_id`
- `guild_id`
- `event_name`
- `event_action`
- `error_code` (quando houver)
- `created_at_ts`

---

## Rotina semanal (sexta-feira)
1. Exportar métricas da semana por servidor.
2. Comparar com metas oficiais.
3. Classificar status:
   - Verde: todos os KPIs batidos;
   - Amarelo: 1 KPI abaixo;
   - Vermelho: 2+ KPIs abaixo.
4. Definir ação da semana seguinte.

---

## Regras de decisão
- **2 semanas seguidas abaixo da meta**: simplificar painel (menos opções visíveis, mais CTA de próximo passo).
- **Erro de uso > 15%**: revisar textos de feedback e navegação dos botões.
- **Engajamento < 2,5**: reduzir cliques necessários para completar ciclo (resgatar → treinar → operação).

---

## Entregável de acompanhamento (template)
- Semana:
- Adoção do painel (%):
- Erro de uso (%):
- Engajamento por sessão:
- Retenção D1:
- Retenção D7:
- Status (Verde/Amarelo/Vermelho):
- Decisão aplicada:
- Hipótese para próxima semana:
