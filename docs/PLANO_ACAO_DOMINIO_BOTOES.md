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
