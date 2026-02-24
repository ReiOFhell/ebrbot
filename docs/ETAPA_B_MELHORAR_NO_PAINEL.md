# Etapa B.1 — Melhorar construções direto no painel

Melhoria aplicada sobre a subview de Construções:

- O botão **🛠️ Melhorar** abre seleção de construção no próprio painel (select menu).
- O jogador escolhe **Celeiros / Casernas / Forja** e o upgrade é executado sem precisar digitar comando.
- A tela é atualizada no mesmo embed com retorno no padrão UX:
  - resultado;
  - variação;
  - próximo passo.
- O comando textual `!melhorar` foi mantido e agora reutiliza o mesmo núcleo (`do_upgrade`).

Benefício: menos fricção e menos dependência de sintaxe, mantendo compatibilidade com comandos existentes.
