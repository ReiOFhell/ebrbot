# Proposta — Centralizar o jogo em `!dominio` com botões

Sua ideia é **boa e correta** para Discord: reduzir comandos e jogar por painel.

## Diagnóstico
Hoje, muitos comandos criam fricção:
- jogador precisa decorar sintaxe;
- perde contexto entre ações;
- sensação de complexidade aumenta sem aumentar diversão.

## Direção recomendada
Manter **1 comando central** (`!dominio`) e transformar o resto em botões/menus no próprio painel.

---

## Estrutura sugerida do painel

### Bloco superior (sempre visível)
- Ouro atual
- Ouro para resgatar
- Tropas
- Poder
- Níveis dos 3 prédios (Celeiros/Casernas/Forja)

### Linha de botões principais
1. **Resgatar** (equivale `!coletar`)
2. **Treinar** (equivale `!treinar`)
3. **Construções**
4. **Militar**
5. **Operações**
6. **Rank**

---

## Fluxo por botão

## 1) Resgatar
- Clique direto.
- Retorno imediato com:
  - quanto ganhou bruto,
  - manutenção,
  - líquido,
  - próximo passo recomendado.

## 2) Construções
Abre uma view (ephemeral) com 3 botões:
- Celeiros
- Casernas
- Forja

Ao clicar em cada um:
- mostra nível atual,
- custo de upgrade,
- impacto esperado,
- botão **Melhorar**.

## 3) Militar
Abre painel ephemeral com:
- doutrina atual,
- slot de general,
- slot de estrategista,
- botões: trocar doutrina, equipar general, equipar estrategista.

## 4) Operações
Lista operações desbloqueadas e bloqueadas (com motivo).
- Cada operação vira botão: **Simular**.
- Se faltar requisito, mensagem clara no mesmo painel.

## 5) Rank
Mostra top riqueza/poder/prestígio com paginação simples.

---

## Redução de comandos (proposta prática)

## Comandos visíveis ao usuário
- `!dominio` (principal)
- `!rank` (opcional como atalho)
- `!guia` (ajuda)

## Comandos que viram ações internas de botão
- `!coletar`
- `!treinar`
- `!melhorar`
- `!doutrina`
- `!equipar_general`
- `!equipar_estrategista`
- `!simular_operacao`
- `!forjar`

Resultado: de ~14 comandos para 3–4 comandos públicos.

---

## Por que isso tende a funcionar melhor no servidor
1. **Menos curva de aprendizado** (não precisa decorar sintaxe).
2. **Mais retenção** (o jogador sempre vê o próximo passo no mesmo lugar).
3. **Menos erro de uso** (botões validam fluxo).
4. **Mais sensação de progresso** (UI consolidada e feedback contínuo).

---

## Regras de UX para o painel (essenciais)
Toda ação deve responder com 3 linhas:
1. O que aconteceu;
2. quanto mudou;
3. o próximo clique recomendado.

Exemplo:
- ✅ Treino concluído
- Δ Tropas: +120 | Δ Poder: +98
- Próximo: abrir **Operações**

---

## Riscos e mitigação
- **Painel poluído** → usar 6 botões máximos por tela + subviews.
- **Timeout de interação** → botão “Reabrir painel”.
- **Spam de clique** → cooldown curto por botão + lock por usuário.

---

## Plano de implementação (curto)

### Etapa A (rápida)
- manter backend atual;
- criar `DominioView` com botões que chamam as funções já existentes.

### Etapa B
- mover respostas de comandos para handlers internos reutilizáveis;
- tornar comandos antigos aliases/ocultos.

### Etapa C
- deixar apenas `!dominio` como entrada principal;
- manter `!rank` e `!guia` como atalhos.

---

## Conclusão
Sim: a centralização no `!dominio` com botões é a melhor evolução para o seu caso.
É o caminho mais consistente para **menos complexidade + mais jogabilidade** no Discord.
