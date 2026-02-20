# Blueprint de Reformulação (Núcleo C) — Feudos Imperiais

> Objetivo: manter o jogo **simples de jogar no Discord** (painel + poucos botões/comandos), mas com profundidade suficiente para criar **ganância, disputa e meta de longo prazo**.
> 
> Sem código nesta etapa. Apenas proposta de design pronta para aprovação.

---

## 1) Princípio de Produto (anti-"comando vazio")

O jogador precisa sentir em 5 segundos:
1. **O que eu tenho** (estado do feudo);
2. **O que posso fazer agora**;
3. **Quanto isso me faz crescer**;
4. **Quem está acima de mim no rank**.

Regra de ouro:
- Poucos comandos centrais;
- Retorno numérico claro;
- Próximo passo sugerido sempre.

---

## 2) Loop central (simples por fora, profundo por dentro)

**Coletar → Construir/Upgradear → Treinar → Incursionar → Equipar → Subir no Rank → Reinvestir**

Esse loop é o jogo. Todo o resto (lore, eventos, conselho, decretos) existe para amplificar esse ciclo.

---

## 3) Estrutura de Feudo (3 prédios oficiais)

Cada jogador tem 1 Feudo com 3 eixos estruturais. Isso evita excesso de menu e mantém clareza:

### 3.1 Celeiros de Guerra (Economia)
- Função: gera **Ouro** ao longo do tempo.
- Escala: T1 → T10.
- Papel: habilitar crescimento bilionário/trilionário (ganância).

### 3.2 Casernas Imperiais (Militar)
- Função: treina **Tropas** por ciclo.
- Escala: T1 → T10.
- Papel: base de poder para incursões e domínio competitivo.

### 3.3 Forja Relicária (Equipamento)
- Função: produz chance de **Achados** (fragmentos/relíquias/entidades).
- Escala: T1 → T10.
- Papel: camada de raridade + sub-lore + diferenciação extrema de contas.

### Dependências (simples e fortes)
- Sem Ouro: progresso trava.
- Sem Tropa: não há incursão.
- Sem Forja: crescimento fica "comum" e sem salto lendário.

---

## 4) Progressão em 3 eixos (poder evidente entre X e Y)

### 4.1 Riqueza (Ouro)
- Escala longa: milhões → bilhões → trilhões.
- Serve para upgrades, manutenção militar e mercado.

### 4.2 Poder (Força do Feudo)
- Fórmula conceitual: Tropas + Qualidade de General + Equipamento de Legião + bônus de doutrina.
- Define capacidade real de vitória em operações.

### 4.3 Prestígio (Legado)
- Pontuação de temporada (não substitui ouro).
- Define títulos, visibilidade, marca histórica nos Anais.

**Resultado de design:**
- Jogador A pode ser mais rico;
- Jogador B pode ser mais forte militarmente;
- Jogador C pode liderar o prestígio.

Assim você cria múltiplas formas de ambição e disputa.

---

## 5) Exército modular (sem poluir UI)

Modelo de composição:
- **Tropa** (massa)
- **General** (1 slot, define estilo)
- **Estrategista** (slot avançado, desbloqueia operações especiais)
- **Equipamento de Legião** (set coletivo)

### Doutrinas de exército (escolha 1 ativa)
- Cerco
- Choque
- Furtivo
- Arcano

Fácil de entender no painel:
- "Meu exército está em Doutrina Choque + General X + Set 2/5".

Profundo para metagame:
- combinações diferentes performam melhor em operações específicas.

---

## 6) Sistema de Achados & Relíquias (sub-lore emergente)

A lore não é entregue no `!guia`; ela é **encontrada**.

Camadas de achado:
1. **Fragmento** (comum): pedaço de pergaminho, pista curta;
2. **Relíquia** (raro): item com micro-lore e efeito;
3. **Entidade** (lendário): herói/general/artefato de era.

### Raridades (modelo de referência)
- SS: 0,01%
- SSS: 0,001%
- SSS+: 0,000001%
- 99999: 0,00000001%

### Regra crucial de UX
O jogador não precisa ver probabilidade exata. Ele vê:
- descoberta dramática;
- impacto prático;
- registro nos Anais.

Isso evita sensação de cassino "seco" e aumenta memória emocional do drop.

---

## 7) Operações (raids narrativas com requisito real)

Operações são conteúdo de objetivo, não texto solto.

Formato de operação:
- Requisitos (tier, composição de exército, cargo especial)
- Risco (perda parcial de tropa/tempo)
- Recompensa (ouro, prestígio, relíquias, fragmentos)
- Chance de desbloqueio de sub-lore

### Exemplo de gate elegante
**Tumba do Sultão da Caravana**
- Requer: Casernas T3+, 1 General, 1 Estrategista.
- Sem estrategista: operação falha com retorno parcial.
- Com estrategista: chance de rota completa e achado lendário.

Isso cria desejo por composição, não só por número bruto.

---

## 8) Painel único de jogo (o que o jogador realmente usa)

Comando principal sugerido: `!dominio`

Blocos do painel:
- Ouro atual + geração/h
- Tropas + fila de treino
- Estado dos 3 prédios
- Exército ativo (general/estrategista/doutrina/set)
- Ações rápidas

Ações rápidas (botões ou subcomandos):
- Coletar
- Melhorar
- Treinar
- Incursão
- Achados/Anais
- Rank

**Filosofia:** um painel para tudo; profundidade nas camadas internas.

---

## 9) Ranking que gera ganância e conflito

Três rankings paralelos:
1. **Magnatas do Império** (riqueza)
2. **Senhores de Guerra** (poder militar)
3. **Lendas dos Anais** (prestígio de temporada)

### Temporadas (30 dias)
- Soft reset de prestígio;
- Ouro e infraestrutura parcialmente preservados com amortecimento;
- recompensas de legado (título, emblema, moldura de perfil, bônus inicial pequeno).

Evita estagnação e mantém novatos com chance de ascensão.

---

## 10) Micro-lore (10 exemplos curtos para coleção)

1. **Pergaminho Rasgado I — "O Trono Silenciou"**  
"Juraram lealdade ao Trono. O Trono não respondeu."

2. **Pergaminho Rasgado II — "Cinza no Estandarte"**  
"A bandeira queimou antes da batalha começar."

3. **Elmo do Basalto (Set de Legião)**  
"Usado quando a muralha ainda respirava."

4. **Lâmina do Juramento Quebrado (General-only)**  
"Quem a empunha vence; quem vence paga."

5. **Insígnia da Sétima Caravana**  
"Ninguém viu a sétima partir. Todos viram ela chegar."

6. **Manopla do Lorde-Demônio de Tanque (99999)**  
"Não foi forjada. Foi lembrada."

7. **Máscara do Estrategista Cego**  
"Ele não via o mapa; via o fim."

8. **Crônica do Herói Sem Túmulo**  
"Salvou o mundo e perdeu o nome."

9. **Selo de Sal de Nahr**  
"Onde o sal cai, a memória acorda."

10. **Fragmento do Pacto Primordial**  
"O primeiro pacto não foi assinado por mãos humanas."

---

## 11) Cinco operações exemplo (com requisito claro)

1. **Tumba do Sultão da Caravana**  
Requisito: Casernas T3+, General, Estrategista.  
Foco: relíquias e fragmentos históricos.

2. **Ruínas da Muralha Viva**  
Requisito: Celeiros T4+, Doutrina Cerco.  
Foco: equipamento de legião (set defensivo).

3. **Poço dos Nomes Perdidos**  
Requisito: Forja T4+, General Arcano.  
Foco: entidade rara e alto prestígio.

4. **Estrada das Sete Cinzas**  
Requisito: Tropa mínima + Doutrina Furtiva.  
Foco: ouro bruto com risco de emboscada.

5. **Fortim do Sol Negro**  
Requisito: Feudo T6+, Set de Legião 3/5.  
Foco: título sazonal e chance de drop SSS+.

---

## 12) Governança imperial (Inkosi/rei sem virar arbitrariedade)

Papel do soberano:
- emitir decretos temporários com efeitos globais moderados;
- abrir eventos de risco/recompensa;
- aplicar bônus/ônus faccionais por período curto.

Limites recomendados:
- duração fixa;
- impacto percentual moderado;
- transparência no painel de temporada.

Objetivo: soberania viva sem quebrar a competitividade.

---

## 13) Modelo C (equilibrado) — por que funciona no Discord

- Entrada simples (painel + 5–6 ações visíveis);
- Profundidade opcional (build de exército, coleção, operação especial);
- Progressão numérica clara (ouro/poder/prestígio);
- Emoção de descoberta (sub-lore rara);
- Ranking com disputa constante.

Você preserva a alma da lore, mas o jogador passa a jogar por objetivo.

---

## 14) Critérios de aprovação da proposta (antes de implementar)

A proposta está aprovada se você concordar com:
1. Feudo com 3 prédios oficiais como núcleo.
2. Três eixos de rank (riqueza, poder, prestígio).
3. Achados raros + sub-lore como progressão emocional.
4. Operações com requisitos de composição (general/estrategista).
5. Painel único `!dominio` como centro da experiência.

Se esses 5 pontos fecharem, o restante vira execução técnica.

---

## 15) Próximo passo pós-aprovação (sem código ainda)

Após seu "ok", o próximo documento deve ser:
- Tabela de balanceamento T1→T10 (custos, produção, treino, manutenção);
- Curva econômica (do milhão ao trilhão sem inflação quebrada);
- Catálogo inicial de 30 itens canônicos (com raridade e micro-lore);
- Matriz de operações com risco/recompensa;
- Especificação enxuta de UX textual para cada ação do painel.

Esse pacote fecha o design e evita retrabalho na implementação.
