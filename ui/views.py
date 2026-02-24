from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable

import discord


@dataclass
class PanelDeps:
    service: Any
    build_dominio_embed: Callable[[str], discord.Embed]
    build_construcoes_embed: Callable[[str, str | None], discord.Embed]
    build_militar_embed: Callable[[str, str | None], discord.Embed]
    build_operacoes_embed: Callable[[str, str | None], discord.Embed]
    build_rank_embed: Callable[[], discord.Embed]
    get_conn: Callable[[], Any]
    get_or_create_domain: Callable[[str], Any]
    log_panel_event: Callable[..., None]


class ActionGuard:
    _inflight: set[tuple[str, str]] = set()
    _last_ts: dict[tuple[str, str], float] = {}

    @classmethod
    def try_enter(cls, user_id: str, action: str, cooldown_s: float = 1.0) -> tuple[bool, str | None]:
        key = (user_id, action)
        if key in cls._inflight:
            return False, "Ação em andamento"
        now = time.time()
        last = cls._last_ts.get(key)
        if last is not None and now - last < cooldown_s:
            return False, "Cooldown"
        cls._inflight.add(key)
        cls._last_ts[key] = now
        return True, None

    @classmethod
    def leave(cls, user_id: str, action: str) -> None:
        cls._inflight.discard((user_id, action))


class ConstrucoesView(discord.ui.View):
    def __init__(self, author_id: int, deps: PanelDeps):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.deps = deps

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Apenas o dono do painel pode usar estes botões.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⬅️ Voltar", style=discord.ButtonStyle.primary)
    async def btn_voltar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        embed = self.deps.build_dominio_embed(str(interaction.user.id))
        await interaction.response.edit_message(embed=embed, view=DominioView(author_id=interaction.user.id, deps=self.deps))

    @discord.ui.button(label="🛠️ Melhorar", style=discord.ButtonStyle.success)
    async def btn_melhorar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=self.deps.build_construcoes_embed(str(interaction.user.id), None),
            view=ConstrucoesUpgradeView(author_id=interaction.user.id, deps=self.deps),
        )

    @discord.ui.button(label="🔄 Reabrir Painel", style=discord.ButtonStyle.secondary)
    async def btn_reabrir(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=self.deps.build_dominio_embed(str(interaction.user.id)),
            view=DominioView(author_id=interaction.user.id, deps=self.deps),
        )


class UpgradeSelect(discord.ui.Select):
    def __init__(self, deps: PanelDeps) -> None:
        self.deps = deps
        options = [
            discord.SelectOption(label="Celeiros", value="celeiros", description="Melhora economia por hora"),
            discord.SelectOption(label="Casernas", value="casernas", description="Melhora treino militar"),
            discord.SelectOption(label="Forja", value="forja", description="Melhora achados e bônus"),
        ]
        super().__init__(placeholder="Escolha a construção para melhorar", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        estrutura = self.values[0]
        msg = self.deps.service.do_upgrade(str(interaction.user.id), estrutura)
        embed = self.deps.build_construcoes_embed(str(interaction.user.id), msg)
        await interaction.response.edit_message(
            embed=embed,
            view=ConstrucoesUpgradeView(author_id=interaction.user.id, deps=self.deps),
        )


class ConstrucoesUpgradeView(discord.ui.View):
    def __init__(self, author_id: int, deps: PanelDeps):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.deps = deps
        self.add_item(UpgradeSelect(deps))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Apenas o dono do painel pode usar estes botões.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⬅️ Voltar", style=discord.ButtonStyle.primary)
    async def btn_back(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=self.deps.build_construcoes_embed(str(interaction.user.id), None),
            view=ConstrucoesView(author_id=interaction.user.id, deps=self.deps),
        )

    @discord.ui.button(label="🔄 Reabrir Painel", style=discord.ButtonStyle.secondary)
    async def btn_reabrir(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=self.deps.build_dominio_embed(str(interaction.user.id)),
            view=DominioView(author_id=interaction.user.id, deps=self.deps),
        )


class DoctrineSelect(discord.ui.Select):
    def __init__(self, deps: PanelDeps) -> None:
        self.deps = deps
        options = [
            discord.SelectOption(label="Cerco", value="cerco"),
            discord.SelectOption(label="Choque", value="choque"),
            discord.SelectOption(label="Furtivo", value="furtivo"),
            discord.SelectOption(label="Arcano", value="arcano"),
        ]
        super().__init__(placeholder="Selecione a doutrina", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        msg = self.deps.service.do_set_doctrine(str(interaction.user.id), self.values[0])
        await interaction.response.edit_message(
            embed=self.deps.build_militar_embed(str(interaction.user.id), msg),
            view=MilitarView(author_id=interaction.user.id, deps=self.deps),
        )


class GeneralEquipSelect(discord.ui.Select):
    def __init__(self, user_id: str, deps: PanelDeps) -> None:
        self.deps = deps
        with self.deps.get_conn() as conn:
            generals = conn.execute("SELECT id, name FROM generals WHERE user_id = ? ORDER BY id DESC LIMIT 25", (user_id,)).fetchall()
        options = [discord.SelectOption(label=f"{g['name']} (id {g['id']})", value=str(g["id"])) for g in generals]
        if not options:
            options = [discord.SelectOption(label="Sem generais recrutados", value="none", default=True)]
        super().__init__(placeholder="Equipar general", min_values=1, max_values=1, options=options, disabled=(options[0].value == "none"))

    async def callback(self, interaction: discord.Interaction) -> None:
        value = self.values[0]
        if value == "none":
            await interaction.response.send_message("❌ Nenhum general disponível.", ephemeral=True)
            return
        msg = self.deps.service.do_equip_general(str(interaction.user.id), int(value))
        await interaction.response.edit_message(
            embed=self.deps.build_militar_embed(str(interaction.user.id), msg),
            view=MilitarView(author_id=interaction.user.id, deps=self.deps),
        )


class StrategistEquipSelect(discord.ui.Select):
    def __init__(self, user_id: str, deps: PanelDeps) -> None:
        self.deps = deps
        with self.deps.get_conn() as conn:
            strategists = conn.execute(
                "SELECT id, name FROM strategists WHERE user_id = ? ORDER BY id DESC LIMIT 25", (user_id,)
            ).fetchall()
        options = [discord.SelectOption(label=f"{s['name']} (id {s['id']})", value=str(s["id"])) for s in strategists]
        if not options:
            options = [discord.SelectOption(label="Sem estrategistas recrutados", value="none", default=True)]
        super().__init__(
            placeholder="Equipar estrategista",
            min_values=1,
            max_values=1,
            options=options,
            disabled=(options[0].value == "none"),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        value = self.values[0]
        if value == "none":
            await interaction.response.send_message("❌ Nenhum estrategista disponível.", ephemeral=True)
            return
        msg = self.deps.service.do_equip_strategist(str(interaction.user.id), int(value))
        await interaction.response.edit_message(
            embed=self.deps.build_militar_embed(str(interaction.user.id), msg),
            view=MilitarView(author_id=interaction.user.id, deps=self.deps),
        )


class MilitarView(discord.ui.View):
    def __init__(self, author_id: int, deps: PanelDeps):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.deps = deps
        user_id = str(author_id)
        self.add_item(DoctrineSelect(deps))
        self.add_item(GeneralEquipSelect(user_id, deps))
        self.add_item(StrategistEquipSelect(user_id, deps))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Apenas o dono do painel pode usar estes botões.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🎖️ Recrutar General", style=discord.ButtonStyle.success)
    async def btn_recrutar_general(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        msg = self.deps.service.do_recruit_general_auto(str(interaction.user.id))
        await interaction.response.edit_message(
            embed=self.deps.build_militar_embed(str(interaction.user.id), msg),
            view=MilitarView(author_id=interaction.user.id, deps=self.deps),
        )

    @discord.ui.button(label="📐 Recrutar Estrategista", style=discord.ButtonStyle.secondary)
    async def btn_recrutar_strategista(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        msg = self.deps.service.do_recruit_strategist_auto(str(interaction.user.id))
        await interaction.response.edit_message(
            embed=self.deps.build_militar_embed(str(interaction.user.id), msg),
            view=MilitarView(author_id=interaction.user.id, deps=self.deps),
        )

    @discord.ui.button(label="⬅️ Voltar", style=discord.ButtonStyle.primary)
    async def btn_back(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=self.deps.build_dominio_embed(str(interaction.user.id)),
            view=DominioView(author_id=interaction.user.id, deps=self.deps),
        )

    @discord.ui.button(label="🔄 Reabrir Painel", style=discord.ButtonStyle.secondary)
    async def btn_reabrir(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=self.deps.build_dominio_embed(str(interaction.user.id)),
            view=DominioView(author_id=interaction.user.id, deps=self.deps),
        )


class OperationSelect(discord.ui.Select):
    def __init__(self, user_id: str, deps: PanelDeps) -> None:
        self.deps = deps
        d = deps.get_or_create_domain(user_id)
        with deps.get_conn() as conn:
            ops = conn.execute(
                "SELECT key, title, min_barracks_level, requires_general, requires_strategist, partial_without_strategist "
                "FROM operations ORDER BY id"
            ).fetchall()
        options: list[discord.SelectOption] = []
        for op in ops:
            min_barracks_level = int(op["min_barracks_level"] or 1)
            requires_general = int(op["requires_general"] or 0)
            requires_strategist = int(op["requires_strategist"] or 0)
            partial_without_strategist = int(op["partial_without_strategist"] or 0)

            desc = "Disponível"
            if d["barracks_level"] < min_barracks_level:
                desc = f"Requer Casernas T{min_barracks_level}+"
            elif requires_general and not d["general_id"]:
                desc = "Requer general equipado"
            elif requires_strategist and not d["strategist_id"]:
                desc = "Rota parcial sem estrategista" if partial_without_strategist else "Requer estrategista equipado"
            options.append(discord.SelectOption(label=op["title"], value=op["key"], description=desc[:100]))
        if not options:
            options = [discord.SelectOption(label="Sem operações", value="none")]
        super().__init__(placeholder="Selecionar operação para simular", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        value = self.values[0]
        try:
            if value == "none":
                await interaction.response.send_message("❌ Nenhuma operação cadastrada.", ephemeral=True)
                return

            msg = self.deps.service.do_simular_operacao(user_id, value)
            self.deps.log_panel_event(
                user_id=user_id,
                guild_id=guild_id,
                event_name="panel_action",
                event_action=f"operacao_select:{value}",
            )
            if msg.startswith("❌"):
                self.deps.log_panel_event(
                    user_id=user_id,
                    guild_id=guild_id,
                    event_name="panel_error",
                    event_action=f"operacao_select:{value}",
                    error_code="requirement_missing" if "Requisito ausente" in msg else "action_error",
                )

            await interaction.response.edit_message(
                embed=self.deps.build_operacoes_embed(user_id, msg),
                view=OperacoesView(author_id=interaction.user.id, deps=self.deps),
            )
        except Exception as exc:
            self.deps.log_panel_event(
                user_id=user_id,
                guild_id=guild_id,
                event_name="panel_error",
                event_action=f"operacao_select:{value}",
                error_code="interaction_failure",
            )
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"<@{interaction.user.id}> ❌ Falha ao processar operação. Use `!diagnostico` (admin).",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"<@{interaction.user.id}> ❌ Falha ao processar operação. Use `!diagnostico` (admin).",
                    ephemeral=True,
                )


class OperacoesView(discord.ui.View):
    def __init__(self, author_id: int, deps: PanelDeps):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.deps = deps
        self.add_item(OperationSelect(str(author_id), deps))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Apenas o dono do painel pode usar estes botões.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⬅️ Voltar", style=discord.ButtonStyle.primary)
    async def btn_back(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=self.deps.build_dominio_embed(str(interaction.user.id)),
            view=DominioView(author_id=interaction.user.id, deps=self.deps),
        )

    @discord.ui.button(label="🔄 Reabrir Painel", style=discord.ButtonStyle.secondary)
    async def btn_reabrir(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=self.deps.build_dominio_embed(str(interaction.user.id)),
            view=DominioView(author_id=interaction.user.id, deps=self.deps),
        )


class DominioView(discord.ui.View):
    def __init__(self, author_id: int, deps: PanelDeps):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.deps = deps

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            self.deps.log_panel_event(
                user_id=str(interaction.user.id),
                guild_id=str(interaction.guild_id) if interaction.guild_id else None,
                event_name="panel_error",
                event_action="interaction_check",
                error_code="not_panel_owner",
            )
            await interaction.response.send_message("❌ Apenas o dono do painel pode usar estes botões.", ephemeral=True)
            return False
        return True

    def _log_action_result(self, *, user_id: str, guild_id: str | None, action: str, message: str) -> None:
        self.deps.log_panel_event(
            user_id=user_id,
            guild_id=guild_id,
            event_name="panel_action",
            event_action=action,
        )
        if message.startswith("❌"):
            error_code = "action_error"
            if "Requisito ausente" in message:
                error_code = "requirement_missing"
            elif "Cooldown" in message:
                error_code = "cooldown"
            self.deps.log_panel_event(
                user_id=user_id,
                guild_id=guild_id,
                event_name="panel_error",
                event_action=action,
                error_code=error_code,
            )

    def _guard(self, *, user_id: str, guild_id: str | None, action: str, cooldown_s: float) -> tuple[bool, str | None]:
        ok, reason = ActionGuard.try_enter(user_id, action, cooldown_s=cooldown_s)
        if not ok:
            self.deps.log_panel_event(
                user_id=user_id,
                guild_id=guild_id,
                event_name="panel_error",
                event_action=action,
                error_code="action_lock" if reason == "Ação em andamento" else "cooldown",
            )
            return False, reason
        return True, None

    @discord.ui.button(label="Resgatar", style=discord.ButtonStyle.success)
    async def btn_resgatar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        ok, reason = self._guard(user_id=user_id, guild_id=guild_id, action="resgatar", cooldown_s=1.5)
        if not ok:
            await interaction.response.send_message(f"❌ {reason}. Aguarde e tente novamente.", ephemeral=True)
            return
        try:
            msg = self.deps.service.do_collect(str(interaction.user.id))
            self._log_action_result(
                user_id=user_id,
                guild_id=guild_id,
                action="resgatar",
                message=msg,
            )
            await interaction.response.send_message(msg, ephemeral=True)
        finally:
            ActionGuard.leave(user_id, "resgatar")

    @discord.ui.button(label="Treinar", style=discord.ButtonStyle.primary)
    async def btn_treinar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        ok, reason = self._guard(user_id=user_id, guild_id=guild_id, action="treinar", cooldown_s=1.5)
        if not ok:
            await interaction.response.send_message(f"❌ {reason}. Aguarde e tente novamente.", ephemeral=True)
            return
        try:
            msg = self.deps.service.do_train(str(interaction.user.id))
            self._log_action_result(
                user_id=user_id,
                guild_id=guild_id,
                action="treinar",
                message=msg,
            )
            await interaction.response.send_message(msg, ephemeral=True)
        finally:
            ActionGuard.leave(user_id, "treinar")

    @discord.ui.button(label="Construções", style=discord.ButtonStyle.secondary)
    async def btn_construcoes(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        ok, reason = self._guard(user_id=user_id, guild_id=guild_id, action="construcoes", cooldown_s=0.75)
        if not ok:
            await interaction.response.send_message(f"❌ {reason}. Aguarde e tente novamente.", ephemeral=True)
            return
        try:
            self.deps.log_panel_event(
                user_id=user_id,
                guild_id=guild_id,
                event_name="panel_action",
                event_action="construcoes",
            )
            embed = self.deps.build_construcoes_embed(user_id, None)
            await interaction.response.edit_message(embed=embed, view=ConstrucoesView(author_id=interaction.user.id, deps=self.deps))
        finally:
            ActionGuard.leave(user_id, "construcoes")

    @discord.ui.button(label="Militar", style=discord.ButtonStyle.secondary)
    async def btn_militar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        ok, reason = self._guard(user_id=user_id, guild_id=guild_id, action="militar", cooldown_s=0.75)
        if not ok:
            await interaction.response.send_message(f"❌ {reason}. Aguarde e tente novamente.", ephemeral=True)
            return
        try:
            self.deps.log_panel_event(
                user_id=user_id,
                guild_id=guild_id,
                event_name="panel_action",
                event_action="militar",
            )
            await interaction.response.edit_message(
                embed=self.deps.build_militar_embed(user_id, None),
                view=MilitarView(author_id=interaction.user.id, deps=self.deps),
            )
        finally:
            ActionGuard.leave(user_id, "militar")

    @discord.ui.button(label="Operações", style=discord.ButtonStyle.secondary)
    async def btn_operacoes(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        ok, reason = self._guard(user_id=user_id, guild_id=guild_id, action="operacoes", cooldown_s=0.75)
        if not ok:
            await interaction.response.send_message(f"❌ {reason}. Aguarde e tente novamente.", ephemeral=True)
            return
        try:
            self.deps.log_panel_event(
                user_id=user_id,
                guild_id=guild_id,
                event_name="panel_action",
                event_action="operacoes",
            )
            await interaction.response.edit_message(
                embed=self.deps.build_operacoes_embed(user_id, None),
                view=OperacoesView(author_id=interaction.user.id, deps=self.deps),
            )
        finally:
            ActionGuard.leave(user_id, "operacoes")

    @discord.ui.button(label="Rank", style=discord.ButtonStyle.secondary)
    async def btn_rank(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        ok, reason = self._guard(user_id=user_id, guild_id=guild_id, action="rank", cooldown_s=0.75)
        if not ok:
            await interaction.response.send_message(f"❌ {reason}. Aguarde e tente novamente.", ephemeral=True)
            return
        try:
            self.deps.log_panel_event(
                user_id=user_id,
                guild_id=guild_id,
                event_name="panel_action",
                event_action="rank",
            )
            await interaction.response.send_message(
                content="✅ Painel de rank aberto.\nΔ Tops de riqueza/poder atualizados\nPróximo: volte ao domínio e execute Resgatar/Treinar para subir.",
                embed=self.deps.build_rank_embed(),
                ephemeral=True,
            )
        finally:
            ActionGuard.leave(user_id, "rank")
