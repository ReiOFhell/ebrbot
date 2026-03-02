# Análise Geral do Bot e Plano de Melhorias (passo a passo)

## 1) Resumo executivo

O bot já possui base funcional sólida (economia, operações, painel, persistência e ranking), mas o código está concentrado em poucos arquivos muito grandes e com baixo nível de automação de qualidade.

Principais pontos encontrados:

- **Monólito operacional no `bot.py`** (inicialização de DB, regras, comandos, embeds e admin no mesmo arquivo).
- **Baixa cobertura de validação automatizada** (não há suíte de testes no repositório).
- **Inicialização de banco e seeds acopladas à execução** (funciona, mas dificulta evolução e rollback).
- **Tratamento genérico de erros em pontos críticos** (reduz observabilidade de causa-raiz).
- **Boa oportunidade para modularização por domínio** (domínio/economia/militar/operações/admin/telemetria).

---

## 2) Evidências objetivas da análise

### 2.1 Tamanho e acoplamento de arquivos

- `bot.py`: **1867 linhas**
- `services/gameplay.py`: **438 linhas**
- `ui/views.py`: **487 linhas**
- `core/economy.py`: **128 linhas**

Conclusão: o núcleo está funcional, porém com concentração de responsabilidades em `bot.py`.

### 2.2 Ausência de suíte de testes

Não há pasta `tests/` no projeto atual, e os checks usuais são apenas compilação/execução manual.

### 2.3 Tratamento de erro amplo

Foram identificados blocos com `except Exception` em runtime (ex.: comandos e callbacks), o que mantém estabilidade mas dificulta diagnóstico fino e ações corretivas direcionadas.

---

## 3) O que deve ser mudado, melhorado ou refeito

## Prioridade P0 (curto prazo, alto impacto)

1. **Criar base mínima de qualidade (CI + testes + lint)**.
2. **Reduzir acoplamento do `bot.py`** movendo blocos por contexto.
3. **Introduzir versionamento de schema/migrações** (em vez de depender só de `ensure_column` + seeds no bootstrap).
4. **Padronizar erros e respostas** (erros de usuário vs erro interno, com códigos rastreáveis).

## Prioridade P1 (médio prazo)

5. **Organizar arquitetura por camadas** (commands → services → repositories).
6. **Extrair queries SQL para módulos de repositório**.
7. **Cobrir regras críticas com testes determinísticos** (economia/operação/evolução).
8. **Reforçar telemetria de funil de UX** no painel.

## Prioridade P2 (próximas adições)

9. **Feature flags para mudanças de balanceamento**.
10. **Rotina de backup e healthcheck de DB**.
11. **Documentação operacional de release/rollback**.

---

## 4) Passo a passo para implementar as melhorias

## Fase 0 — Preparação (1 dia)

1. Congelar escopo atual (sem novos recursos durante refactor).
2. Definir branch de melhoria contínua (`chore/refactor-foundation`).
3. Registrar baseline:
   - tempo de resposta do `!dominio`
   - volume de erros por comando
   - contagem de usuários ativos e retenção básica

**Saída da fase:** baseline documentado para comparar antes/depois.

---

## Fase 1 — Qualidade automatizada (1–2 dias)

1. Adicionar ferramentas de qualidade:
   - `ruff` (lint)
   - `black` (formatação)
   - `pytest` (testes)
2. Criar pipeline CI (GitHub Actions):
   - install deps
   - lint
   - type check opcional
   - testes
3. Definir padrão mínimo de merge:
   - CI obrigatório verde
   - sem warnings críticos de lint

**Saída da fase:** todo PR validado automaticamente.

---

## Fase 2 — Testes do núcleo econômico/militar (2–3 dias)

1. Criar pasta `tests/` com foco inicial em:
   - `core/economy.py` (fórmulas e limites)
   - `services/gameplay.py` (coletar/treinar/melhorar/evoluir/operação)
2. Cobrir cenários principais:
   - caminho feliz
   - falta de recurso
   - cooldown
   - requisito de operação ausente
3. Garantir testes determinísticos:
   - controlar random seed quando houver RNG

**Saída da fase:** confiança para evoluir sem quebrar loop central.

---

## Fase 3 — Modularização do `bot.py` (3–5 dias)

1. Extrair módulos:
   - `commands/public.py`
   - `commands/admin.py`
   - `embeds/*.py`
   - `infra/db_init.py`
   - `infra/telemetry.py`
2. Manter `bot.py` apenas como bootstrap/composição.
3. Preservar compatibilidade dos comandos existentes (`!dominio`, `!guia`, `!rank`, etc.).

**Saída da fase:** manutenção mais fácil e menor risco de regressão cruzada.

---

## Fase 4 — Banco e migrações versionadas (2–3 dias)

1. Introduzir versão de schema (`schema_version` + histórico de migrações).
2. Transformar seed atual em scripts idempotentes por versão.
3. Separar claramente:
   - criação de tabela
   - migração de coluna
   - seed funcional
4. Criar comando/admin check:
   - versão atual
   - migração pendente

**Saída da fase:** evolução segura de DB para próximas features.

---

## Fase 5 — Repositórios e isolamento de SQL (3–4 dias)

1. Criar camada `repositories/`:
   - `domain_repo.py`
   - `army_repo.py`
   - `operations_repo.py`
   - `season_repo.py`
2. Mover SQL inline para métodos nomeados.
3. Garantir transações em operações compostas (com contexto único).

**Saída da fase:** regras de negócio mais legíveis e SQL rastreável.

---

## Fase 6 — Observabilidade e confiabilidade (2 dias)

1. Padronizar logs estruturados (`command`, `user_id`, `action`, `error_code`).
2. Trocar `except Exception` genérico por exceções mais específicas quando possível.
3. Expandir métricas de painel:
   - abertura
   - clique por seção
   - abandono por etapa

**Saída da fase:** diagnóstico rápido em produção.

---

## Fase 7 — UX e governança de comandos (2 dias)

1. Revisar comandos ocultos e aliases legados.
2. Consolidar onboarding (`!guia`) com passos de progressão real.
3. Definir política de depreciação de comandos antigos:
   - aviso por X versões
   - remoção programada

**Saída da fase:** superfície de comando limpa para novos jogadores.

---

## Fase 8 — Pronto para próximas adições (1 dia)

Checklist de saída para começar novas features:

- [ ] CI verde obrigatório
- [ ] Testes núcleo cobrindo fluxo principal
- [ ] `bot.py` reduzido para bootstrap
- [ ] Migrações versionadas ativas
- [ ] SQL extraído em repositórios
- [ ] Observabilidade mínima com códigos de erro
- [ ] Documento de release/rollback atualizado

Quando este checklist estiver completo, o projeto está em condição segura para próxima onda de features (novas operações, eventos sazonais, progressões especiais, etc.).

---

## 5) Ordem recomendada de execução (resumida)

1. Fase 1 (qualidade automatizada)
2. Fase 2 (testes do núcleo)
3. Fase 3 (modularização)
4. Fase 4 (migrações)
5. Fase 5 (repositórios)
6. Fase 6 (observabilidade)
7. Fase 7 (UX/comandos)
8. Fase 8 (go/no-go para novas adições)

Essa ordem reduz risco técnico primeiro e acelera futuras entregas.
