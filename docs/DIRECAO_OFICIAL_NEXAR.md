# Decisão Oficial de Design — NEXAR

> **Esta é a nova direção oficial do NEXAR.**
> O produto deixa de ser “vários sistemas soltos” e passa a ser um **domínio vivo**, com leitura rápida, ação imediata e retenção diária dentro do Discord.

---

## 1) NOVO `!dominio` FINAL

O `!dominio` é o **hub central absoluto** do jogo.
Ele deve responder, em segundos, três perguntas:
1. **Onde estou agora?**
2. **O que posso fazer agora?**
3. **Qual é meu próximo passo?**

### Estrutura final obrigatória do painel principal

### A. Economia (estado atual)
- Ouro atual
- Ouro resgatável agora
- Custo do próximo upgrade recomendado
- Status curto: `Pronto para resgate` / `Juntar ouro` / `Upgrade disponível`

### B. Militar (força em movimento)
- Tropas atuais
- Poder total
- Estado do treino (pronto/em ciclo)
- General e Estrategista (rank + progresso)

### C. Operações (risco e avanço)
- Operação recomendada para o estado atual
- Operação bloqueada + motivo objetivo (ex.: falta tier/composição)
- Último resultado operacional (resumo de 1 linha)

### D. Arquivo (valor acumulado)
- Descobertas únicas
- Último achado relevante
- Progresso de coleção (sets/fragmentos)

### E. Próximo Passo (CTA obrigatório)
- Uma linha única, sempre presente, orientando ação imediata.
- Exemplo: `Próximo passo: Resgatar ouro e elevar Casernas para T4.`

### O que sai do foco principal
- Texto longo
- Histórico completo
- Listas extensas
- Informação técnica/admin

### O que vira submenu
- Construções
- Militar (detalhado)
- Operações (lista completa)
- Arquivo (`!cronicas`) detalhado

### Função psicológica oficial
O painel deve:
- **informar** com clareza,
- **provocar ação** por clique,
- **despertar curiosidade**,
- **apontar o próximo passo** sem dúvida.

---

## 2) SISTEMA DE OCORRÊNCIAS (VERSÃO OFICIAL)

Ocorrências são o **coração vivo** do NEXAR.
São o principal gatilho de retorno e surpresa.

### Tipos oficiais
1. **Rumor**
   - pista/informação tática
   - baixo impacto, alta orientação

2. **Oportunidade**
   - janela temporária de vantagem
   - impacto médio (ganho, custo reduzido, bônus situacional)

3. **Presságio**
   - evento raro de alto risco/alto valor
   - impacto alto e memorável

### Como aparecem
- Máximo de **3 ocorrências ativas** por jogador.
- Prioridade visual fixa: **Presságio > Oportunidade > Rumor**.
- Todas com tempo de validade (TTL).

### Como aparecem no painel
Bloco “Ocorrências” com:
- tipo + título curto,
- tempo restante,
- ação sugerida (`ir para Operações`, `forjar`, `coletar agora`).

### Como o jogador interage
Cada ocorrência tem apenas 2 destinos:
- **Resolvida** (via ação já existente),
- **Ignorada** (expira).

Após resolver, retorno curto obrigatório:
- impacto,
- ganho/perda,
- próximo passo.

### Regra de retenção
- Não virar spam: no máximo 1 ocorrência nova relevante por janela curta.
- Repetições não poluem: agregadas por frequência em histórico resumido.
- Resultado esperado: jogador abrir o NEXAR pensando **“o que surgiu agora?”**.

---

## 3) NOVO `!cronicas` / ARQUIVO FINAL

O Arquivo deixa de ser dump textual.
Passa a ser **coleção, descoberta e legado**.

### Modelo oficial

### Visão 1 — Resumo
- Total por categoria:
  - Fragmentos
  - Relíquias
  - Entidades
- Progresso de sets
- Últimos 3 achados relevantes

### Visão 2 — Detalhe
- Paginação por categoria e raridade
- Cada registro com:
  - nome,
  - raridade,
  - quantidade,
  - última aquisição,
  - origem (`forja`, `operação`, `ocorrência`)

### Regra de repetição
- Repetidos **empilham por chave de item**.
- Histórico de aquisição fica separado do inventário principal.

### Raridade e leitura
- Selos de raridade visuais e curtos (`R`, `SR`, `SSR`, `SSS+`, `99999`).
- Quantidade sempre visível (`x2`, `x15`).

### Papel da Forja
- Forja é fonte oficial de descoberta e progressão de coleção.
- Forja não é sistema paralelo: ela alimenta diretamente o Arquivo.

### Resultado esperado
`!cronicas` deve transmitir:
- status,
- valor acumulado,
- memória de conquista,
- desejo de completar coleção.

---

## 4) ROADMAP OFICIAL DE REFORMA

## Etapa 1 — Clareza imediata do núcleo
### O que muda
- `!dominio` vira hub final com blocos fixos + CTA.
- redução de ruído textual.

### O que permanece
- economia, militar, operações e forja atuais.

### O que é reaproveitado
- dados persistidos existentes,
- subviews já implementadas.

### O que é adicionado
- motor de “próximo passo” determinístico.

### Ganho imediato ao jogador
- compreensão instantânea do que fazer agora.

---

## Etapa 2 — Ocorrências como motor de vida
### O que muda
- entrada oficial de Rumor/Oportunidade/Presságio no fluxo diário.

### O que permanece
- loop base de progresso por ações existentes.

### O que é reaproveitado
- operações e forja como destino natural das ocorrências.

### O que é adicionado
- geração temporal controlada + TTL + resolução simples.

### Ganho imediato ao jogador
- motivo real para voltar várias vezes ao dia.

---

## Etapa 3 — Arquivo como status competitivo
### O que muda
- `!cronicas` vira coleção estruturada (resumo + detalhe + progresso).

### O que permanece
- raridades e achados já existentes.

### O que é reaproveitado
- inventário e histórico atuais.

### O que é adicionado
- empilhamento oficial,
- visão por categoria,
- progressão de set com leitura clara.

### Ganho imediato ao jogador
- sensação de legado e status contínuo.

---

## Declaração final

**Esta é a nova direção oficial do NEXAR**:
- progresso claro,
- risco real,
- curiosidade constante,
- oportunidade viva,
- status reconhecível.

O NEXAR passa a ser um domínio que **se move mesmo quando o jogador não está olhando** — e que recompensa quem volta, decide e executa.
