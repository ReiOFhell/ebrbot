from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from logging import Logger
import random
import sqlite3
from typing import Callable
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

TZ_BR = ZoneInfo("America/Sao_Paulo")
TICKET_PRICE = 50_000
MAX_TICKETS_PER_USER_PER_RAFFLE = 1000

RAFFLE_TYPES: dict[str, str] = {
    "r": "relampago",
    "d": "diaria",
    "a": "admin",
}
RAFFLE_TYPE_ALIASES = {
    "relampago": "relampago",
    "diaria": "diaria",
    "admin": "admin",
    "a": "admin",
    "r": "relampago",
    "d": "diaria",
}
RAFFLE_TITLES = {
    "relampago": "🎲 NEXAR | Rifa Relâmpago",
    "diaria": "🎲 NEXAR | Rifa Diária",
    "admin": "🛠️ NEXAR | Rifa Admin (Teste)",
}


@dataclass
class RaffleDeps:
    get_conn: Callable[[], sqlite3.Connection]
    get_or_create_domain: Callable[[str], sqlite3.Row]
    now_ts: Callable[[], int]
    logger: Logger


class RaffleService:
    def __init__(self, deps: RaffleDeps):
        self.deps = deps

    def init_db(self) -> None:
        with self.deps.get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS raffles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT NOT NULL,
                    round_no INTEGER NOT NULL,
                    start_ts INTEGER NOT NULL,
                    end_ts INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    total_tickets INTEGER NOT NULL DEFAULT 0,
                    participants_total INTEGER NOT NULL DEFAULT 0,
                    total_pot INTEGER NOT NULL DEFAULT 0,
                    winner_id TEXT,
                    winner_tickets INTEGER,
                    closed_at_ts INTEGER,
                    created_at_ts INTEGER NOT NULL,
                    updated_at_ts INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS raffle_entries (
                    raffle_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    tickets INTEGER NOT NULL DEFAULT 0,
                    spent_gold INTEGER NOT NULL DEFAULT 0,
                    updated_at_ts INTEGER NOT NULL,
                    PRIMARY KEY(raffle_id, user_id),
                    FOREIGN KEY(raffle_id) REFERENCES raffles(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS raffle_runtime (
                    tipo TEXT PRIMARY KEY,
                    last_guild_id TEXT,
                    last_channel_id TEXT,
                    updated_at_ts INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS raffle_state (
                    tipo TEXT PRIMARY KEY,
                    last_winner_id TEXT,
                    last_winner_name TEXT,
                    last_prize INTEGER NOT NULL DEFAULT 0,
                    last_closed_ts INTEGER,
                    updated_at_ts INTEGER NOT NULL
                )
                """
            )

            conn.execute("CREATE INDEX IF NOT EXISTS idx_raffles_tipo_status_end ON raffles(tipo, status, end_ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_raffles_status_end ON raffles(status, end_ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_raffle_entries_user ON raffle_entries(user_id)")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_raffles_active_tipo ON raffles(tipo) WHERE status = 'active'")

            now = self.deps.now_ts()
            for tipo in RAFFLE_TITLES:
                self._ensure_active_raffle(conn, tipo, now)
                conn.execute(
                    "INSERT OR IGNORE INTO raffle_state (tipo, last_prize, updated_at_ts) VALUES (?, 0, ?)",
                    (tipo, now),
                )
            conn.commit()

    def _normalize_tipo(self, raw: str) -> str | None:
        return RAFFLE_TYPE_ALIASES.get(raw.strip().lower())

    def _next_end_ts(self, tipo: str, now_ts: int) -> int:
        now_br = datetime.fromtimestamp(now_ts, tz=TZ_BR)
        if tipo == "relampago":
            return int((now_br + timedelta(minutes=25)).timestamp())
        if tipo == "admin":
            return int((now_br + timedelta(minutes=1)).timestamp())
        nxt = (now_br + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return int(nxt.timestamp())

    def _ensure_active_raffle(self, conn: sqlite3.Connection, tipo: str, now: int) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM raffles WHERE tipo = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (tipo,),
        ).fetchone()
        if row:
            return row
        round_no = int(
            conn.execute("SELECT COALESCE(MAX(round_no), 0) n FROM raffles WHERE tipo = ?", (tipo,)).fetchone()["n"]
        )
        conn.execute(
            """
            INSERT INTO raffles (
                tipo, round_no, start_ts, end_ts, status,
                total_tickets, participants_total, total_pot,
                created_at_ts, updated_at_ts
            ) VALUES (?, ?, ?, ?, 'active', 0, 0, 0, ?, ?)
            """,
            (tipo, round_no + 1, now, self._next_end_ts(tipo, now), now, now),
        )
        return conn.execute("SELECT * FROM raffles WHERE id = last_insert_rowid()").fetchone()

    def _record_runtime_channel(self, conn: sqlite3.Connection, tipo: str, guild_id: str | None, channel_id: str | None) -> None:
        conn.execute(
            """
            INSERT INTO raffle_runtime (tipo, last_guild_id, last_channel_id, updated_at_ts)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tipo) DO UPDATE SET
                last_guild_id = excluded.last_guild_id,
                last_channel_id = excluded.last_channel_id,
                updated_at_ts = excluded.updated_at_ts
            """,
            (tipo, guild_id, channel_id, self.deps.now_ts()),
        )

    def buy_tickets(
        self,
        *,
        user_id: str,
        tipo_raw: str,
        quantity: int,
        guild_id: str | None,
        channel_id: str | None,
        is_admin: bool,
    ) -> tuple[bool, str]:
        tipo = self._normalize_tipo(tipo_raw)
        if not tipo:
            return False, "❌ Tipo inválido. Use r, d ou a/admin."
        if tipo == "admin" and not is_admin:
            return False, "❌ A rifa admin é exclusiva para administradores."
        if quantity <= 0:
            return False, "❌ Quantidade inválida. Use inteiro > 0."

        self.deps.get_or_create_domain(user_id)
        now = self.deps.now_ts()

        with self.deps.get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            raffle = self._ensure_active_raffle(conn, tipo, now)

            current = conn.execute(
                "SELECT tickets FROM raffle_entries WHERE raffle_id = ? AND user_id = ?",
                (raffle["id"], user_id),
            ).fetchone()
            mine_before = int(current["tickets"] if current else 0)
            remaining = MAX_TICKETS_PER_USER_PER_RAFFLE - mine_before
            if remaining <= 0:
                conn.commit()
                return False, "❌ Limite atingido: 1000/1000 tickets nesta rifa."
            if quantity > remaining:
                conn.commit()
                return False, f"❌ Limite excedido. Você ainda pode comprar **{remaining}** tickets."

            cost = quantity * TICKET_PRICE
            gold_row = conn.execute("SELECT gold FROM resources WHERE user_id = ?", (user_id,)).fetchone()
            gold = int(gold_row["gold"] if gold_row else 0)
            if gold < cost:
                conn.commit()
                return False, f"❌ Ouro insuficiente. Custo: {cost:,} | Falta: {cost-gold:,}".replace(",", ".")

            conn.execute("UPDATE resources SET gold = gold - ?, updated_at_ts = ? WHERE user_id = ?", (cost, now, user_id))
            conn.execute(
                """
                INSERT INTO raffle_entries (raffle_id, user_id, tickets, spent_gold, updated_at_ts)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(raffle_id, user_id) DO UPDATE SET
                    tickets = tickets + excluded.tickets,
                    spent_gold = spent_gold + excluded.spent_gold,
                    updated_at_ts = excluded.updated_at_ts
                """,
                (raffle["id"], user_id, quantity, cost, now),
            )
            participants_total = int(
                conn.execute(
                    "SELECT COUNT(*) c FROM raffle_entries WHERE raffle_id = ? AND tickets > 0",
                    (raffle["id"],),
                ).fetchone()["c"]
            )
            conn.execute(
                """
                UPDATE raffles
                SET total_tickets = total_tickets + ?,
                    total_pot = total_pot + ?,
                    participants_total = ?,
                    updated_at_ts = ?
                WHERE id = ?
                """,
                (quantity, cost, participants_total, now, raffle["id"]),
            )
            self._record_runtime_channel(conn, tipo, guild_id, channel_id)

            updated = conn.execute(
                "SELECT total_tickets, total_pot, end_ts FROM raffles WHERE id = ?",
                (raffle["id"],),
            ).fetchone()
            mine_after = int(
                conn.execute(
                    "SELECT tickets FROM raffle_entries WHERE raffle_id = ? AND user_id = ?",
                    (raffle["id"], user_id),
                ).fetchone()["tickets"]
            )
            conn.commit()

        total_tickets = int(updated["total_tickets"])
        chance = (mine_after / total_tickets * 100.0) if total_tickets > 0 else 0.0
        return True, (
            f"✅ Aposta confirmada: +{quantity} tickets\n"
            f"💰 Δ Ouro: -{cost:,}\n"
            f"🎟️ Seus tickets: {mine_after}/1000\n"
            f"📊 Sua chance agora: {chance:.2f}%\n"
            f"⏳ Resultado: <t:{int(updated['end_ts'])}:R>"
        ).replace(",", ".")

    def get_panel_data(self, *, tipo_raw: str, user_id: str, guild_id: str | None, channel_id: str | None) -> dict[str, object] | None:
        tipo = self._normalize_tipo(tipo_raw)
        if not tipo:
            return None
        self.deps.get_or_create_domain(user_id)

        with self.deps.get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            raffle = self._ensure_active_raffle(conn, tipo, self.deps.now_ts())
            self._record_runtime_channel(conn, tipo, guild_id, channel_id)

            my_row = conn.execute(
                "SELECT tickets FROM raffle_entries WHERE raffle_id = ? AND user_id = ?",
                (raffle["id"], user_id),
            ).fetchone()
            my_tickets = int(my_row["tickets"] if my_row else 0)
            total_tickets = int(raffle["total_tickets"])
            chance = (my_tickets / total_tickets * 100.0) if total_tickets > 0 else 0.0

            state = conn.execute(
                "SELECT last_winner_id, last_winner_name, last_prize FROM raffle_state WHERE tipo = ?",
                (tipo,),
            ).fetchone()
            conn.commit()

        return {
            "tipo": tipo,
            "title": RAFFLE_TITLES[tipo],
            "end_ts": int(raffle["end_ts"]),
            "total_tickets": total_tickets,
            "participants_total": int(raffle["participants_total"]),
            "total_pot": int(raffle["total_pot"]),
            "my_tickets": my_tickets,
            "chance": chance,
            "last_winner_id": str(state["last_winner_id"]) if state and state["last_winner_id"] else None,
            "last_winner_name": str(state["last_winner_name"]) if state and state["last_winner_name"] else None,
            "last_prize": int(state["last_prize"]) if state else 0,
        }

    def settle_expired_raffles(self) -> list[dict[str, object]]:
        now = self.deps.now_ts()
        settlements: list[dict[str, object]] = []

        with self.deps.get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            expired = conn.execute(
                "SELECT * FROM raffles WHERE status = 'active' AND end_ts <= ? ORDER BY end_ts ASC",
                (now,),
            ).fetchall()

            for raffle in expired:
                raffle_id = int(raffle["id"])
                tipo = str(raffle["tipo"])
                locked = conn.execute(
                    "UPDATE raffles SET status = 'closing', updated_at_ts = ? WHERE id = ? AND status = 'active'",
                    (now, raffle_id),
                ).rowcount
                if locked == 0:
                    continue

                entries = conn.execute(
                    "SELECT user_id, tickets FROM raffle_entries WHERE raffle_id = ? AND tickets > 0 ORDER BY user_id",
                    (raffle_id,),
                ).fetchall()
                participants = [{"user_id": str(e["user_id"]), "tickets": int(e["tickets"])} for e in entries]
                total_tickets = int(raffle["total_tickets"])
                total_pot = int(raffle["total_pot"])
                participants_total = len(participants)

                winner_id: str | None = None
                winner_name: str | None = None
                winner_tickets = 0

                if total_tickets > 0 and total_pot > 0 and participants:
                    pick = random.randint(1, total_tickets)
                    acc = 0
                    for p in participants:
                        acc += int(p["tickets"])
                        if pick <= acc:
                            winner_id = str(p["user_id"])
                            winner_tickets = int(p["tickets"])
                            break
                    if winner_id:
                        conn.execute(
                            "UPDATE resources SET gold = gold + ?, updated_at_ts = ? WHERE user_id = ?",
                            (total_pot, now, winner_id),
                        )
                        winner_name = winner_id

                conn.execute(
                    """
                    UPDATE raffles
                    SET status = 'closed',
                        winner_id = ?,
                        winner_tickets = ?,
                        participants_total = ?,
                        closed_at_ts = ?,
                        updated_at_ts = ?
                    WHERE id = ?
                    """,
                    (winner_id, winner_tickets, participants_total, now, now, raffle_id),
                )
                conn.execute(
                    """
                    INSERT INTO raffle_state (tipo, last_winner_id, last_winner_name, last_prize, last_closed_ts, updated_at_ts)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tipo) DO UPDATE SET
                        last_winner_id = excluded.last_winner_id,
                        last_winner_name = excluded.last_winner_name,
                        last_prize = excluded.last_prize,
                        last_closed_ts = excluded.last_closed_ts,
                        updated_at_ts = excluded.updated_at_ts
                    """,
                    (tipo, winner_id, winner_name, total_pot, now, now),
                )

                rt = conn.execute(
                    "SELECT last_channel_id FROM raffle_runtime WHERE tipo = ?",
                    (tipo,),
                ).fetchone()

                settlements.append(
                    {
                        "tipo": tipo,
                        "title": RAFFLE_TITLES[tipo],
                        "winner_id": winner_id,
                        "winner_name": winner_name,
                        "winner_tickets": winner_tickets,
                        "total_tickets": total_tickets,
                        "total_pot": total_pot,
                        "participants_total": participants_total,
                        "participants": participants,
                        "channel_id": str(rt["last_channel_id"]) if rt and rt["last_channel_id"] else None,
                    }
                )

                self._ensure_active_raffle(conn, tipo, now)

            conn.commit()
        return settlements


def build_raffle_embed(data: dict[str, object], *, tipo_alias: str) -> discord.Embed:
    tipo = str(data["tipo"])
    end_ts = int(data["end_ts"])
    total_tickets = int(data["total_tickets"])
    my_tickets = int(data["my_tickets"])
    chance = float(data["chance"])

    if data["last_winner_id"]:
        last_line = f"{data['last_winner_name']} ({data['last_winner_id']}) (+{int(data['last_prize']):,} ouro)".replace(",", ".")
    else:
        last_line = "Nenhum ainda."

    embed = discord.Embed(title=str(data["title"]), color=discord.Color.gold())
    embed.add_field(name="💰 Prêmio atual", value=f"{int(data['total_pot']):,} ouro".replace(",", "."), inline=True)
    embed.add_field(name="🎟️ Tickets totais", value=f"{total_tickets:,} tickets".replace(",", "."), inline=True)
    embed.add_field(name="👥 Participantes", value=str(int(data["participants_total"])), inline=True)
    embed.add_field(name="🧾 Seus tickets", value=f"{my_tickets}/1000", inline=True)
    embed.add_field(name="📊 Sua chance atual", value=f"{chance:.2f}%", inline=True)
    embed.add_field(name="🤑 Último ganhador", value=last_line, inline=False)
    embed.add_field(name="⏳ Resultado", value=f"<t:{end_ts}:F> • <t:{end_ts}:R>", inline=False)
    embed.add_field(
        name="🛒 Comprar",
        value=(
            f"`!rifa b {tipo_alias} 10` / `!rifa buy {tipo_alias} 10`"
        ),
        inline=False,
    )
    embed.set_footer(text="Ticket: 50.000 ouro • Limite: 1000 por pessoa/por rifa • 1 vencedor")
    return embed


class RaffleLoop:
    def __init__(self, bot: commands.Bot, service: RaffleService, logger: Logger):
        self.bot = bot
        self.service = service
        self.logger = logger

    async def _notify_participants_dm(self, settlement: dict[str, object]) -> bool:
        total_tickets = int(settlement["total_tickets"])
        if total_tickets <= 0:
            return False

        winner_id = str(settlement["winner_id"]) if settlement["winner_id"] else None
        dm_failed = False
        for p in settlement["participants"]:
            user_id = str(p["user_id"])
            tickets = int(p["tickets"])
            chance = (tickets / total_tickets) * 100.0
            won = winner_id is not None and user_id == winner_id
            result_line = f"✅ VOCÊ GANHOU +{int(settlement['total_pot']):,} ouro" if won else f"❌ você não foi escolhido; vencedor foi <@{winner_id}>"
            msg = (
                f"🎲 A rifa acabou!\n"
                f"Rifa: {settlement['title']}\n"
                f"Seus tickets: {tickets}\n"
                f"Sua chance final: {chance:.2f}% ({tickets}/{total_tickets})\n"
                f"{result_line}"
            ).replace(",", ".")
            user = self.bot.get_user(int(user_id))
            if user is None:
                try:
                    user = await self.bot.fetch_user(int(user_id))
                except Exception:
                    dm_failed = True
                    continue
            try:
                await user.send(msg)
            except Exception:
                dm_failed = True
        return dm_failed

    async def _announce_channel(self, settlement: dict[str, object], dm_failed: bool) -> None:
        channel_id = settlement.get("channel_id")
        if not channel_id:
            return
        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                return
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        winner = f"<@{settlement['winner_id']}>" if settlement["winner_id"] else "Sem vencedor"
        embed = discord.Embed(title="🎉 Rifa encerrada!", color=discord.Color.dark_gold())
        embed.add_field(name="Rifa", value=str(settlement["title"]), inline=False)
        embed.add_field(name="Vencedor", value=winner, inline=True)
        embed.add_field(name="Prêmio", value=f"{int(settlement['total_pot']):,} ouro".replace(",", "."), inline=True)
        embed.add_field(name="Participantes", value=str(int(settlement["participants_total"])), inline=True)
        embed.add_field(name="Tickets totais", value=f"{int(settlement['total_tickets']):,}".replace(",", "."), inline=True)
        await channel.send(embed=embed)
        if dm_failed:
            await channel.send("📩 Não consegui enviar DM para alguns participantes.")

    @tasks.loop(seconds=30)
    async def raffle_scheduler(self) -> None:
        settlements = self.service.settle_expired_raffles()
        for settlement in settlements:
            self.logger.info(
                "Rifa encerrada | tipo=%s vencedor=%s premio=%s",
                settlement["tipo"],
                settlement["winner_id"] or "nenhum",
                settlement["total_pot"],
            )
            dm_failed = await self._notify_participants_dm(settlement)
            await self._announce_channel(settlement, dm_failed)

    @raffle_scheduler.before_loop
    async def before_raffle_scheduler(self) -> None:
        await self.bot.wait_until_ready()

    def start(self) -> None:
        if not self.raffle_scheduler.is_running():
            self.raffle_scheduler.start()


def setup_bets(
    *,
    bot: commands.Bot,
    get_conn: Callable[[], sqlite3.Connection],
    get_or_create_domain: Callable[[str], sqlite3.Row],
    update_player_state: Callable[..., None],
    now_ts: Callable[[], int],
    logger: Logger,
) -> tuple[RaffleService, RaffleLoop]:
    del update_player_state
    deps = RaffleDeps(get_conn=get_conn, get_or_create_domain=get_or_create_domain, now_ts=now_ts, logger=logger)
    service = RaffleService(deps)
    service.init_db()
    loop = RaffleLoop(bot=bot, service=service, logger=logger)

    @bot.command(name="rifa")
    async def rifa(ctx: commands.Context, *args: str) -> None:
        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild.id) if ctx.guild else None
        channel_id = str(ctx.channel.id) if ctx.channel else None
        is_admin = bool(ctx.guild and ctx.author.guild_permissions.administrator)

        if not args:
            entries = [("r", "relampago"), ("d", "diaria")]
            if is_admin:
                entries.append(("a", "admin"))
            embeds = [
                build_raffle_embed(
                    service.get_panel_data(tipo_raw=tipo, user_id=user_id, guild_id=guild_id, channel_id=channel_id),
                    tipo_alias=alias,
                )
                for alias, tipo in entries
            ]
            await ctx.send(content=f"<@{ctx.author.id}>", embeds=embeds)
            return

        first = args[0].lower()
        if first in {"b", "buy"}:
            if len(args) < 3:
                await ctx.send("Uso: `!rifa b <r|d|a> <quantidade>` ou `!rifa buy <r|d|admin> <quantidade>`")
                return
            tipo_raw = args[1]
            try:
                quantity = int(args[2])
            except ValueError:
                await ctx.send("❌ Quantidade inválida. Use inteiro > 0.")
                return

            ok, msg = service.buy_tickets(
                user_id=user_id,
                tipo_raw=tipo_raw,
                quantity=quantity,
                guild_id=guild_id,
                channel_id=channel_id,
                is_admin=is_admin,
            )
            await ctx.send(f"<@{ctx.author.id}>\n{msg}" if ok else f"<@{ctx.author.id}> {msg}")
            return

        # painel direto: !rifa r / !rifa d / !rifa a
        panel = service.get_panel_data(tipo_raw=first, user_id=user_id, guild_id=guild_id, channel_id=channel_id)
        if panel is None:
            await ctx.send("❌ Uso: `!rifa`, `!rifa r`, `!rifa d`, `!rifa a`, `!rifa b <tipo> <qtd>`, `!rifa buy <tipo> <qtd>`")
            return
        if panel["tipo"] == "admin" and not is_admin:
            await ctx.send("❌ A rifa admin é exclusiva para administradores.")
            return
        alias = "r" if panel["tipo"] == "relampago" else ("d" if panel["tipo"] == "diaria" else "a")
        await ctx.send(content=f"<@{ctx.author.id}>", embed=build_raffle_embed(panel, tipo_alias=alias))

    @bot.command(name="rifas")
    async def rifas(ctx: commands.Context) -> None:
        await rifa(ctx)

    return service, loop
