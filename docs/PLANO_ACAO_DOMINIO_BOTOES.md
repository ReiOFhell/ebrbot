# Plano de Ação — Centralização em `!dominio` com Botões

Objetivo: transformar a proposta de UX em execução prática, com entregas pequenas e jogáveis.

---

## 1) Norte do produto (o que vamos perseguir)

### Meta principal
Ter **1 entrada central** (`!dominio`) que permita jogar o núcleo inteiro sem decorar sintaxe.

### Resultado esperado
- redução de comandos públicos para 3–4;
- aumento de uso diário do painel;
- queda de erros por comando inválido;
- sensação de progresso mais clara por clique.

### Indicadores de sucesso (Norte do produto)
- ≥ 70% dos jogadores ativos usando `!dominio` como entrada principal.
- ≤ 15% de mensagens de erro por uso incorreto de comando.
- ≥ 2,5 ações médias por sessão de painel.
- aumento de retenção D1/D7 após migração para clique-first.



## 1.1 Quadro executivo do Norte (para acompanhamento semanal)

### Meta operacional
- `!dominio` deve ser a porta de entrada padrão do jogo.

### KPIs-alvo
- **Adoção do painel:** ≥ 70% dos jogadores ativos usando `!dominio` como primeira ação da sessão.
- **Erro de uso:** ≤ 15% de mensagens de erro por comando inválido/uso incorreto.
- **Engajamento por sessão:** ≥ 2,5 ações médias por sessão iniciada no painel.
- **Retenção:** crescimento de D1/D7 após migração para fluxo clique-first.

### Instrumentação mínima
- Registrar evento `panel_open` ao usar `!dominio`.
- Registrar evento `panel_action` por botão (`resgatar`, `treinar`, `construcoes`, `militar`, `operacoes`, `rank`).
- Registrar evento `panel_error` com código de requisito ausente.
- Consolidar relatórios semanais por usuário ativo e por botão.

### Critério de decisão
- Se 2 semanas seguidas ficarem abaixo dos KPIs, simplificar fluxo e reduzir profundidade visível do painel antes de adicionar novas mecânicas.


---

## 2) Escopo funcional do painel

## 2.1 Painel raiz (`!dominio`)
Mostrar em uma tela:
- ouro atual / ouro resgatável;
- tropas / poder;
- níveis de Celeiros, Casernas, Forja;
- status de doutrina e slots (general/estrategista);
- ações rápidas (botões).

## 2.2 Botões da primeira versão
1. Resgatar
2. Treinar
3. Construções
4. Militar
5. Operações
6. Rank

## 2.3 Regras de UX obrigatórias
Cada clique responde com:
1. resultado;
2. variação de recursos;
3. próximo clique sugerido.

---



## 3.1 Progressão em 3 eixos (poder evidente entre X e Y)

### 3.1 Riqueza (Ouro)
- Escala longa: milhões → bilhões → trilhões.
- Função: upgrades, manutenção militar e mercado.
- Medida principal: `resources.gold` + patrimônio de progressão.

### 3.2 Poder (Força do Feudo)
- Fórmula conceitual: Tropas + Qualidade de General + Equipamento de Legião + bônus de doutrina.
- Função: capacidade real de vitória em operações.
- Medida principal: `army.power` (composição + doutrina + slots).

### 3.3 Prestígio (Legado)
- Pontuação de temporada (não substitui ouro).
- Função: títulos, visibilidade e marca nos Anais.
- Medida principal: ranking sazonal em `season_scores`.

### Resultado de design (ambição múltipla)
- Jogador A pode liderar em riqueza;
- Jogador B pode liderar em poder militar;
- Jogador C pode liderar em prestígio.

Isso evita meta única e aumenta disputa saudável.

## 3) Backlog por etapas (execução)

## Etapa A — Base interativa sem mudar lógica (2–3 dias)

### Entregas
- criar `DominioView` com botões principais;
- botão **Resgatar** chama fluxo de `coletar`;
- botão **Treinar** chama fluxo de `treinar`;
- botão **Rank** chama fluxo de `rank`.

### Critério de pronto
- jogador consegue usar `!dominio` e executar resgatar/treinar/rank sem comando textual adicional.

---

## Etapa B — Subviews de Construções e Militar (3–4 dias)

### Entregas
- **ConstruçõesView** (Celeiros/Casernas/Forja + Melhorar);
- **MilitarView** (doutrina, equipar general, equipar estrategista);
- respostas ephemerais para detalhes de estado individual;
- validações e mensagens de requisito no próprio botão.

### Critério de pronto
- upgrades e composição militar funcionam integralmente via botões.

---

## Etapa C — Operações por painel (3–4 dias)

### Entregas
- **OperaçõesView** listando operações por desbloqueio;
- botão de simulação por operação;
- exibição de bloqueios com motivo claro;
- persistência de run confirmada em `operation_runs`.

### Critério de pronto
- jogador consegue descobrir operações disponíveis e simular sem sair do painel.

---

## Etapa D — Redução real de comandos públicos (1–2 dias)

### Entregas
- manter públicos: `!dominio`, `!rank`, `!guia`;
- comandos antigos viram aliases internos/ocultos;
- atualizar ajuda para orientar clique-first.

### Critério de pronto
- onboarding completo com 1 comando principal.

---

## 4) Arquitetura sugerida (simples)

## 4.1 Camadas
- **core/economy.py**: fórmulas e cálculo;
- **services/gameplay.py**: regras de ação (resgatar/treinar/melhorar/operar);
- **ui/views.py**: botões e telas;
- **bot.py**: roteamento de comandos e bootstrap.

## 4.2 Benefício
Evita duplicar regra em callback de botão e em comando textual.

---

## 5) Métricas de validação

Acompanhar por semana:
- % de usuários que usam `!dominio` ao menos 3x/dia;
- taxa de cliques por botão (Resgatar, Treinar, Operações...);
- taxa de erro por requisito ausente;
- tempo médio entre abrir painel e concluir 1 ação;
- retenção D1/D7.

---

## 6) Riscos e mitigação

1. **View expira rápido**
   - Mitigar com botão “Reabrir Painel”.

2. **Spam de clique**
   - Cooldown leve por ação + lock por usuário/ação.

3. **Painel ficar lotado**
   - Máximo 6 botões por tela + subviews.

4. **Regra divergir entre botão e comando**
   - Centralizar lógica em serviços únicos.

---

## 7) Checklist de pronto (go-live)

- [ ] `!dominio` executa 80% das ações comuns.
- [ ] Mensagens com resultado + variação + próximo passo.
- [ ] Bloqueios com motivo claro em todas as ações.
- [ ] `operation_runs` sendo populada pelos fluxos de operação.
- [ ] `!guia` atualizado para UX por botões.

---

## 8) Próxima ação imediata (agora)

1. Abrir PR da **Etapa A** só com `DominioView` e 3 botões (Resgatar/Treinar/Rank).
2. Medir estabilidade por 24h em servidor de teste.
3. Em seguida, Etapa B (Construções/Militar) em PR separado.

Esse plano mantém risco baixo e entrega valor jogável a cada merge.
