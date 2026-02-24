# Pacote Pós-OK — Núcleo C (Feudos Imperiais)

Documento de fechamento de design para iniciar implementação sem retrabalho.

---

## 1) Tabela de balanceamento T1→T10

### 1.1 Celeiros de Guerra (Ouro/h)
| Tier | Custo upgrade (Ouro) | Produção Ouro/h | Manutenção/h |
|---|---:|---:|---:|
| T1 | 100.000 | 12.000 | 300 |
| T2 | 250.000 | 28.000 | 700 |
| T3 | 700.000 | 62.000 | 1.600 |
| T4 | 1.800.000 | 135.000 | 3.500 |
| T5 | 4.500.000 | 290.000 | 7.500 |
| T6 | 12.000.000 | 620.000 | 16.000 |
| T7 | 32.000.000 | 1.350.000 | 35.000 |
| T8 | 90.000.000 | 2.900.000 | 75.000 |
| T9 | 260.000.000 | 6.200.000 | 160.000 |
| T10 | 750.000.000 | 13.500.000 | 350.000 |

### 1.2 Casernas Imperiais (Treino)
| Tier | Custo upgrade (Ouro) | Tropas por ciclo | Duração ciclo | Manutenção/h |
|---|---:|---:|---:|---:|
| T1 | 120.000 | 10 | 30 min | 500 |
| T2 | 300.000 | 24 | 30 min | 1.200 |
| T3 | 850.000 | 55 | 30 min | 2.600 |
| T4 | 2.200.000 | 120 | 30 min | 5.500 |
| T5 | 5.500.000 | 260 | 30 min | 11.500 |
| T6 | 14.000.000 | 560 | 30 min | 24.000 |
| T7 | 38.000.000 | 1.200 | 30 min | 52.000 |
| T8 | 105.000.000 | 2.550 | 30 min | 112.000 |
| T9 | 300.000.000 | 5.400 | 30 min | 240.000 |
| T10 | 860.000.000 | 11.500 | 30 min | 520.000 |

### 1.3 Forja Relicária (qualidade de achados)
| Tier | Custo upgrade (Ouro) | Tentativas de Forja/dia | Bônus de qualidade |
|---|---:|---:|---:|
| T1 | 90.000 | 2 | +0% |
| T2 | 220.000 | 3 | +1% |
| T3 | 600.000 | 4 | +2% |
| T4 | 1.600.000 | 5 | +4% |
| T5 | 4.000.000 | 6 | +7% |
| T6 | 10.500.000 | 7 | +10% |
| T7 | 29.000.000 | 8 | +14% |
| T8 | 82.000.000 | 9 | +19% |
| T9 | 230.000.000 | 10 | +25% |
| T10 | 670.000.000 | 12 | +32% |

### 1.4 Tempos de upgrade (anti-rush)
| Tier alvo | Tempo de upgrade |
|---|---:|
| T2 | 15 min |
| T3 | 35 min |
| T4 | 1 h 20 min |
| T5 | 2 h 30 min |
| T6 | 4 h 30 min |
| T7 | 7 h |
| T8 | 10 h |
| T9 | 14 h |
| T10 | 20 h |

---

## 2) Curva econômica (milhão → trilhão sem inflação quebrada)

## 2.1 Fórmulas base
- **Custo de upgrade (genérico):** `base * 2.55^(tier-1)`
- **Produção de ouro:** `base * 2.20^(tier-1)`
- **Manutenção:** `base * 2.30^(tier-1)`

Racional:
- custo cresce mais rápido que produção no longo prazo;
- manutenção pune expansão sem planejamento;
- evita “bola de neve sem freio”.

## 2.2 Marcos esperados por estágio de conta
| Estágio | Janela esperada | Ouro total alvo | Produção/h alvo |
|---|---|---:|---:|
| Início | Dia 1–3 | 1M–8M | 20k–150k |
| Crescimento | Dia 4–10 | 10M–120M | 200k–1.5M |
| Domínio | Dia 11–20 | 150M–3B | 2M–18M |
| Alta elite | Dia 21–30 | 5B–120B | 25M–220M |
| Endgame sazonal | pós-30 dias | 200B–1T+ | 300M+ |

## 2.3 Freios econômicos (obrigatórios)
1. Taxa de mercado progressiva para grandes volumes (2% → 9%).
2. Custo de manutenção militar cresce por "faixas de exército".
3. Diminuição de eficiência acima de 24h sem coletar (overflow de estoque).
4. Reparo pós-derrota em operações grandes.
5. Soft reset de temporada em Prestígio e bônus temporários.

---

## 3) Catálogo inicial de 30 itens canônicos

### 3.1 Fragmentos (12)
| Item | Raridade | Fonte | Micro-lore | Efeito |
|---|---|---|---|---|
| Pergaminho Rasgado I | C | Forja/Incursão | "O Trono não respondeu." | +1% Prestígio em operação (1 uso) |
| Pergaminho Rasgado II | C | Forja | "A bandeira queimou antes do aço." | +2% ouro em coleta única |
| Fragmento de Sal de Nahr | C | Incursão | "A memória acorda no sal." | Remove penalidade leve de fadiga |
| Mapa da Sétima Rota | C | Caravana | "Ela chegou sem partir." | +3% chance de evento oculto (1h) |
| Crônica Queimada | C | Ruínas | "Sobrou o título, não o nome." | +5 Prestígio |
| Selo Trincado de Basalto | C | Forja | "A muralha respirava." | +1% defesa em operação |
| Tábua de Comando Velha | C | Casernas | "Contava mortos antes da luta." | -3% tempo de treino (1 ciclo) |
| Fio de Estandarte Negro | C | Incursão | "Só os derrotados o viram." | +1% poder em doutrina Choque |
| Bilhete do Cartógrafo | C | Operação | "O caminho muda quando olham." | +1 tentativa de rota |
| Lacre Imperial Gasto | C | Conselho | "Assinado em silêncio." | +1 voto simbólico em evento |
| Cinza de Altar Antigo | C | Forja | "A chama lembrava nomes." | +2% qualidade forja (1 uso) |
| Cifra do Vigia | C | Ruínas | "Ele viu o fim duas vezes." | +1% sucesso furtivo |

### 3.2 Relíquias (12)
| Item | Raridade | Fonte | Micro-lore | Efeito |
|---|---|---|---|---|
| Elmo do Basalto | R | Ruínas Muralha | "Usado quando a pedra respirava." | Set Legião Basalto (1/5) |
| Grevas do Basalto | R | Ruínas Muralha | "Marchavam sem ruído." | Set Legião Basalto (2/5) |
| Escudo do Basalto | R | Ruínas Muralha | "Negava o primeiro impacto." | Set Legião Basalto (3/5) |
| Lâmina do Juramento Quebrado | R | Tumba | "Vencer também custa." | General +8% ataque |
| Máscara do Estrategista Cego | R | Poço | "Via o fim, não o mapa." | Estrategista +10% sucesso tático |
| Insígnia da Sétima Caravana | R | Caravana | "Ninguém viu partir." | +12% ouro em Estrada das Cinzas |
| Manoplas da Vigília | R | Fortim | "Nunca baixaram o estandarte." | +6% defesa de legião |
| Coroa de Cinzas Frias | R | Forja alta | "O fogo já havia vencido." | +15 Prestígio por drop lendário |
| Lança de Nahr | R | Ruínas | "Onde tocou, nasceu silêncio." | Doutrina Cerco +7% |
| Livro de Ferro do Senescal | R | Conselho | "Contas antes de glória." | -4% manutenção global |
| Relógio de Guerra Partido | R | Incursão | "O tempo falhou primeiro." | -8% tempo de upgrade (1 uso) |
| Selo do Pacto Menor | R | Poço | "Juramento sem testemunhas." | +6% qualidade forja (2h) |

### 3.3 Entidades/Artefatos de Era (6)
| Item | Raridade | Fonte | Micro-lore | Efeito |
|---|---|---|---|---|
| Crônica do Herói Sem Túmulo | L | Operação elite | "Salvou o mundo e perdeu o nome." | General único Rank S |
| Manopla do Lorde-Demônio de Tanque | Mítica | Fortim Sol Negro | "Não foi forjada. Foi lembrada." | General Rank SSS+ (defesa extrema) |
| Estandarte da Primeira Ruptura | L | Evento temporada | "Erguido antes da era escrita." | +20% poder em guerra sazonal |
| Olho de Obsidiana Primordial | Mítica | Poço profundo | "Vê o que nunca existiu." | Libera operação secreta |
| Coração da Muralha Viva | L | Ruínas avançadas | "A pedra ainda escolhe lados." | Set Basalto bônus final (5/5) |
| Fragmento do Pacto Primordial | Mítica | Achado ultrarraro | "Não foi assinado por humanos." | Marca de Crônicas + título único |

### 3.4 Escala de raridade padrão
- Comum (C): ~6% por tentativa útil
- Raro (R): ~0,35%
- Lendário (L): ~0,01%
- Mítica (SSS+/99999): 0,000001% a 0,00000001%

---

## 4) Matriz de operações (risco/recompensa)

| Operação | Requisitos | Risco | Recompensa base | Chance especial |
|---|---|---|---|---|
| Tumba do Sultão da Caravana | Casernas T3+, General, Estrategista | Perda 6–12% tropas | Ouro + Relíquia histórica | 0,15% Entidade |
| Ruínas da Muralha Viva | Celeiros T4+, Doutrina Cerco | Perda 4–9% tropas | Itens Set Basalto | 0,08% peça lendária |
| Poço dos Nomes Perdidos | Forja T4+, General Arcano | Falha tática + cooldown 2h | Prestígio alto + Relíquia | 0,02% Mítica |
| Estrada das Sete Cinzas | Tropa mínima + Furtivo | Emboscada 10% chance | Ouro bruto elevado | 0,2% evento oculto |
| Fortim do Sol Negro | Feudo T6+, Set 3/5 | Perda 12–20% tropas | Título sazonal + drop premium | 0,005% SSS+ |
| Caravana Quebrada de Nahr | Celeiros T3+, Estrategista | Roubo parcial de carga | Ouro + Fragmentos | 0,12% mapa secreto |
| Bastião do Juramento Partido | Casernas T5+, General | Defesa inimiga forte | Prestígio + item general-only | 0,03% Lendário |
| Cripta do Vigia Duplo | Forja T6+, Arcano/Furtivo | Debuff 3h se falhar | Relíquia tática | 0,01% Entidade |
| Trono de Sal | Prestígio sazonal mínimo | Custo alto de entrada | Prestígio maciço | 0,001% Mítica |
| Fenda do Pacto Antigo | Gate secreto (item-chave) | Risco máximo | Recompensa de era | 0,00000001% item 99999 |

### 4.1 Regras de justiça competitiva
- 2 operações de alto risco por dia (cap);
- proteção de novato (primeiros 3 dias sem perdas graves);
- derrota nunca zera conta (apenas atraso/attrition).

---

## 5) UX textual enxuta por ação do painel

## 5.1 Estrutura padrão de resposta
Toda ação retorna 3 blocos:
1. **Resultado** (o que ocorreu);
2. **Variação** (+/- recursos/poder/prestígio);
3. **Próximo passo recomendado**.

Formato curto padrão:
- `✅ [AÇÃO] concluída.`
- `Δ Ouro: +X | Δ Tropas: +Y | Δ Prestígio: +Z`
- `Próximo: <ação sugerida>`

## 5.2 Exemplos por ação principal

### `Coletar`
- "✅ Coleta imperial concluída."
- "Δ Ouro: +1.240.000 | Estoque: 68%"
- "Próximo: `Melhorar Celeiros` (custo 4.500.000)."

### `Melhorar`
- "✅ Celeiros avançaram para T5."
- "Δ Produção/h: +155.000 | Δ Manutenção/h: +4.000"
- "Próximo: `Treinar` para sustentar incursões."

### `Treinar`
- "✅ Casernas concluíram o ciclo."
- "Δ Tropas: +260 | Prontas para incursão: 1.420"
- "Próximo: `Incursão: Tumba do Sultão`."

### `Incursão`
- "⚔️ Incursão concluída: vitória tática."
- "Δ Ouro: +2.800.000 | Δ Tropas: -94 | Δ Prestígio: +22"
- "Achado: **Insígnia da Sétima Caravana**."
- "Próximo: `Equipar General` ou `Rank`."

### `Achados/Crônicas`
- "📜 Novo fragmento registrado nas Crônicas."
- "Item: Fragmento do Pacto Primordial (incompleto 1/3)."
- "Próximo: `Poço dos Nomes Perdidos` (requisito já cumprido)."

### `Rank`
- "🏛️ Posição atual: #12 Riqueza | #34 Poder | #7 Prestígio."
- "Meta próxima: +420 Prestígio para Top 5."
- "Próximo: `Fortim do Sol Negro` (janela em 2h)."

## 5.3 Alertas de erro (curtos, nunca vagos)
- Falta de requisito: "❌ Requisito ausente: Estrategista ativo."
- Recurso insuficiente: "❌ Ouro insuficiente: falta 1.300.000."
- Cooldown: "⏳ Ação em recuperação: 18m restantes."
- Limite diário: "⚠️ Limite diário atingido (2/2 operações de alto risco)."

---

## 6) Checklist de implementação (ordem recomendada)
1. Tabelas e fórmulas de economia + manutenção.
2. Loop de painel (`dominio`) com ações rápidas.
3. Operações base (3 primeiras da matriz).
4. Sistema de achados (fragmento/relíquia/entidade).
5. Rank triplo + temporada.
6. Conteúdo sazonal (Fortim/Trono/Fenda).

---

## 7) Critérios de aceite do pacote
- O jogador novo entende o caminho em 1 painel.
- Existe diferença visível entre contas em 3 eixos.
- Raridade gera surpresa sem quebrar balanceamento.
- As operações são desejáveis e legíveis.
- O texto de retorno nunca deixa dúvida sobre avanço.
