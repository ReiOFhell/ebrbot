from __future__ import annotations

import asyncio
import random
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from logging import Logger
from typing import Callable
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

TZ_BR = ZoneInfo("America/Sao_Paulo")
TICKET_PRICE = 50_000
MAX_TICKETS_PER_USER_PER_RAFFLE = 1000
CHECK_INTERVAL_SECONDS = 60

RAFFLE_TYPES: dict[str, str] = {
    "r": "relampago",
    "s": "sequencial",
    "d": "diaria",
    "w": "semanal",
    "m": "mensal",
    "t": "trimestral",
}
RAFFLE_LABELS = {
    "relampago": "Relâmpago",
    "sequencial": "Sequencial",
    "diaria": "Diária",
    "semanal": "Semanal",
    "mensal": "Mensal",
    "trimestral": "Trimestral",
}


@dataclass
class RaffleDeps:
    get_conn: Callable[[], sqlite3.Connection]
    get_or_create_domain: Callable[[str], sqlite3.Row]
    update_player_state: Callable[..., None]
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_raffles_tipo_status_end ON raffles(tipo, status, end_ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_raffles_status_end ON raffles(status, end_ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_raffle_entries_user ON raffle_entries(user_id)")

            now = self.deps.now_ts()
            for tipo in RAFFLE_LABELS:
                existing = conn.execute(
                    "SELECT id FROM raffles WHERE tipo = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
                    (tipo,),
                ).fetchone()
                if existing:
                    continue
                round_no = conn.execute(
                    "SELECT COALESCE(MAX(round_no), 0) n FROM raffles WHERE tipo = ?",
                    (tipo,),
                ).fetchone()["n"]
                end_ts = self._next_end_ts(tipo, now)
                conn.execute(
                    """
                    INSERT INTO raffles (tipo, round_no, start_ts, end_ts, status, created_at_ts, updated_at_ts)
                    VALUES (?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (tipo, int(round_no) + 1, now, end_ts, now, now),
                )
            conn.commit()

    def _from_alias(self, alias: str) -> str | None:
        return RAFFLE_TYPES.get(alias.strip().lower())

    def _next_end_ts(self, tipo: str, now_ts: int) -> int:
        now_br = datetime.fromtimestamp(now_ts, tz=TZ_BR)
        if tipo == "relampago":
            return int((now_br + timedelta(minutes=25)).timestamp())
        if tipo == "sequencial":
            return int((now_br + timedelta(hours=1)).timestamp())
        if tipo == "diaria":
            nxt = (now_br + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            return int(nxt.timestamp())
        if tipo == "semanal":
            days_until_sat = (5 - now_br.weekday()) % 7
            base = (now_br + timedelta(days=days_until_sat)).replace(hour=0, minute=0, second=0, microsecond=0)
            if base <= now_br:
                base += timedelta(days=7)
            return int(base.timestamp())
        if tipo == "mensal":
            year = now_br.year + (1 if now_br.month == 12 else 0)
            month = 1 if now_br.month == 12 else now_br.month + 1
            nxt = datetime(year, month, 1, 0, 0, 0, tzinfo=TZ_BR)
            return int(nxt.timestamp())
        # trimestral
        current_q = (now_br.month - 1) // 3
        end_month = (current_q + 1) * 3
        year = now_br.year
        if end_month == 12:
            nxt = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=TZ_BR)
        else:
            nxt = datetime(year, end_month + 1, 1, 0, 0, 0, tzinfo=TZ_BR)
        if nxt <= now_br:
            month = nxt.month + 3
            year = nxt.year
            while month > 12:
                month -= 12
                year += 1
            nxt = datetime(year, month, 1, 0, 0, 0, tzinfo=TZ_BR)
        return int(nxt.timestamp())

    @staticmethod
    def _fmt_ts(ts: int) -> str:
        return datetime.fromtimestamp(ts, tz=TZ_BR).strftime("%d/%m/%Y %H:%M (%Z)")

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

    def buy_tickets(self, *, user_id: str, tipo_alias: str, quantity: int, guild_id: str | None, channel_id: str | None) -> tuple[bool, str]:
        tipo = self._from_alias(tipo_alias)
        if not tipo:
            return False, "❌ Tipo inválido. Use: r, s, d, w, m, t."
        if quantity <= 0:
            return False, "❌ Quantidade inválida. Use um inteiro positivo."

        self.deps.get_or_create_domain(user_id)
        now = self.deps.now_ts()
        with self.deps.get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            raffle = conn.execute(
                "SELECT * FROM raffles WHERE tipo = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
                (tipo,),
            ).fetchone()
            if not raffle:
                round_no = conn.execute("SELECT COALESCE(MAX(round_no), 0) n FROM raffles WHERE tipo = ?", (tipo,)).fetchone()["n"]
                end_ts = self._next_end_ts(tipo, now)
                conn.execute(
                    "INSERT INTO raffles (tipo, round_no, start_ts, end_ts, status, created_at_ts, updated_at_ts) VALUES (?, ?, ?, ?, 'active', ?, ?)",
                    (tipo, int(round_no) + 1, now, end_ts, now, now),
                )
                raffle = conn.execute("SELECT * FROM raffles WHERE id = last_insert_rowid()").fetchone()

            entry = conn.execute(
                "SELECT tickets FROM raffle_entries WHERE raffle_id = ? AND user_id = ?",
                (raffle["id"], user_id),
            ).fetchone()
            current_user_tickets = int(entry["tickets"] if entry else 0)
            remaining = MAX_TICKETS_PER_USER_PER_RAFFLE - current_user_tickets
            if remaining <= 0:
                conn.commit()
                return False, "❌ Limite atingido nesta rifa: 1000/1000 tickets."
            if quantity > remaining:
                conn.commit()
                return False, f"❌ Limite individual excedido. Você ainda pode comprar **{remaining}** tickets nesta rifa."

            cost = quantity * TICKET_PRICE
            r = conn.execute("SELECT gold FROM resources WHERE user_id = ?", (user_id,)).fetchone()
            gold = int(r["gold"] if r else 0)
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
            conn.execute(
                "UPDATE raffles SET total_tickets = total_tickets + ?, total_pot = total_pot + ?, updated_at_ts = ? WHERE id = ?",
                (quantity, cost, now, raffle["id"]),
            )
            self._record_runtime_channel(conn, tipo, guild_id, channel_id)

            updated = conn.execute("SELECT total_tickets, total_pot, end_ts FROM raffles WHERE id = ?", (raffle["id"],)).fetchone()
            mine = conn.execute(
                "SELECT tickets FROM raffle_entries WHERE raffle_id = ? AND user_id = ?",
                (raffle["id"], user_id),
            ).fetchone()["tickets"]
            conn.commit()

        msg = (
            f"✅ Compra confirmada — Rifa **{RAFFLE_LABELS[tipo]}**\n"
            f"Tickets comprados agora: **{quantity}**\n"
            f"Seus tickets: **{mine}/1000**\n"
            f"Total de tickets da rifa: **{int(updated['total_tickets']):,}**\n"
            f"Total arrecadado: **{int(updated['total_pot']):,} ouro**\n"
            f"Prêmio atual: **{int(updated['total_pot']):,} ouro**\n"
            f"Encerramento: **{self._fmt_ts(int(updated['end_ts']))}**"
        ).replace(",", ".")
        return True, msg

    def get_hub_lines(self, user_id: str, guild_id: str | None = None, channel_id: str | None = None) -> list[str]:
        self.deps.get_or_create_domain(user_id)
        with self.deps.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM raffles WHERE status = 'active' ORDER BY CASE tipo WHEN 'relampago' THEN 1 WHEN 'sequencial' THEN 2 WHEN 'diaria' THEN 3 WHEN 'semanal' THEN 4 WHEN 'mensal' THEN 5 ELSE 6 END",
            ).fetchall()
            if guild_id or channel_id:
                for tipo in RAFFLE_LABELS:
                    self._record_runtime_channel(conn, tipo, guild_id, channel_id)
                conn.commit()

            by_tipo = {r["tipo"]: r for r in rows}
            lines: list[str] = []
            for alias, tipo in RAFFLE_TYPES.items():
                r = by_tipo.get(tipo)
                if not r:
                    lines.append(f"**{RAFFLE_LABELS[tipo]} ({alias})** — indisponível")
                    continue
                mine = conn.execute(
                    "SELECT tickets FROM raffle_entries WHERE raffle_id = ? AND user_id = ?",
                    (r["id"], user_id),
                ).fetchone()
                mine_tickets = int(mine["tickets"] if mine else 0)
                lines.append(
                    (
                        f"**{RAFFLE_LABELS[tipo]} (`{alias}`)**\n"
                        f"• Encerramento: {self._fmt_ts(int(r['end_ts']))}\n"
                        f"• Tickets totais: {int(r['total_tickets']):,}\n"
                        f"• Prêmio atual: {int(r['total_pot']):,} ouro\n"
                        f"• Seus tickets: {mine_tickets}/1000\n"
                        f"• Comprar: `!rifa {alias} 10`"
                    ).replace(",", ".")
                )
            return lines

    def settle_expired_raffles(self) -> list[dict[str, object]]:
        now = self.deps.now_ts()
        announcements: list[dict[str, object]] = []
        with self.deps.get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            expired = conn.execute(
                "SELECT * FROM raffles WHERE status = 'active' AND end_ts <= ? ORDER BY end_ts ASC",
                (now,),
            ).fetchall()

            for raffle in expired:
                rid = int(raffle["id"])
                tipo = str(raffle["tipo"])
                # Evita dupla liquidação em corrida.
                changed = conn.execute(
                    "UPDATE raffles SET status = 'closing', updated_at_ts = ? WHERE id = ? AND status = 'active'",
                    (now, rid),
                ).rowcount
                if changed == 0:
                    continue

                entries = conn.execute(
                    "SELECT user_id, tickets FROM raffle_entries WHERE raffle_id = ? AND tickets > 0 ORDER BY user_id",
                    (rid,),
                ).fetchall()
                total_tickets = int(raffle["total_tickets"] or 0)
                total_pot = int(raffle["total_pot"] or 0)

                winner_id: str | None = None
                winner_tickets = 0
                if entries and total_tickets > 0 and total_pot > 0:
                    pick = random.randint(1, total_tickets)
                    acc = 0
                    for e in entries:
                        acc += int(e["tickets"])
                        if pick <= acc:
                            winner_id = str(e["user_id"])
                            winner_tickets = int(e["tickets"])
                            break
                    if winner_id:
                        # Garante linha de recursos e paga prêmio integral.
                        self.deps.get_or_create_domain(winner_id)
                        conn.execute(
                            "UPDATE resources SET gold = gold + ?, updated_at_ts = ? WHERE user_id = ?",
                            (total_pot, now, winner_id),
                        )

                conn.execute(
                    """
                    UPDATE raffles
                    SET status = 'closed', winner_id = ?, winner_tickets = ?, closed_at_ts = ?, updated_at_ts = ?
                    WHERE id = ?
                    """,
                    (winner_id, winner_tickets, now, now, rid),
                )

                round_no = conn.execute(
                    "SELECT COALESCE(MAX(round_no), 0) n FROM raffles WHERE tipo = ?",
                    (tipo,),
                ).fetchone()["n"]
                new_end = self._next_end_ts(tipo, now)
                conn.execute(
                    "INSERT INTO raffles (tipo, round_no, start_ts, end_ts, status, created_at_ts, updated_at_ts) VALUES (?, ?, ?, ?, 'active', ?, ?)",
                    (tipo, int(round_no) + 1, now, new_end, now, now),
                )

                rt = conn.execute(
                    "SELECT last_guild_id, last_channel_id FROM raffle_runtime WHERE tipo = ?",
                    (tipo,),
                ).fetchone()

                announcements.append(
                    {
                        "tipo": tipo,
                        "label": RAFFLE_LABELS[tipo],
                        "raffle_id": rid,
                        "winner_id": winner_id,
                        "winner_tickets": winner_tickets,
                        "total_tickets": total_tickets,
                        "total_pot": total_pot,
                        "channel_id": str(rt["last_channel_id"]) if rt and rt["last_channel_id"] else None,
                        "guild_id": str(rt["last_guild_id"]) if rt and rt["last_guild_id"] else None,
                    }
                )

            conn.commit()
        return announcements


class RaffleLoop:
    def __init__(self, bot: commands.Bot, service: RaffleService, logger: Logger):
        self.bot = bot
        self.service = service
        self.logger = logger
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                settlements = self.service.settle_expired_raffles()
                for s in settlements:
                    self.logger.info(
                        "Rifa encerrada | tipo=%s id=%s vencedor=%s premio=%s",
                        s["tipo"],
                        s["raffle_id"],
                        s["winner_id"] or "nenhum",
                        s["total_pot"],
                    )
                    await self._announce_settlement(s)
            except Exception as exc:  # noqa: BLE001
                self.logger.exception("Falha no loop de rifas", exc_info=exc)
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    async def _announce_settlement(self, settlement: dict[str, object]) -> None:
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

        winner_id = settlement.get("winner_id")
        winner_text = f"<@{winner_id}>" if winner_id else "Sem vencedor (sem tickets válidos)"
        embed = discord.Embed(
            title=f"🎉 Resultado da Rifa {settlement['label']}",
            color=discord.Color.dark_gold(),
            timestamp=datetime.fromtimestamp(int(time.time()), tz=TZ_BR),
        )
        embed.add_field(name="Vencedor", value=winner_text, inline=False)
        embed.add_field(name="Total de tickets", value=f"{int(settlement['total_tickets']):,}".replace(",", "."), inline=True)
        embed.add_field(name="Total arrecadado", value=f"{int(settlement['total_pot']):,} ouro".replace(",", "."), inline=True)
        embed.add_field(name="Prêmio pago", value=f"{int(settlement['total_pot']):,} ouro".replace(",", "."), inline=True)
        embed.add_field(name="Tickets do vencedor", value=str(settlement["winner_tickets"]), inline=True)
        embed.add_field(name="Status", value="✅ A próxima rifa já começou.", inline=False)
        await channel.send(embed=embed)


def setup_bets(
    *,
    bot: commands.Bot,
    get_conn: Callable[[], sqlite3.Connection],
    get_or_create_domain: Callable[[str], sqlite3.Row],
    update_player_state: Callable[..., None],
    now_ts: Callable[[], int],
    logger: Logger,
) -> tuple[RaffleService, RaffleLoop]:
    deps = RaffleDeps(
        get_conn=get_conn,
        get_or_create_domain=get_or_create_domain,
        update_player_state=update_player_state,
        now_ts=now_ts,
        logger=logger,
    )
    service = RaffleService(deps)
    service.init_db()
    loop = RaffleLoop(bot=bot, service=service, logger=logger)

    @bot.command(name="rifa")
    async def rifa(ctx: commands.Context, tipo: str | None = None, quantidade: int | None = None) -> None:
        if not tipo or quantidade is None:
            await ctx.send("Uso: `!rifa <r|s|d|w|m|t> <quantidade>`")
            return
        ok, msg = service.buy_tickets(
            user_id=str(ctx.author.id),
            tipo_alias=tipo,
            quantity=int(quantidade),
            guild_id=str(ctx.guild.id) if ctx.guild else None,
            channel_id=str(ctx.channel.id) if ctx.channel else None,
        )
        await ctx.send(f"<@{ctx.author.id}> {msg}" if not ok else f"<@{ctx.author.id}>\n{msg}")

    @bot.command(name="rifas")
    async def rifas(ctx: commands.Context) -> None:
        lines = service.get_hub_lines(
            user_id=str(ctx.author.id),
            guild_id=str(ctx.guild.id) if ctx.guild else None,
            channel_id=str(ctx.channel.id) if ctx.channel else None,
        )
        embed = discord.Embed(title="🎟️ Hub de Rifas do NEXAR", color=discord.Color.gold())
        embed.description = "\n\n".join(lines)
        embed.set_footer(text=f"Preço fixo: {TICKET_PRICE:,} ouro por ticket • Limite individual: 1000 por rifa".replace(",", "."))
        await ctx.send(content=f"<@{ctx.author.id}>", embed=embed)

    return service, loop
