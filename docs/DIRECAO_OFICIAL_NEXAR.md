# Decisão Oficial de Design — NEXAR

Este documento define a nova direção jogável oficial do NEXAR. A partir desta decisão, o bot deixa de operar como um conjunto disperso de sistemas e passa a operar como um **domínio vivo orientado a retenção no Discord**.

---

## 1) NOVO `!dominio` FINAL (Hub Central)

### Estrutura final do painel principal
O `!dominio` passa a ter **4 blocos fixos** e **1 trilho de ação**:

1. **Economia (Agora)**
   - Ouro atual
   - Ouro resgatável
   - Custo da próxima melhoria recomendada
   - Indicador curto: `Pronto para resgate` / `Juntar para upgrade`

2. **Militar (Força em curso)**
   - Tropas
   - Poder total
   - Estado de treino (pronto/em ciclo)
   - Estado do General e Estrategista (rank e progresso)

3. **Operações (Risco do momento)**
   - 1 operação recomendada para o estado atual
   - 1 operação bloqueada com motivo explícito (ex.: “Falta Casernas T4”)
   - Resultado da última operação (mini-resumo)

4. **Arquivo (Valor acumulado)**
   - Total de descobertas únicas
   - Último achado relevante
   - Progresso de coleção (ex.: `Set Basalto 2/5`)

5. **Próximo Passo (CTA obrigatório)**
   - Linha única e direta, sempre presente:
     - Ex.: `Próximo passo: Resgatar e elevar Celeiros para T4.`
     - Ex.: `Próximo passo: Executar Estrada das Sete Cinzas.`

### O que sai do foco principal
- Detalhes extensos, listas longas e histórico completo saem da tela principal.
- Informações técnicas de diagnóstico e administração nunca aparecem no painel normal.

### O que vira submenu
- **Construções**: upgrade detalhado por prédio.
- **Militar**: evolução detalhada de General/Estrategista + doutrina.
- **Operações**: lista completa, requisitos e execução.
- **Arquivo**: inventário completo e detalhes de coleção.

### Função psicológica oficial do painel
O `!dominio` deve, em uma única leitura:
- **Informar**: “onde eu estou agora”.
- **Provocar ação**: “o que está pronto para clique”.
- **Despertar curiosidade**: “o que apareceu de novo”.
- **Guiar progresso**: “qual é meu próximo passo imediato”.

---

## 2) SISTEMA DE OCORRÊNCIAS (Versão Oficial)

Ocorrências passam a ser o motor vivo do NEXAR. Elas são curtas, acionáveis e temporais.

### Tipos oficiais
1. **Rumor**
   - Natureza: informativo/tático.
   - Ex.: bônus contextual, aviso de risco, pista de operação.
   - Impacto: pequeno, orienta decisão.

2. **Oportunidade**
   - Natureza: janela de ganho.
   - Ex.: bônus temporário em ouro, chance extra de achado, custo reduzido de ação.
   - Impacto: médio, cria urgência de retorno.

3. **Presságio**
   - Natureza: evento raro com consequência de alto valor narrativo.
   - Ex.: rota especial, chance de relíquia superior, risco elevado com retorno alto.
   - Impacto: alto, memorável.

### Como aparecem
- Cada jogador mantém **até 3 ocorrências ativas** simultâneas.
- Regra de prioridade visual no painel:
  1) Presságio
  2) Oportunidade
  3) Rumor
- Ocorrências têm validade (TTL) e expiram automaticamente.

### Como são exibidas no `!dominio`
- Bloco “Ocorrências” com formato padrão:
  - Ícone + tipo + título curto
  - Tempo restante
  - Ação sugerida (`Ir para Operações`, `Forjar agora`, etc.)

### Interação do jogador
- Cada ocorrência deve ter apenas dois estados: **ignorada** ou **resolvida**.
- Resolução sempre via ação existente (não criar comando novo obrigatório).
- Resultado curto após resolução:
  - ganho/perda,
  - impacto,
  - próximo passo.

### Regra de retenção sem bagunça
- No máximo 1 nova ocorrência relevante por janela curta (anti-spam).
- Ocorrência repetida não vira texto duplicado: soma frequência em histórico resumido.
- Objetivo: o jogador pensar “vou abrir o NEXAR para ver se algo apareceu”.

---

## 3) NOVO `!cronicas` / ARQUIVO FINAL

O Arquivo passa a ser coleção viva e legível, não dump de texto.

### Modelo oficial de organização

#### A) Resumo (primeira visão)
- Totais por categoria:
  - Fragmentos
  - Relíquias
  - Entidades
- Progresso por coleção/set
- Últimas 3 descobertas relevantes

#### B) Detalhe (segunda visão)
- Lista paginada por categoria/raridade
- Cada item mostra:
  - nome,
  - raridade,
  - quantidade,
  - última data de aquisição,
  - tag de origem (`forja`, `operação`, `ocorrência`)

### Regra de empilhamento
- Itens repetidos **empilham por chave** (`item_key`) com contador.
- Histórico separado guarda eventos de aquisição, não duplicata no inventário principal.

### Categorias e raridade (visual oficial)
- Categorias fixas: `Fragmento`, `Relíquia`, `Entidade`.
- Raridade com selo visual curto (ex.: `R`, `SR`, `SSR`, `SSS+`, `99999`).
- Quantidade sempre visível ao lado do nome (`x3`, `x12`).

### Forja no Arquivo (integração oficial)
- Forja entra como **fonte de descoberta** e **progressão de coleção**.
- Não é sistema isolado: cada forja alimenta diretamente o Arquivo e o progresso de sets.

### Resultado desejado
`!cronicas` deve transmitir:
- coleção com valor,
- descoberta com memória,
- legado com status.

---

## 4) ROADMAP OFICIAL DE REFORMA (3 Etapas)

## Etapa 1 — Clareza imediata do núcleo (impacto em 1 semana)
### O que muda
- Reformulação do `!dominio` com blocos fixos + “Próximo Passo”.
- Remoção de ruído textual da tela principal.
- Submenus organizados por área (Construções, Militar, Operações, Arquivo).

### O que permanece
- Economia, tropas, operações, forja e ranking continuam existindo.

### O que é reaproveitado
- Dados atuais de ouro, poder, estruturas e operações.
- UI de botões já existente.

### O que é adicionado
- Camada de recomendação de próximo passo (determinística).

### Melhoria imediata para o jogador
- Entendimento em segundos do que fazer agora.

---

## Etapa 2 — Coração vivo via Ocorrências (impacto em retenção)
### O que muda
- Introdução oficial do sistema Rumor/Oportunidade/Presságio.
- Bloco de ocorrências passa a morar no `!dominio`.

### O que permanece
- Loop base (resgatar, evoluir, treinar, operar) continua igual.

### O que é reaproveitado
- Operações, forja e recompensas existentes como destinos das ocorrências.

### O que é adicionado
- Geração temporal controlada de ocorrências + TTL + resolução.

### Melhoria imediata para o jogador
- Motivo real para voltar várias vezes ao dia.

---

## Etapa 3 — Arquivo como status e legado (impacto em longo prazo)
### O que muda
- `!cronicas` vira coleção com resumo + detalhe paginado.
- Empilhamento de repetidos e progressão de sets.

### O que permanece
- Achados já existentes e lógica de raridade.

### O que é reaproveitado
- Histórico atual de itens/pergaminhos/relíquias.

### O que é adicionado
- Camada de apresentação orientada a valor (quantidade, raridade, origem, progresso).

### Melhoria imediata para o jogador
- Sensação de legado contínuo e status acumulado.

---

## Declaração final

**Esta é a nova direção oficial do NEXAR**:
- menos fricção,
- mais clareza por clique,
- mundo vivo por ocorrências,
- coleção com significado,
- progresso que o jogador sente toda vez que abre o painel.
