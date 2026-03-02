# Proposta de Reformulação — EBR Bot (foco em jogabilidade, clareza e competição)

## Diagnóstico direto (o problema real)
Hoje o bot tem **lore forte** e muitos comandos, mas falta um **loop central visível**. Para o jogador comum:
- ele executa comandos, recebe texto, mas não entende claramente "o que ganho com isso";
- não há um caminho óbvio de evolução (curto, médio e longo prazo);
- não existe uma régua pública e simples que torne poder/riqueza/status comparáveis entre jogadores.

Em resumo: existe conteúdo, mas falta **economia + progressão + ranking + consequência** funcionando como um sistema único.

---

## Objetivo da reformulação
Transformar o bot em um jogo com:
1. **Progressão evidente** (novato → elite);
2. **Diferença real de poder entre X e Y** (riqueza, produção, influência, PvP/social);
3. **Poucos comandos, cada um com propósito claro**;
4. **Decisões estratégicas com trade-offs** (tempo, risco, especialização);
5. **Competição recorrente** (rank semanal/mensal e temporada).

---

## Princípio mestre: 1 loop principal + 2 loops secundários

### Loop principal (obrigatório)
**Produzir → Investir → Escalar → Competir → Reinvestir**

Esse loop será o “motor” do bot. Tudo que não alimentar esse ciclo perde prioridade.

### Loops secundários
1. **Político/Faccional:** alianças, guerras frias, bônus coletivos;
2. **Narrativo/Lore:** eventos e decisões com impacto mecânico (não só texto).

---

## Novo núcleo de jogo (simples, forte e legível)

### 1) Recursos base (claridade absoluta)
Use no máximo 5 moedas/recursos:
- **Comida** (sustenta população/trabalhadores)
- **Créditos** (dinheiro principal)
- **Energia Arcana** (habilidades/ações especiais)
- **Influência** (poder político/faccional)
- **Prestígio** (pontos de ranking de temporada)

Se tudo vira dezenas de atributos, o jogador se perde. Aqui cada recurso tem função única.

### 2) Estrutura de domínio (inspirado no exemplo da cidade)
Cada jogador possui um **Domínio** com slots de construção:
- **Fazenda** → gera Comida;
- **Moradia** → aumenta População;
- **Oficina/Empresa** → converte População + Comida em Créditos;
- **Santuário** → gera Energia Arcana;
- **Quartel** → permite ações competitivas (raides/sabotagem/defesa).

#### Dependências claras (efeito dominó)
- sem Comida: Moradia degrada;
- sem População ativa: Empresa perde eficiência;
- sem manutenção: produção cai por etapas.

Isso cria planejamento real e sensação de “cidade viva”.

### 3) Progressão por tiers
Cada prédio e trilha tem 5 tiers (T1 a T5):
- T1/T2: onboarding;
- T3: começa competição séria;
- T4/T5: elite do servidor.

O jogador entende fácil: “estou T2, quero T3”.

### 4) Especializações (builds)
Em vez de muitos comandos soltos, o jogador escolhe **1 arquétipo econômico**:
- **Mercador** (mais lucro em vendas);
- **Senescal** (melhor estabilidade/manutenção);
- **Arcanista** (mais energia e ações especiais);
- **Comandante** (vantagem em confronto).

Classe/lore continuam, mas agora com impacto econômico/competitivo real.

---

## Competitividade: tornar poder visível

### Ranking público em 3 eixos
- **Riqueza** (Créditos + ativos);
- **Poder** (capacidade ofensiva/defensiva);
- **Prestígio** (pontuação de temporada).

Comando único: `!rank` com abas/páginas.

### Temporadas (30 dias)
- reset parcial (soft reset de prestígio, preserva legado cosmético e marcos);
- recompensas exclusivas (título, cargo, emblema, bônus inicial na próxima temporada).

Sem temporada, jogo estagna e os líderes viram inalcançáveis.

### Conflito controlado (competitivo, não tóxico)
- ações limitadas por energia/tempo;
- defesa passiva para offline;
- janelas de ataque e proteção para novatos.

---

## Redesign de comandos (menos comandos, mais valor)

## Comandos essenciais (núcleo)
- `!start` → cria domínio e tutorial de 3 passos;
- `!painel` → visão consolidada: recursos, produção/h, riscos, próximos objetivos;
- `!construir <tipo>` → expande infraestrutura;
- `!upgrade <estrutura>` → melhora tier;
- `!coletar` → coleta produção acumulada;
- `!mercado` → compra/venda e itens aceleradores;
- `!acoes` → lista ações estratégicas disponíveis hoje;
- `!rank` → ranking claro e competitivo;
- `!temporada` → tempo restante, metas e recompensas.

### Comandos de lore/política (integrados ao sistema)
- `!conselho` e `!decreto` viram **modificadores globais reais** (ex.: +10% produção agrícola por 24h).
- `!intriga` vira ação com custo/risco/recompensa (não só registro textual).

### Mapeamento dos comandos atuais
Boa parte dos comandos atuais pode virar:
- alias para `!painel`;
- subcomandos de um comando pai;
- ou funcionalidades absorvidas no painel de domínio.

Regra: comando novo só entra se gerar decisão de jogo mensurável.

---

## Itens e aceleração (efeito “bot de fazenda”)
Adicionar itens fáceis de entender:
- **Fertilizante**: acelera produção da fazenda por X horas;
- **Autômato/Trator**: bônus permanente de eficiência;
- **Contrato de Mão de Obra**: recuperação rápida de população ativa;
- **Selo Arcano**: reduz cooldown de ações.

Itens criam economia e meta de investimento sem complexidade excessiva.

---

## UX que resolve a sensação de “comando vazio”

### Todo comando deve responder com:
1. **O que aconteceu**;
2. **Quanto mudou** (+/- recurso);
3. **Qual próximo passo recomendado**.

Exemplo de saída ideal:
> Fazenda T2 coletada: +120 Comida, +8 Prestígio.  
> Consumo atual: 90/dia. Superávit: +30/dia.  
> Próximo passo: `!upgrade moradia` (custo 300 Créditos).

Sem esse padrão, o jogador sente que “nada aconteceu”.

---

## Proposta de implementação (sem reescrever tudo de uma vez)

### Fase 1 — Vertical Slice (7–10 dias)
- painéis consolidados;
- sistema de recursos base;
- 3 estruturas (Fazenda, Moradia, Empresa);
- `!start`, `!painel`, `!coletar`, `!construir`, `!upgrade`, `!rank`.

### Fase 2 — Competição (7 dias)
- temporada;
- prestígio;
- objetivos diários/semanais;
- bônus faccionais com impacto real.

### Fase 3 — Profundidade (10+ dias)
- itens aceleradores;
- intriga estratégica com risco/recompensa;
- balanceamento de economia e anti-exploit.

---

## Métricas de sucesso (para saber se ficou “bom de jogar”)
- **D1/D7 retention** (volta no dia 1 e dia 7);
- **Comandos por usuário/dia** (uso real, não cadastro); 
- **Taxa de progressão** (quantos chegam T2/T3);
- **Distribuição de riqueza** (evitar concentração impossível);
- **Participação em temporada** (% jogadores ativos no ranking).

Se métricas não subirem, simplificar mais ainda.

---

## Decisões de design que recomendo aprovar agora
1. Adotar **economia de 5 recursos** como padrão oficial.
2. Consolidar comandos em um **núcleo de 8–9 comandos úteis**.
3. Implementar **temporadas de 30 dias** com soft reset.
4. Garantir que toda resposta de comando tenha **resultado + variação + próximo passo**.
5. Tratar lore como **multiplicador de mecânica**, não substituto.

---

## Se você aprovar, próximo passo prático
Eu posso transformar esta proposta em um **plano técnico executável** com:
- schema SQL novo (ou migração incremental);
- contrato de cada comando (input/output);
- fórmulas iniciais de produção/custos;
- tabela de balanceamento T1→T5;
- roadmap de implementação em PRs pequenos (baixo risco).

Esse seria o caminho para sair de “robusto porém difuso” para “simples, viciante e competitivo”.
