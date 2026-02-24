# Roadmap de Implementação — Núcleo C (Feudos Imperiais)

Baseado em:
- `docs/BLUEPRINT_NUCLEO_C_FEUDOS.md`
- `docs/PACOTE_POS_OK_NUCLEO_C.md`

Objetivo deste documento: transformar o design aprovado em **execução incremental**, com marcos claros, critérios de pronto e ordem de implementação para chegar ao destino esperado sem retrabalho.

---

## 1) Meta final (definição de sucesso)

Você chegou ao destino quando o bot tiver:
1. Painel único `!dominio` com ações jogáveis em 1 tela.
2. Loop funcional completo: coletar → melhorar → treinar → incursão → achados → rank.
3. Progressão clara em 3 eixos: riqueza, poder, prestígio.
4. Operações com risco/recompensa e requisitos de composição.
5. Temporada ativa com ranking e recompensa de legado.

---

## 2) Estratégia de entrega (como não se perder)

### 2.1 Método
- Implementar por **fatias verticais** (cada fase já jogável).
- Evitar “big-bang” (reescrever tudo de uma vez).
- Cada fase fecha com métrica mínima + testes + release interno.

### 2.2 Ordem obrigatória
1. Fundação de dados + economia base.
2. Painel/UX e ações principais.
3. Exército e operações.
4. Achados/sub-lore.
5. Ranking/temporada.
6. Balanceamento fino + observabilidade.

---

## 3) Backlog por fases (passo a passo)

## Fase 0 — Preparação técnica (1–2 dias)

### Entregas
- Congelar estado atual do bot (tag/release interno).
- Criar branch de evolução do Núcleo C.
- Definir feature flags (ex.: `NUCLEO_C_ENABLED`).
- Criar plano de migração incremental do SQLite.

### Critério de pronto
- É possível ligar/desligar o Núcleo C sem quebrar comandos legados.

---

## Fase 1 — Fundação de dados e fórmulas (2–4 dias)

### 1.1 Schema mínimo novo
Criar tabelas (ou expandir) para:
- `domains` (estado do feudo por jogador)
- `domain_buildings` (celeiros/casernas/forja + tiers + timers)
- `resources` (ouro, manutenção acumulada, última coleta)
- `army` (tropas, doutrina, força calculada)
- `generals` e `strategists` (slots e vínculo)
- `operations` (catálogo + requisitos)
- `operation_runs` (execuções + resultado + perdas)
- `items` (catálogo)
- `inventories` (itens por jogador)
- `season_state` e `season_scores`

### 1.2 Regras econômicas base
Implementar fórmulas do pacote pós-OK:
- custo, produção e manutenção por tier;
- tempos de upgrade;
- overflow de coleta (>24h);
- manutenção militar por faixa.

### 1.3 Serviço de cálculo central
Criar módulo único de cálculo (sem duplicar fórmula em comandos).

### Critério de pronto
- Dado um jogador fake, o sistema calcula corretamente:
  - produção/h,
  - custo de upgrade,
  - manutenção,
  - saldo líquido por janela de tempo.

---

## Fase 2 — Painel `!dominio` e ações essenciais (3–5 dias)

### 2.1 Painel único
Implementar `!dominio` com blocos:
- Ouro atual e geração/h;
- estado dos 3 prédios;
- tropas e status de treino;
- exército ativo (doutrina/general/estrategista);
- atalhos de ação.

### 2.2 Ações básicas
Subcomandos/botões:
- `coletar`
- `melhorar <celeiros|casernas|forja>`
- `treinar`
- `rank` (resumo rápido)

### 2.3 Padrão de resposta UX
Toda resposta segue: Resultado + Variação + Próximo passo.

### Critério de pronto
- Um jogador novo consegue fazer o ciclo básico (coletar → melhorar → treinar) sem abrir guia externo.

---

## Fase 3 — Exército modular e composição (2–4 dias)

### 3.1 Núcleo militar
- tropa (massa)
- doutrina (cerco/choque/furtivo/arcano)
- slot de general
- slot de estrategista
- cálculo de poder do feudo

### 3.2 Regras de desbloqueio
- estrategista só entra após gate mínimo (tier/recurso/operação).
- sem composição mínima, operação retorna erro claro de requisito.

### Critério de pronto
- Mudança de doutrina e slots altera poder calculado e resultado esperado em operação simulada.

---

## Fase 4 — Operações com risco/recompensa (3–5 dias)

### 4.1 Primeiro lote (MVP)
Implementar 3 operações iniciais:
1. Tumba do Sultão da Caravana
2. Ruínas da Muralha Viva
3. Estrada das Sete Cinzas

### 4.2 Motor de operação
Para cada run:
- valida requisito;
- calcula chance de sucesso/falha;
- aplica perdas de tropas;
- distribui recompensa base;
- registra no histórico.

### 4.3 Regras de justiça
- cap diário de operações de alto risco;
- proteção de novato;
- derrota nunca zera conta.

### Critério de pronto
- Operações geram outcomes consistentes (vitória/falha parcial/falha) com impacto numérico rastreável.

---

## Fase 5 — Achados, raridade e sub-lore (3–5 dias)

### 5.1 Catálogo canônico inicial
Cadastrar os 30 itens do pacote:
- 12 fragmentos
- 12 relíquias
- 6 entidades/artefatos

### 5.2 Pipeline de drop
- fonte: forja + operações;
- pesos por raridade;
- modificadores por tier/qualidade;
- registro nos Anais.

### 5.3 Lore emergente
- descoberta gera mensagem dramática curta;
- item entra no inventário;
- desbloqueio opcional de operação/rota quando aplicável.

### Critério de pronto
- Jogador recebe drops comuns com frequência saudável e drops raros com baixa frequência sem parecer “nunca acontece”.

---

## Fase 6 — Rank triplo e temporada (3–4 dias)

### 6.1 Rankings
Implementar e publicar:
- Magnatas (riqueza)
- Senhores de Guerra (poder)
- Lendas dos Anais (prestígio)

### 6.2 Temporada
- duração 30 dias;
- soft reset de prestígio;
- recompensas de legado;
- painel de tempo restante e meta pessoal.

### 6.3 Encerramento de temporada
Job administrativo:
- congela ranking final;
- distribui recompensas;
- reinicia estado sazonal.

### Critério de pronto
- Temporada encerra e reinicia sem apagar progresso estrutural indevido.

---

## Fase 7 — Balanceamento, anti-exploit e observabilidade (contínuo)

### 7.1 Anti-exploit
- idempotência em coleta/treino;
- lock transacional em operações;
- limites de spam por usuário;
- validações de estado em cada ação.

### 7.2 Telemetria mínima
Registrar:
- comandos por usuário/dia;
- taxa de progressão por tier;
- distribuição de riqueza;
- taxa de sucesso por operação;
- taxa de drop por raridade.

### 7.3 Ajustes quinzenais
- custo/produção,
- perdas militares,
- chance de drop,
- recompensas de prestígio.

### Critério de pronto
- Economia estável por 2 semanas sem inflação explosiva nem estagnação total.

---

## 4) Sequência de PRs recomendada (prática)

1. **PR-01**: schema + migrações + serviço de cálculo.
2. **PR-02**: `!dominio` + coletar + melhorar + treinar.
3. **PR-03**: exército modular (doutrina/general/estrategista).
4. **PR-04**: 3 operações MVP + justiça competitiva.
5. **PR-05**: sistema de achados + inventário + Anais.
6. **PR-06**: rank triplo + temporada + premiação.
7. **PR-07**: anti-exploit + métricas + tuning inicial.

Regra: PR pequeno, testável e jogável isoladamente.

---

## 5) Plano de testes por fase

## 5.1 Testes unitários
- fórmulas de custo/produção/manutenção;
- cálculo de poder por composição;
- algoritmo de drop por raridade (distribuição esperada);
- validações de requisito de operação.

## 5.2 Testes de integração
- fluxo completo do jogador novo (dia 1);
- upgrade com timer;
- operação com sucesso/falha;
- encerramento e reinício de temporada.

## 5.3 Testes de carga (mínimo)
- bursts de `coletar` e `treinar`;
- concorrência em operação popular;
- leitura de rank com muitos jogadores.

---

## 6) Riscos reais e mitigação

1. **Risco: inflação precoce de ouro**  
Mitigar com manutenção e taxação progressiva.

2. **Risco: frustração por raridade impossível**  
Mitigar com pity leve oculto por atividade útil (sem expor fórmula).

3. **Risco: operação punitiva demais**  
Mitigar com derrota parcial e recuperação assistida.

4. **Risco: painel virar poluído**  
Mitigar com layout fixo de 5 blocos e ações curtas.

5. **Risco: novatos inalcançáveis no rank**  
Mitigar com temporada + recompensas por bracket.

---

## 7) Métricas de produto para validar destino

Acompanhar semanalmente:
- D1, D3, D7 retention;
- % de usuários que usam `!dominio` 3+ vezes/dia;
- % que chega em T3 até dia 7;
- % que participa de ao menos 1 operação/dia;
- distribuição Top 1% vs mediana em riqueza/poder;
- taxa de retorno após derrota em operação.

Se duas semanas seguidas piorarem, simplificar loop antes de adicionar conteúdo.

---

## 8) Definição de “pronto para produção”

Liberar geral apenas quando:
1. Fases 1–6 concluídas;
2. falhas críticas de economia = 0 por 7 dias;
3. abuso/exploit sem bloqueios conhecidos;
4. mensagens UX sem ambiguidade em todas ações;
5. rank/temporada operando fim a fim.

---

## 9) Próximo passo imediato (ação já)

Ordem prática das próximas 72h:
1. Abrir PR-01 (schema + cálculo) com fixtures.
2. Em paralelo, desenhar payload JSON de resposta do `!dominio`.
3. Definir 10 cenários de teste de progressão (dia 1 ao dia 7).
4. Travar nomes canônicos de tabelas/campos para evitar churn.

Com isso, o time sai de “ideia” para “execução objetiva” no mesmo ciclo.
