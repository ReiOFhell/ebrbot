from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from logging import Logger
import random
import sqlite3
import time
from typing import Callable
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

TZ_BR = ZoneInfo("America/Sao_Paulo")
TICKET_PRICE = 50_000
MAX_TICKETS_PER_USER_PER_RAFFLE = 1000
BJ_TIMEOUT_SECONDS = 60
BJ_COOLDOWN_SECONDS = 10
BJ_FLAVOR_CHANCE = 0.005

RAFFLE_TYPES: dict[str, str] = {"r": "relampago", "d": "diaria", "a": "admin"}
RAFFLE_TYPE_ALIASES = {
    "r": "relampago",
    "relampago": "relampago",
    "d": "diaria",
    "diaria": "diaria",
    "a": "admin",
    "admin": "admin",
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

    @staticmethod
    def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
        cols = {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        return column in cols

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
        if not self._has_column(conn, table, column):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS blackjack_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    bet INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    player_hand TEXT NOT NULL,
                    dealer_hand TEXT NOT NULL,
                    created_at_ts INTEGER NOT NULL,
                    updated_at_ts INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS blackjack_stats (
                    user_id TEXT PRIMARY KEY,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    pushes INTEGER NOT NULL DEFAULT 0,
                    blackjacks INTEGER NOT NULL DEFAULT 0,
                    surrenders INTEGER NOT NULL DEFAULT 0,
                    profit_total INTEGER NOT NULL DEFAULT 0,
                    biggest_win INTEGER NOT NULL DEFAULT 0,
                    biggest_loss INTEGER NOT NULL DEFAULT 0,
                    updated_at_ts INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS blackjack_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    bet INTEGER NOT NULL,
                    result TEXT NOT NULL,
                    profit INTEGER NOT NULL,
                    created_at_ts INTEGER NOT NULL
                )
                """
            )

            # defensive migrations
            self._ensure_column(conn, "raffles", "participants_total", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "raffles", "total_pot", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "raffles", "winner_tickets", "INTEGER")
            self._ensure_column(conn, "raffle_entries", "spent_gold", "INTEGER NOT NULL DEFAULT 0")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_raffles_tipo_status_end ON raffles(tipo, status, end_ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_raffles_status_end ON raffles(status, end_ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_raffle_entries_user ON raffle_entries(user_id)")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_raffles_active_tipo ON raffles(tipo) WHERE status = 'active'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bj_sessions_user_status ON blackjack_sessions(user_id, status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bj_history_user_ts ON blackjack_history(user_id, created_at_ts)")

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
        if tipo not in RAFFLE_TITLES:
            raise ValueError(f"tipo inválido: {tipo}")
        row = conn.execute(
            "SELECT * FROM raffles WHERE tipo = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (tipo,),
        ).fetchone()
        if row:
            return row
        round_no = int(conn.execute("SELECT COALESCE(MAX(round_no), 0) n FROM raffles WHERE tipo = ?", (tipo,)).fetchone()["n"])
        conn.execute(
            """
            INSERT INTO raffles (tipo, round_no, start_ts, end_ts, status, total_tickets, participants_total, total_pot, created_at_ts, updated_at_ts)
            VALUES (?, ?, ?, ?, 'active', 0, 0, 0, ?, ?)
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

    def buy_tickets(self, *, user_id: str, tipo_raw: str, quantity: int, guild_id: str | None, channel_id: str | None, is_admin: bool) -> tuple[bool, str]:
        tipo = self._normalize_tipo(tipo_raw)
        if not tipo:
            return False, "❌ Tipo inválido. Use r, d ou a/admin."
        if tipo == "admin" and not is_admin:
            return False, "❌ A rifa admin é exclusiva para administradores."
        if quantity <= 0:
            return False, "❌ Quantidade inválida. Use inteiro > 0."

        self.deps.get_or_create_domain(user_id)
        now = self.deps.now_ts()

        try:
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
                participants_total = int(conn.execute("SELECT COUNT(*) c FROM raffle_entries WHERE raffle_id = ? AND tickets > 0", (raffle["id"],)).fetchone()["c"])
                conn.execute(
                    """
                    UPDATE raffles
                    SET total_tickets = total_tickets + ?, total_pot = total_pot + ?, participants_total = ?, updated_at_ts = ?
                    WHERE id = ?
                    """,
                    (quantity, cost, participants_total, now, raffle["id"]),
                )
                self._record_runtime_channel(conn, tipo, guild_id, channel_id)

                updated = conn.execute("SELECT total_tickets, total_pot, end_ts FROM raffles WHERE id = ?", (raffle["id"],)).fetchone()
                mine_after = int(conn.execute("SELECT tickets FROM raffle_entries WHERE raffle_id = ? AND user_id = ?", (raffle["id"], user_id)).fetchone()["tickets"])
                conn.commit()
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower():
                return False, "⚠️ Sistema de rifas ocupado no momento. Tente novamente em alguns segundos."
            raise

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

            my_row = conn.execute("SELECT tickets FROM raffle_entries WHERE raffle_id = ? AND user_id = ?", (raffle["id"], user_id)).fetchone()
            my_tickets = int(my_row["tickets"] if my_row else 0)
            total_tickets = int(raffle["total_tickets"])
            chance = (my_tickets / total_tickets * 100.0) if total_tickets > 0 else 0.0

            state = conn.execute("SELECT last_winner_id, last_winner_name, last_prize FROM raffle_state WHERE tipo = ?", (tipo,)).fetchone()
            conn.commit()

        participants_total = int(raffle["participants_total"] if "participants_total" in raffle.keys() else 0)
        return {
            "tipo": tipo,
            "title": RAFFLE_TITLES[tipo],
            "end_ts": int(raffle["end_ts"]),
            "total_tickets": total_tickets,
            "participants_total": participants_total,
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
            conn.execute(
                "UPDATE raffles SET status = 'closed', updated_at_ts = ? WHERE status = 'active' AND tipo NOT IN ('relampago','diaria','admin')",
                (now,),
            )
            expired = conn.execute("SELECT * FROM raffles WHERE status = 'active' AND end_ts <= ? ORDER BY end_ts ASC", (now,)).fetchall()

            for raffle in expired:
                raffle_id = int(raffle["id"])
                tipo = str(raffle["tipo"])
                if tipo not in RAFFLE_TITLES:
                    conn.execute("UPDATE raffles SET status = 'closed', updated_at_ts = ? WHERE id = ?", (now, raffle_id))
                    continue
                locked = conn.execute(
                    "UPDATE raffles SET status = 'closing', updated_at_ts = ? WHERE id = ? AND status = 'active'",
                    (now, raffle_id),
                ).rowcount
                if locked == 0:
                    continue

                entries = conn.execute("SELECT user_id, tickets FROM raffle_entries WHERE raffle_id = ? AND tickets > 0 ORDER BY user_id", (raffle_id,)).fetchall()
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
                        conn.execute("UPDATE resources SET gold = gold + ?, updated_at_ts = ? WHERE user_id = ?", (total_pot, now, winner_id))
                        winner_name = winner_id

                conn.execute(
                    """
                    UPDATE raffles SET status='closed', winner_id=?, winner_tickets=?, participants_total=?, closed_at_ts=?, updated_at_ts=? WHERE id=?
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
                rt = conn.execute("SELECT last_channel_id FROM raffle_runtime WHERE tipo = ?", (tipo,)).fetchone()
                settlements.append(
                    {
                        "tipo": tipo,
                        "title": RAFFLE_TITLES.get(tipo, f"🎲 NEXAR | Rifa {tipo.title()}"),
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
    if data["last_winner_id"]:
        last_line = f"{data['last_winner_name']} ({data['last_winner_id']}) (+{int(data['last_prize']):,} ouro)".replace(",", ".")
    else:
        last_line = "Nenhum ainda."

    end_ts = int(data["end_ts"])
    embed = discord.Embed(title=str(data["title"]), color=discord.Color.gold())
    embed.add_field(name="💰 Prêmio atual", value=f"{int(data['total_pot']):,} ouro".replace(",", "."), inline=True)
    embed.add_field(name="🎟️ Tickets totais", value=f"{int(data['total_tickets']):,} tickets".replace(",", "."), inline=True)
    embed.add_field(name="👥 Participantes", value=str(int(data["participants_total"])), inline=True)
    embed.add_field(name="🧾 Seus tickets", value=f"{int(data['my_tickets'])}/1000", inline=True)
    embed.add_field(name="📊 Sua chance atual", value=f"{float(data['chance']):.2f}%", inline=True)
    embed.add_field(name="🤑 Último ganhador", value=last_line, inline=False)
    embed.add_field(name="⏳ Resultado", value=f"<t:{end_ts}:F> • <t:{end_ts}:R>", inline=False)
    embed.add_field(name="🛒 Comprar", value=f"`!rifa b {tipo_alias} 10` / `!rifa buy {tipo_alias} 10`", inline=False)
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
            uid = str(p["user_id"])
            tickets = int(p["tickets"])
            chance = (tickets / total_tickets) * 100.0
            won = winner_id is not None and uid == winner_id
            result_line = f"✅ VOCÊ GANHOU +{int(settlement['total_pot']):,} ouro" if won else f"❌ você não foi escolhido; vencedor foi <@{winner_id}>"
            msg = (
                f"🎲 A rifa acabou!\n"
                f"Rifa: {settlement['title']}\n"
                f"Seus tickets: {tickets}\n"
                f"Sua chance final: {chance:.2f}% ({tickets}/{total_tickets})\n"
                f"{result_line}"
            ).replace(",", ".")
            user = self.bot.get_user(int(uid))
            if user is None:
                try:
                    user = await self.bot.fetch_user(int(uid))
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


def _draw_card() -> str:
    return random.choice(["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"])


def _hand_total(hand: list[str]) -> int:
    total = 0
    aces = 0
    for c in hand:
        if c in {"J", "Q", "K"}:
            total += 10
        elif c == "A":
            aces += 1
            total += 11
        else:
            total += int(c)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def _hand_text(hand: list[str]) -> str:
    return " ".join(hand)


class BlackjackService:
    def __init__(self, deps: RaffleDeps):
        self.deps = deps
        self.cooldowns: dict[str, int] = {}

    def _get_active_session(self, conn: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM blackjack_sessions WHERE user_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()

    def _ensure_stats_row(self, conn: sqlite3.Connection, user_id: str, ts: int) -> None:
        conn.execute("INSERT OR IGNORE INTO blackjack_stats (user_id, updated_at_ts) VALUES (?, ?)", (user_id, ts))

    def start_session(self, user_id: str, bet: int) -> tuple[bool, str, int | None]:
        now = self.deps.now_ts()
        if bet <= 0:
            return False, "❌ A aposta deve ser maior que zero.", None
        if self.cooldowns.get(user_id, 0) > now:
            return False, "⏳ Aguarde alguns segundos para abrir outra mesa.", None

        self.deps.get_or_create_domain(user_id)
        with self.deps.get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            active = self._get_active_session(conn, user_id)
            if active:
                conn.commit()
                return False, "❌ Você já possui uma Mesa Imperial ativa. Use os botões da mesa atual.", None

            gold = int(conn.execute("SELECT gold FROM resources WHERE user_id = ?", (user_id,)).fetchone()["gold"] or 0)
            if bet > gold:
                conn.commit()
                return False, "❌ Ouro insuficiente para selar essa aposta.", None

            player = [_draw_card(), _draw_card()]
            dealer = [_draw_card(), _draw_card()]
            conn.execute("UPDATE resources SET gold = gold - ?, updated_at_ts = ? WHERE user_id = ?", (bet, now, user_id))
            conn.execute(
                """
                INSERT INTO blackjack_sessions (user_id, bet, status, player_hand, dealer_hand, created_at_ts, updated_at_ts)
                VALUES (?, ?, 'active', ?, ?, ?, ?)
                """,
                (user_id, bet, json.dumps(player), json.dumps(dealer), now, now),
            )
            sid = int(conn.execute("SELECT last_insert_rowid() id").fetchone()["id"])
            conn.commit()
            return True, "📜 A aposta foi selada. 👁️ O Trono observa o seu risco.", sid

    def get_session(self, user_id: str) -> sqlite3.Row | None:
        with self.deps.get_conn() as conn:
            return self._get_active_session(conn, user_id)

    def _settle(self, conn: sqlite3.Connection, srow: sqlite3.Row, result: str) -> tuple[int, int, int]:
        user_id = str(srow["user_id"])
        bet = int(srow["bet"])
        player = json.loads(str(srow["player_hand"]))
        dealer = json.loads(str(srow["dealer_hand"]))
        p_total = _hand_total(player)
        d_total = _hand_total(dealer)

        payout = 0
        profit = 0
        if result == "blackjack":
            payout = bet + int(bet * 1.5)
            profit = int(bet * 1.5)
        elif result == "win":
            payout = bet * 2
            profit = bet
        elif result == "push":
            payout = bet
            profit = 0
        elif result == "surrender":
            payout = bet // 2
            profit = -(bet - payout)
        else:
            payout = 0
            profit = -bet

        ts = self.deps.now_ts()
        if payout > 0:
            conn.execute("UPDATE resources SET gold = gold + ?, updated_at_ts = ? WHERE user_id = ?", (payout, ts, user_id))

        self._ensure_stats_row(conn, user_id, ts)
        if result in {"win", "blackjack"}:
            conn.execute("UPDATE blackjack_stats SET wins = wins + 1 WHERE user_id = ?", (user_id,))
        elif result == "push":
            conn.execute("UPDATE blackjack_stats SET pushes = pushes + 1 WHERE user_id = ?", (user_id,))
        elif result == "surrender":
            conn.execute("UPDATE blackjack_stats SET surrenders = surrenders + 1 WHERE user_id = ?", (user_id,))
        else:
            conn.execute("UPDATE blackjack_stats SET losses = losses + 1 WHERE user_id = ?", (user_id,))
        if result == "blackjack":
            conn.execute("UPDATE blackjack_stats SET blackjacks = blackjacks + 1 WHERE user_id = ?", (user_id,))

        stats = conn.execute("SELECT biggest_win, biggest_loss, profit_total FROM blackjack_stats WHERE user_id = ?", (user_id,)).fetchone()
        biggest_win = max(int(stats["biggest_win"] or 0), max(0, profit))
        biggest_loss = min(int(stats["biggest_loss"] or 0), min(0, profit))
        conn.execute(
            """
            UPDATE blackjack_stats
            SET profit_total = profit_total + ?, biggest_win = ?, biggest_loss = ?, updated_at_ts = ?
            WHERE user_id = ?
            """,
            (profit, biggest_win, biggest_loss, ts, user_id),
        )
        conn.execute(
            "INSERT INTO blackjack_history (user_id, bet, result, profit, created_at_ts) VALUES (?, ?, ?, ?, ?)",
            (user_id, bet, result, profit, ts),
        )
        conn.execute("UPDATE blackjack_sessions SET status = 'finished', updated_at_ts = ? WHERE id = ?", (ts, int(srow["id"])))
        return payout, profit, bet

    def player_action(self, user_id: str, action: str) -> tuple[bool, str, dict[str, object] | None]:
        with self.deps.get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            srow = self._get_active_session(conn, user_id)
            if not srow:
                conn.commit()
                return False, "❌ Nenhuma mesa ativa encontrada para você.", None

            player = json.loads(str(srow["player_hand"]))
            dealer = json.loads(str(srow["dealer_hand"]))
            bet = int(srow["bet"])
            created_at = int(srow["created_at_ts"])
            now = self.deps.now_ts()

            if now - created_at > BJ_TIMEOUT_SECONDS:
                action = "timeout"

            initial_turn = len(player) == 2
            result: str | None = None

            if action == "surrender" and initial_turn:
                result = "surrender"
            elif action == "double" and initial_turn:
                gold = int(conn.execute("SELECT gold FROM resources WHERE user_id = ?", (user_id,)).fetchone()["gold"] or 0)
                if gold < bet:
                    conn.commit()
                    return False, "❌ Ouro insuficiente para dobrar a aposta.", None
                conn.execute("UPDATE resources SET gold = gold - ?, updated_at_ts = ? WHERE user_id = ?", (bet, now, user_id))
                bet *= 2
                conn.execute("UPDATE blackjack_sessions SET bet = ?, updated_at_ts = ? WHERE id = ?", (bet, now, int(srow["id"])))
                player.append(_draw_card())
                conn.execute("UPDATE blackjack_sessions SET player_hand = ?, updated_at_ts = ? WHERE id = ?", (json.dumps(player), now, int(srow["id"])))
                p_total = _hand_total(player)
                result = "lose" if p_total > 21 else None
                action = "stand"
            elif action == "hit":
                player.append(_draw_card())
                conn.execute("UPDATE blackjack_sessions SET player_hand = ?, updated_at_ts = ? WHERE id = ?", (json.dumps(player), now, int(srow["id"])))
                if _hand_total(player) > 21:
                    result = "lose"
            # stand/timeout/after double fallthrough

            if action in {"stand", "timeout"} and result is None:
                while _hand_total(dealer) < 17:
                    dealer.append(_draw_card())
                conn.execute("UPDATE blackjack_sessions SET dealer_hand = ?, updated_at_ts = ? WHERE id = ?", (json.dumps(dealer), now, int(srow["id"])))
                p_total = _hand_total(player)
                d_total = _hand_total(dealer)
                is_natural = len(player) == 2 and p_total == 21
                if p_total > 21:
                    result = "lose"
                elif d_total > 21:
                    result = "blackjack" if is_natural else "win"
                elif p_total > d_total:
                    result = "blackjack" if is_natural else "win"
                elif p_total == d_total:
                    result = "push"
                else:
                    result = "lose"

            if result:
                payout, profit, final_bet = self._settle(conn, srow, result)
                conn.commit()
                self.cooldowns[user_id] = self.deps.now_ts() + BJ_COOLDOWN_SECONDS
                payload = {
                    "finished": True,
                    "result": result,
                    "payout": payout,
                    "profit": profit,
                    "bet": final_bet,
                    "player": player,
                    "dealer": dealer,
                    "timeout": action == "timeout",
                }
                return True, "🜂 O Croupier revela a sentença.", payload

            conn.commit()
            payload = {"finished": False, "bet": bet, "player": player, "dealer": dealer}
            return True, "Sua vez na Mesa Imperial.", payload

    def stats(self, user_id: str) -> sqlite3.Row:
        now = self.deps.now_ts()
        with self.deps.get_conn() as conn:
            self._ensure_stats_row(conn, user_id, now)
            conn.commit()
            return conn.execute("SELECT * FROM blackjack_stats WHERE user_id = ?", (user_id,)).fetchone()

    def top_profit(self) -> list[sqlite3.Row]:
        with self.deps.get_conn() as conn:
            return conn.execute("SELECT user_id, profit_total FROM blackjack_stats ORDER BY profit_total DESC LIMIT 10").fetchall()


def build_bj_embed(*, user: discord.abc.User, bet: int, player: list[str], dealer: list[str], finished: bool,
                   result_line: str | None = None, profit: int | None = None) -> discord.Embed:
    p_total = _hand_total(player)
    shown_dealer = dealer if finished else [dealer[0], "?"]
    d_total = _hand_total(dealer) if finished else "?"
    embed = discord.Embed(title="🎲 NEXAR | Mesa Imperial — Blackjack", color=discord.Color.dark_gold())
    embed.add_field(name="Aposta Selada", value=f"{bet:,} ouro".replace(",", "."), inline=False)
    embed.add_field(name="Croupier do Trono", value=f"{_hand_text(shown_dealer)} (Total: {d_total})", inline=False)
    embed.add_field(name="Jogador", value=f"{_hand_text(player)} (Total: {p_total})", inline=False)
    embed.add_field(name="Estado", value="Sentença do Croupier" if finished else "Sua vez", inline=False)
    if result_line:
        delta = f"\nΔ Ouro: {profit:+,}".replace(",", ".") if profit is not None else ""
        embed.add_field(name="Resultado", value=f"{result_line}{delta}", inline=False)
    return embed


class BlackjackView(discord.ui.View):
    def __init__(self, *, owner_id: int, service: BlackjackService, bot: commands.Bot):
        super().__init__(timeout=BJ_TIMEOUT_SECONDS)
        self.owner_id = owner_id
        self.service = service
        self.bot = bot
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Apenas quem abriu a mesa pode jogar nela.", ephemeral=True)
            return False
        return True

    async def _run_action(self, interaction: discord.Interaction, action: str) -> None:
        ok, msg, data = self.service.player_action(str(interaction.user.id), action)
        if not ok or not data:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        finished = bool(data["finished"])
        if finished:
            self.disable_all_items()
            flavor = ""
            if random.random() < BJ_FLAVOR_CHANCE:
                flavor = "\n📜 Fragmento: \"A moeda não tem lado… só preço.\""
            result_map = {
                "blackjack": "🃏 Blackjack Imperial!",
                "win": "✅ Vitória.",
                "push": "⚖️ Empate.",
                "lose": "❌ Derrota.",
                "surrender": "🏳️ Rendição aceita.",
            }
            line = result_map.get(str(data["result"]), "Fim da rodada.") + flavor
            embed = build_bj_embed(
                user=interaction.user,
                bet=int(data["bet"]),
                player=data["player"],
                dealer=data["dealer"],
                finished=True,
                result_line=line,
                profit=int(data["profit"]),
            )
            await interaction.response.edit_message(embed=embed, view=self)
            return

        embed = build_bj_embed(
            user=interaction.user,
            bet=int(data["bet"]),
            player=data["player"],
            dealer=data["dealer"],
            finished=False,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🂡 Puxar", style=discord.ButtonStyle.success)
    async def hit(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._run_action(interaction, "hit")

    @discord.ui.button(label="🛡️ Parar", style=discord.ButtonStyle.primary)
    async def stand(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._run_action(interaction, "stand")

    @discord.ui.button(label="⚡ Dobrar", style=discord.ButtonStyle.secondary)
    async def double(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._run_action(interaction, "double")

    @discord.ui.button(label="🏳️ Render-se", style=discord.ButtonStyle.danger)
    async def surrender(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._run_action(interaction, "surrender")

    async def on_timeout(self) -> None:
        ok, _msg, data = self.service.player_action(str(self.owner_id), "timeout")
        self.disable_all_items()
        if not self.message:
            return
        if ok and data and data.get("finished"):
            user = self.bot.get_user(self.owner_id)
            if user is None:
                try:
                    user = await self.bot.fetch_user(self.owner_id)
                except Exception:
                    return
            embed = build_bj_embed(
                user=user,
                bet=int(data["bet"]),
                player=data["player"],
                dealer=data["dealer"],
                finished=True,
                result_line="⏳ Tempo esgotado: a mesa foi encerrada por stand automático.",
                profit=int(data["profit"]),
            )
            try:
                await self.message.edit(embed=embed, view=self)
            except Exception:
                return
        else:
            try:
                await self.message.edit(view=self)
            except Exception:
                return


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
    service = RaffleService(RaffleDeps(get_conn=get_conn, get_or_create_domain=get_or_create_domain, now_ts=now_ts, logger=logger))
    bj_service = BlackjackService(RaffleDeps(get_conn=get_conn, get_or_create_domain=get_or_create_domain, now_ts=now_ts, logger=logger))
    service.init_db()
    loop = RaffleLoop(bot=bot, service=service, logger=logger)

    @bot.command(name="rifa")
    async def rifa(ctx: commands.Context, *args: str) -> None:
        uid = str(ctx.author.id)
        gid = str(ctx.guild.id) if ctx.guild else None
        cid = str(ctx.channel.id) if ctx.channel else None
        is_admin = bool(ctx.guild and ctx.author.guild_permissions.administrator)

        if not args:
            entries = [("r", "relampago"), ("d", "diaria")]
            if is_admin:
                entries.append(("a", "admin"))
            embeds = []
            for alias, tipo in entries:
                data = service.get_panel_data(tipo_raw=tipo, user_id=uid, guild_id=gid, channel_id=cid)
                if data:
                    embeds.append(build_raffle_embed(data, tipo_alias=alias))
            await ctx.send(content=f"<@{ctx.author.id}>", embeds=embeds)
            return

        first = args[0].lower()
        if first in {"b", "buy"}:
            if len(args) < 3:
                await ctx.send("Uso: `!rifa b <r|d|a> <quantidade>` ou `!rifa buy <r|d|admin> <quantidade>`")
                return
            tipo_raw = args[1]
            try:
                qtd = int(args[2])
            except ValueError:
                await ctx.send("❌ Quantidade inválida. Use inteiro > 0.")
                return
            ok, msg = service.buy_tickets(user_id=uid, tipo_raw=tipo_raw, quantity=qtd, guild_id=gid, channel_id=cid, is_admin=is_admin)
            await ctx.send(f"<@{ctx.author.id}>\n{msg}" if ok else f"<@{ctx.author.id}> {msg}")
            return

        data = service.get_panel_data(tipo_raw=first, user_id=uid, guild_id=gid, channel_id=cid)
        if not data:
            await ctx.send("❌ Uso: `!rifa`, `!rifa r`, `!rifa d`, `!rifa a`, `!rifa b <tipo> <qtd>`, `!rifa buy <tipo> <qtd>`")
            return
        if data["tipo"] == "admin" and not is_admin:
            await ctx.send("❌ A rifa admin é exclusiva para administradores.")
            return
        alias = "r" if data["tipo"] == "relampago" else ("d" if data["tipo"] == "diaria" else "a")
        await ctx.send(content=f"<@{ctx.author.id}>", embed=build_raffle_embed(data, tipo_alias=alias))

    @bot.command(name="rifas")
    async def rifas(ctx: commands.Context) -> None:
        await rifa(ctx)

    @bot.command(name="bj")
    async def bj(ctx: commands.Context, aposta: str | None = None) -> None:
        if aposta is None:
            await ctx.send(
                "🎲 Mesa Imperial — Blackjack\n"
                "Uso: `!bj <aposta>`\n"
                "Botões: 🂡 Puxar • 🛡️ Parar • ⚡ Dobrar • 🏳️ Render-se\n"
                "Payouts: Blackjack +1.5x lucro | Vitória +1x | Empate 0 | Derrota -1x | Render-se -0.5x"
            )
            return
        if not aposta.isdigit():
            await ctx.send("❌ A aposta deve ser um inteiro positivo (sem decimal).")
            return
        bet = int(aposta)
        ok, msg, sid = bj_service.start_session(str(ctx.author.id), bet)
        if not ok or sid is None:
            await ctx.send(f"<@{ctx.author.id}> {msg}")
            return
        srow = bj_service.get_session(str(ctx.author.id))
        if not srow:
            await ctx.send("❌ Não foi possível abrir a mesa agora.")
            return
        player = json.loads(str(srow["player_hand"]))
        dealer = json.loads(str(srow["dealer_hand"]))
        embed = build_bj_embed(user=ctx.author, bet=int(srow["bet"]), player=player, dealer=dealer, finished=False)
        view = BlackjackView(owner_id=ctx.author.id, service=bj_service, bot=bot)
        msg_obj = await ctx.send(content=f"<@{ctx.author.id}> {msg}", embed=embed, view=view)
        view.message = msg_obj

    @bot.command(name="bjstats")
    async def bjstats(ctx: commands.Context) -> None:
        row = bj_service.stats(str(ctx.author.id))
        embed = discord.Embed(title="📊 NEXAR | Estatísticas da Mesa Imperial", color=discord.Color.blurple())
        embed.add_field(name="Vitórias", value=str(int(row["wins"] or 0)), inline=True)
        embed.add_field(name="Derrotas", value=str(int(row["losses"] or 0)), inline=True)
        embed.add_field(name="Empates", value=str(int(row["pushes"] or 0)), inline=True)
        embed.add_field(name="Blackjacks", value=str(int(row["blackjacks"] or 0)), inline=True)
        embed.add_field(name="Rendições", value=str(int(row["surrenders"] or 0)), inline=True)
        embed.add_field(name="Lucro total", value=f"{int(row['profit_total'] or 0):,} ouro".replace(",", "."), inline=False)
        embed.add_field(name="Maior vitória", value=f"{int(row['biggest_win'] or 0):,}".replace(",", "."), inline=True)
        embed.add_field(name="Maior derrota", value=f"{int(row['biggest_loss'] or 0):,}".replace(",", "."), inline=True)
        await ctx.send(content=f"<@{ctx.author.id}>", embed=embed)

    @bot.command(name="bjrank")
    async def bjrank(ctx: commands.Context) -> None:
        rows = bj_service.top_profit()
        if not rows:
            await ctx.send("📉 Nenhum dado de Blackjack ainda.")
            return
        lines = [f"{i}. <@{r['user_id']}> — {int(r['profit_total']):,}".replace(",", ".") for i, r in enumerate(rows, start=1)]
        embed = discord.Embed(title="🏛️ NEXAR | Ranking Blackjack (Lucro Total)", description="\n".join(lines), color=discord.Color.dark_teal())
        await ctx.send(embed=embed)

    return service, loop
