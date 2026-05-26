# Etapa B — Subview de Construções no próprio embed

Implementação aplicada:

- Ao clicar em **Construções** no `!dominio`, o bot agora **edita a mesma mensagem** com um embed de construções (`build_construcoes_embed`) em vez de abrir texto ephemeral separado.
- O painel de construções usa `ConstrucoesView` com botão **⬅️ Voltar** para retornar ao embed principal (`build_dominio_embed`) sem criar novos comandos.

## Benefício
- Fluxo mais organizado em uma única mensagem.
- Navegação clara (painel principal ↔ construções).
- Menos poluição de mensagens no canal.
