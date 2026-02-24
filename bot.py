import logging
import os
import random
import sqlite3
import time
from pathlib import Path

import discord
from discord.ext import commands

from core.economy import (
    TRAIN_COOLDOWN_SECONDS,
    barracks_train_amount,
    barn_production_per_hour,
    building_upgrade_cost,
    building_upgrade_time_seconds,
    economy_snapshot,
    effective_collect_seconds,
    net_balance_for_window_seconds,
    recalc_power,
    simulate_operation_success_chance,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("ebr.nucleoc")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "nucleoc.db"

DISCORD_TOKEN_FALLBACK = ""  # opcional: cole aqui apenas para teste local


def resolve_token() -> str:
    token = (os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN") or DISCORD_TOKEN_FALLBACK or "").strip()
    if not token:
        raise RuntimeError("Token não encontrado. Defina DISCORD_TOKEN (ou BOT_TOKEN).")
    return token


intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DOCTRINES = {"cerco", "choque", "furtivo", "arcano"}
GENERAL_RANK_BONUS = {"C": 0.02, "B": 0.04, "A": 0.06, "S": 0.10}
STRATEGIST_RANK_BONUS = {"C": 0.015, "B": 0.03, "A": 0.05, "S": 0.08}
MAX_BUILDING_TIER = 10


def now_ts() -> int:
    return int(time.time())


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, col: str, ddl: str) -> None:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def init_db() -> None:
    with get_conn() as conn:
        # 1) estado principal por jogador
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS domains (
                user_id TEXT PRIMARY KEY,
                created_at_ts INTEGER NOT NULL
            )
            """
        )
        # 2) buildings + timers
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS domain_buildings (
                user_id TEXT PRIMARY KEY,
                barn_level INTEGER NOT NULL DEFAULT 1,
                barracks_level INTEGER NOT NULL DEFAULT 1,
                forge_level INTEGER NOT NULL DEFAULT 1,
                building_upgrade_ends_at_ts INTEGER,
                updated_at_ts INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES domains(user_id)
            )
            """
        )
        # 3) recursos
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS resources (
                user_id TEXT PRIMARY KEY,
                gold INTEGER NOT NULL DEFAULT 100000,
                accumulated_maintenance INTEGER NOT NULL DEFAULT 0,
                last_collect_ts INTEGER NOT NULL,
                updated_at_ts INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES domains(user_id)
            )
            """
        )
        # 4) exército
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS army (
                user_id TEXT PRIMARY KEY,
                troops INTEGER NOT NULL DEFAULT 0,
                doctrine TEXT NOT NULL DEFAULT 'choque',
                power INTEGER NOT NULL DEFAULT 0,
                last_train_ts INTEGER NOT NULL,
                updated_at_ts INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES domains(user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS generals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                rank TEXT NOT NULL DEFAULT 'C',
                equipped INTEGER NOT NULL DEFAULT 0,
                created_at_ts INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES domains(user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS strategists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                rank TEXT NOT NULL DEFAULT 'C',
                equipped INTEGER NOT NULL DEFAULT 0,
                created_at_ts INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES domains(user_id)
            )
            """
        )
        # 5) operações
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                min_barracks_level INTEGER NOT NULL DEFAULT 1,
                requires_strategist INTEGER NOT NULL DEFAULT 0,
                base_gold_reward INTEGER NOT NULL DEFAULT 0,
                base_risk_percent REAL NOT NULL DEFAULT 0.0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                operation_id INTEGER NOT NULL,
                outcome TEXT NOT NULL,
                troops_lost INTEGER NOT NULL DEFAULT 0,
                gold_delta INTEGER NOT NULL DEFAULT 0,
                created_at_ts INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES domains(user_id),
                FOREIGN KEY(operation_id) REFERENCES operations(id)
            )
            """
        )
        # 6) itens + inventário
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                rarity TEXT NOT NULL,
                lore TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inventories (
                user_id TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id, item_id),
                FOREIGN KEY(user_id) REFERENCES domains(user_id),
                FOREIGN KEY(item_id) REFERENCES items(id)
            )
            """
        )
        # 7) temporada
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS season_state (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                season_number INTEGER NOT NULL,
                started_at_ts INTEGER NOT NULL,
                ends_at_ts INTEGER NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS season_scores (
                season_number INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                prestige INTEGER NOT NULL DEFAULT 0,
                wealth_snapshot INTEGER NOT NULL DEFAULT 0,
                power_snapshot INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(season_number, user_id),
                FOREIGN KEY(user_id) REFERENCES domains(user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS panel_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                guild_id TEXT,
                event_name TEXT NOT NULL,
                event_action TEXT,
                error_code TEXT,
                created_at_ts INTEGER NOT NULL
            )
            """
        )

        # Compatibilidade incremental de colunas da Fase 3
        ensure_column(conn, "army", "general_id", "INTEGER")
        ensure_column(conn, "army", "strategist_id", "INTEGER")
        ensure_column(conn, "operations", "difficulty_power", "INTEGER NOT NULL DEFAULT 1000")
        ensure_column(conn, "operations", "preferred_doctrine", "TEXT")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_operation_runs_user ON operation_runs(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_generals_user ON generals(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_strategists_user ON strategists(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_panel_events_user ON panel_events(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_panel_events_name ON panel_events(event_name)")

        # seeds mínimos
        conn.execute(
            """
            INSERT OR IGNORE INTO operations (key, title, min_barracks_level, requires_strategist, base_gold_reward, base_risk_percent)
            VALUES
            ('tumba_sultao', 'Tumba do Sultão da Caravana', 3, 1, 300000, 0.12),
            ('ruinas_muralha', 'Ruínas da Muralha Viva', 4, 0, 450000, 0.09),
            ('estrada_cinzas', 'Estrada das Sete Cinzas', 2, 0, 180000, 0.10)
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO items (key, name, rarity, lore)
            VALUES
            ('pergaminho_rasgado_i', 'Pergaminho Rasgado I', 'C', 'O Trono não respondeu.'),
            ('elmo_basalto', 'Elmo do Basalto', 'R', 'Usado quando a muralha ainda respirava.'),
            ('cronica_heroi_sem_tumulo', 'Crônica do Herói Sem Túmulo', 'L', 'Salvou o mundo e perdeu o nome.')
            """
        )

        conn.execute("UPDATE operations SET difficulty_power = 2200, preferred_doctrine = 'furtivo' WHERE key = 'tumba_sultao'")
        conn.execute("UPDATE operations SET difficulty_power = 3500, preferred_doctrine = 'cerco' WHERE key = 'ruinas_muralha'")
        conn.execute("UPDATE operations SET difficulty_power = 1600, preferred_doctrine = 'choque' WHERE key = 'estrada_cinzas'")

        conn.commit()


def log_panel_event(
    *,
    user_id: str,
    guild_id: str | None,
    event_name: str,
    event_action: str | None = None,
    error_code: str | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO panel_events (user_id, guild_id, event_name, event_action, error_code, created_at_ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, guild_id, event_name, event_action, error_code, now_ts()),
        )
        conn.commit()


def get_or_create_domain(user_id: str) -> sqlite3.Row:
    ts = now_ts()
    with get_conn() as conn:
        # Migração defensiva: contas antigas podem existir em `domains` sem linhas irmãs.
        domain = conn.execute("SELECT * FROM domains WHERE user_id = ?", (user_id,)).fetchone()
        if not domain:
            conn.execute("INSERT INTO domains (user_id, created_at_ts) VALUES (?, ?)", (user_id, ts))

        # Garante linhas relacionadas mesmo para usuários já existentes de versões anteriores.
        conn.execute(
            "INSERT OR IGNORE INTO domain_buildings (user_id, updated_at_ts) VALUES (?, ?)",
            (user_id, ts),
        )
        conn.execute(
            "INSERT OR IGNORE INTO resources (user_id, last_collect_ts, updated_at_ts) VALUES (?, ?, ?)",
            (user_id, ts, ts),
        )
        conn.execute(
            "INSERT OR IGNORE INTO army (user_id, last_train_ts, updated_at_ts) VALUES (?, ?, ?)",
            (user_id, ts, ts),
        )
        conn.commit()

        return conn.execute(
            """
            SELECT d.user_id, d.created_at_ts,
                   b.barn_level, b.barracks_level, b.forge_level,
                   r.gold, r.accumulated_maintenance, r.last_collect_ts,
                   a.troops, a.doctrine, a.power, a.last_train_ts, a.general_id, a.strategist_id
            FROM domains d
            JOIN domain_buildings b ON b.user_id = d.user_id
            JOIN resources r ON r.user_id = d.user_id
            JOIN army a ON a.user_id = d.user_id
            WHERE d.user_id = ?
            """,
            (user_id,),
        ).fetchone()


def get_slot_bonuses(conn: sqlite3.Connection, general_id: int | None, strategist_id: int | None) -> tuple[float, float]:
    g_bonus = 0.0
    s_bonus = 0.0
    if general_id:
        row = conn.execute("SELECT rank FROM generals WHERE id = ?", (general_id,)).fetchone()
        if row:
            g_bonus = GENERAL_RANK_BONUS.get(str(row["rank"]), 0.0)
    if strategist_id:
        row = conn.execute("SELECT rank FROM strategists WHERE id = ?", (strategist_id,)).fetchone()
        if row:
            s_bonus = STRATEGIST_RANK_BONUS.get(str(row["rank"]), 0.0)
    return g_bonus, s_bonus


def has_strategist_gate(domain: sqlite3.Row, conn: sqlite3.Connection) -> tuple[bool, str]:
    if domain["barracks_level"] < 3:
        return False, "Requisito: Casernas T3+ para habilitar estrategista."
    if domain["gold"] < 200_000:
        return False, "Requisito: 200.000 ouro para manter conselho estratégico."
    runs = conn.execute("SELECT COUNT(*) c FROM operation_runs WHERE user_id = ?", (domain["user_id"],)).fetchone()["c"]
    if runs < 1:
        return False, "Requisito: concluir ao menos 1 operação (ex.: `!simular_operacao estrada_cinzas`) para desbloquear estrategista."
    return True, "OK"


def update_player_state(user_id: str, *, gold: int | None = None, last_collect_ts: int | None = None,
                        accumulated_maintenance: int | None = None, troops: int | None = None,
                        last_train_ts: int | None = None, power: int | None = None, doctrine: str | None = None,
                        general_id: int | None = None, strategist_id: int | None = None,
                        barn_level: int | None = None, barracks_level: int | None = None,
                        forge_level: int | None = None) -> None:
    ts = now_ts()
    with get_conn() as conn:
        if gold is not None or last_collect_ts is not None or accumulated_maintenance is not None:
            sets, vals = [], []
            if gold is not None:
                sets.append("gold = ?")
                vals.append(gold)
            if last_collect_ts is not None:
                sets.append("last_collect_ts = ?")
                vals.append(last_collect_ts)
            if accumulated_maintenance is not None:
                sets.append("accumulated_maintenance = ?")
                vals.append(accumulated_maintenance)
            sets.append("updated_at_ts = ?")
            vals.append(ts)
            conn.execute(f"UPDATE resources SET {', '.join(sets)} WHERE user_id = ?", (*vals, user_id))

        if troops is not None or last_train_ts is not None or power is not None or doctrine is not None or general_id is not None or strategist_id is not None:
            sets, vals = [], []
            if troops is not None:
                sets.append("troops = ?")
                vals.append(troops)
            if last_train_ts is not None:
                sets.append("last_train_ts = ?")
                vals.append(last_train_ts)
            if power is not None:
                sets.append("power = ?")
                vals.append(power)
            if doctrine is not None:
                sets.append("doctrine = ?")
                vals.append(doctrine)
            if general_id is not None:
                sets.append("general_id = ?")
                vals.append(general_id)
            if strategist_id is not None:
                sets.append("strategist_id = ?")
                vals.append(strategist_id)
            sets.append("updated_at_ts = ?")
            vals.append(ts)
            conn.execute(f"UPDATE army SET {', '.join(sets)} WHERE user_id = ?", (*vals, user_id))

        if barn_level is not None or barracks_level is not None or forge_level is not None:
            sets, vals = [], []
            if barn_level is not None:
                sets.append("barn_level = ?")
                vals.append(barn_level)
            if barracks_level is not None:
                sets.append("barracks_level = ?")
                vals.append(barracks_level)
            if forge_level is not None:
                sets.append("forge_level = ?")
                vals.append(forge_level)
            sets.append("updated_at_ts = ?")
            vals.append(ts)
            conn.execute(f"UPDATE domain_buildings SET {', '.join(sets)} WHERE user_id = ?", (*vals, user_id))

        conn.commit()


def action_feedback(title: str, delta_line: str, next_step: str) -> str:
    return f"✅ {title}\nΔ {delta_line}\nPróximo: {next_step}"


def do_collect(user_id: str) -> str:
    d = get_or_create_domain(user_id)
    now = now_ts()
    elapsed = effective_collect_seconds(now - d["last_collect_ts"])

    snap = economy_snapshot(
        barn_level=d["barn_level"],
        barracks_level=d["barracks_level"],
        forge_level=d["forge_level"],
        troops=d["troops"],
    )

    gross_gain = int(snap.production_per_hour * (elapsed / 3600))
    maintenance_cost = int(snap.total_maintenance_per_hour * (elapsed / 3600))
    net_gain = gross_gain - maintenance_cost

    new_gold = max(0, d["gold"] + net_gain)
    update_player_state(
        user_id,
        gold=new_gold,
        last_collect_ts=now,
        accumulated_maintenance=d["accumulated_maintenance"] + max(0, maintenance_cost),
    )

    return (
        "✅ Coleta concluída.\n"
        f"Δ Ouro bruto: +{gross_gain:,} | Manutenção: -{maintenance_cost:,} | Líquido: {net_gain:+,}\n"
        "Próximo: clique em **Treinar** ou abra **Construções**"
    ).replace(",", ".")


def do_train(user_id: str) -> str:
    d = get_or_create_domain(user_id)
    now = now_ts()
    delta = now - d["last_train_ts"]
    if delta < TRAIN_COOLDOWN_SECONDS:
        rest = TRAIN_COOLDOWN_SECONDS - delta
        return f"❌ Treino indisponível\nΔ Cooldown restante: {max(1, rest // 60)} min\nPróximo: aguarde e clique novamente"

    troops_gain = barracks_train_amount(d["barracks_level"])
    new_troops = d["troops"] + troops_gain
    with get_conn() as conn:
        g_bonus, s_bonus = get_slot_bonuses(conn, d["general_id"], d["strategist_id"])
    new_power = recalc_power(new_troops, d["barracks_level"], d["forge_level"], d["doctrine"], g_bonus, s_bonus)
    update_player_state(user_id, troops=new_troops, power=new_power, last_train_ts=now)

    return (
        "✅ Treino concluído.\n"
        f"Δ Tropas: +{troops_gain:,} | Poder: {new_power:,}\n"
        "Próximo: clique em **Operações** ou **Rank**"
    ).replace(",", ".")


def build_rank_embed() -> discord.Embed:
    with get_conn() as conn:
        rich = conn.execute(
            "SELECT d.user_id, r.gold FROM domains d JOIN resources r ON r.user_id=d.user_id ORDER BY r.gold DESC LIMIT 5"
        ).fetchall()
        war = conn.execute(
            "SELECT d.user_id, a.power FROM domains d JOIN army a ON a.user_id=d.user_id ORDER BY a.power DESC LIMIT 5"
        ).fetchall()

    def fmt(rows: list[sqlite3.Row], metric: str) -> str:
        if not rows:
            return "Sem dados."
        return "\n".join(f"{i}. <@{r['user_id']}> — {r[metric]:,}".replace(",", ".") for i, r in enumerate(rows, start=1))

    embed = discord.Embed(title="🏛️ Rankings Imperiais", color=discord.Color.blurple())
    embed.add_field(name="Magnatas (Ouro)", value=fmt(rich, "gold"), inline=False)
    embed.add_field(name="Senhores de Guerra (Poder)", value=fmt(war, "power"), inline=False)
    return embed


def build_dominio_embed(user_id: str) -> discord.Embed:
    d = get_or_create_domain(user_id)
    snap = economy_snapshot(
        barn_level=d["barn_level"],
        barracks_level=d["barracks_level"],
        forge_level=d["forge_level"],
        troops=d["troops"],
    )

    embed = discord.Embed(title="🏰 Domínio Imperial", color=discord.Color.dark_gold())
    embed.add_field(
        name="Recursos",
        value=(
            f"🪙 Ouro: **{d['gold']:,}**\n"
            f"⚙️ Manutenção/h: **{snap.total_maintenance_per_hour:,}**\n"
            f"📈 Saldo líquido/h: **{snap.net_per_hour:,}**"
        ).replace(",", "."),
        inline=False,
    )
    embed.add_field(
        name="Estruturas",
        value=(
            f"🌾 Celeiros T{d['barn_level']}\n"
            f"🛡️ Casernas T{d['barracks_level']}\n"
            f"🔨 Forja T{d['forge_level']}"
        ),
        inline=False,
    )
    embed.add_field(
        name="Militar",
        value=(
            f"👥 Tropas: **{d['troops']:,}**\n"
            f"⚔️ Poder: **{d['power']:,}**\n"
            f"🧭 Doutrina: **{d['doctrine']}**\n"
            f"🎖️ General slot: **{d['general_id'] or 'vazio'}**\n"
            f"📐 Estrategista slot: **{d['strategist_id'] or 'vazio'}**"
        ).replace(",", "."),
        inline=False,
    )
    embed.set_footer(text="Botões: Resgatar • Treinar • Construções • Militar • Operações • Rank")
    return embed


def build_construcoes_embed(user_id: str) -> discord.Embed:
    d = get_or_create_domain(user_id)

    def next_cost(kind: str, level: int) -> str:
        if level >= MAX_BUILDING_TIER:
            return "máximo"
        return f"{building_upgrade_cost(level, kind):,} ouro".replace(",", ".")

    embed = discord.Embed(title="🏗️ Painel de Construções", color=discord.Color.orange())
    embed.description = (
        f"🌾 Celeiros T{d['barn_level']} • próximo: {next_cost('celeiros', d['barn_level'])}\n"
        f"🛡️ Casernas T{d['barracks_level']} • próximo: {next_cost('casernas', d['barracks_level'])}\n"
        f"🔨 Forja T{d['forge_level']} • próximo: {next_cost('forja', d['forge_level'])}\n\n"
        "Use `!melhorar <celeiros|casernas|forja>` para upgrade."
    )
    embed.set_footer(text="Botão voltar retorna ao painel principal")
    return embed


class ConstrucoesView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Apenas o dono do painel pode usar estes botões.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⬅️ Voltar", style=discord.ButtonStyle.primary)
    async def btn_voltar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        embed = build_dominio_embed(str(interaction.user.id))
        await interaction.response.edit_message(embed=embed, view=DominioView(author_id=interaction.user.id))


class DominioView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            log_panel_event(
                user_id=str(interaction.user.id),
                guild_id=str(interaction.guild_id) if interaction.guild_id else None,
                event_name="panel_error",
                event_action="interaction_check",
                error_code="not_panel_owner",
            )
            await interaction.response.send_message("❌ Apenas o dono do painel pode usar estes botões.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Resgatar", style=discord.ButtonStyle.success)
    async def btn_resgatar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        log_panel_event(
            user_id=str(interaction.user.id),
            guild_id=str(interaction.guild_id) if interaction.guild_id else None,
            event_name="panel_action",
            event_action="resgatar",
        )
        msg = do_collect(str(interaction.user.id))
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="Treinar", style=discord.ButtonStyle.primary)
    async def btn_treinar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        log_panel_event(
            user_id=str(interaction.user.id),
            guild_id=str(interaction.guild_id) if interaction.guild_id else None,
            event_name="panel_action",
            event_action="treinar",
        )
        msg = do_train(str(interaction.user.id))
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="Construções", style=discord.ButtonStyle.secondary)
    async def btn_construcoes(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        log_panel_event(
            user_id=str(interaction.user.id),
            guild_id=str(interaction.guild_id) if interaction.guild_id else None,
            event_name="panel_action",
            event_action="construcoes",
        )
        embed = build_construcoes_embed(str(interaction.user.id))
        await interaction.response.edit_message(embed=embed, view=ConstrucoesView(author_id=interaction.user.id))

    @discord.ui.button(label="Militar", style=discord.ButtonStyle.secondary)
    async def btn_militar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        log_panel_event(
            user_id=str(interaction.user.id),
            guild_id=str(interaction.guild_id) if interaction.guild_id else None,
            event_name="panel_action",
            event_action="militar",
        )
        d = get_or_create_domain(str(interaction.user.id))
        await interaction.response.send_message(
            (
                "✅ Painel militar aberto.\n"
                f"Δ Doutrina: {d['doctrine']} | General: {d['general_id'] or 'vazio'} | Estrategista: {d['strategist_id'] or 'vazio'}\n"
                "Próximo: use `!doutrina` / `!equipar_general` / `!equipar_estrategista`"
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Operações", style=discord.ButtonStyle.secondary)
    async def btn_operacoes(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        log_panel_event(
            user_id=str(interaction.user.id),
            guild_id=str(interaction.guild_id) if interaction.guild_id else None,
            event_name="panel_action",
            event_action="operacoes",
        )
        with get_conn() as conn:
            ops = conn.execute("SELECT key, title, min_barracks_level, requires_strategist FROM operations ORDER BY id").fetchall()
        d = get_or_create_domain(str(interaction.user.id))
        lines = []
        for op in ops:
            reason = "OK"
            if d["barracks_level"] < op["min_barracks_level"]:
                reason = f"Requer Casernas T{op['min_barracks_level']}+"
            elif op["requires_strategist"] and not d["strategist_id"]:
                reason = "Requer estrategista equipado"
            lines.append(f"• `{op['key']}` — {reason}")
        await interaction.response.send_message(
            "✅ Painel de operações aberto.\n"
            f"Δ Operações mapeadas: {len(lines)}\n"
            "\n".join(lines)
            + "\nPróximo: use `!simular_operacao <key>`",
            ephemeral=True,
        )

    @discord.ui.button(label="Rank", style=discord.ButtonStyle.secondary)
    async def btn_rank(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        log_panel_event(
            user_id=str(interaction.user.id),
            guild_id=str(interaction.guild_id) if interaction.guild_id else None,
            event_name="panel_action",
            event_action="rank",
        )
        await interaction.response.send_message(embed=build_rank_embed(), ephemeral=True)


@bot.command(name="dominio")
async def dominio(ctx: commands.Context) -> None:
    log_panel_event(
        user_id=str(ctx.author.id),
        guild_id=str(ctx.guild.id) if ctx.guild else None,
        event_name="panel_open",
        event_action="dominio",
    )
    embed = build_dominio_embed(str(ctx.author.id))
    await ctx.send(embed=embed, view=DominioView(author_id=ctx.author.id))


@bot.command(name="coletar")
async def coletar(ctx: commands.Context) -> None:
    await ctx.send(do_collect(str(ctx.author.id)))


@bot.command(name="treinar")
async def treinar(ctx: commands.Context) -> None:
    await ctx.send(do_train(str(ctx.author.id)))


@bot.command(name="melhorar")
async def melhorar(ctx: commands.Context, estrutura: str | None = None) -> None:
    if not estrutura:
        await ctx.send("Uso: `!melhorar <celeiros|casernas|forja>`")
        return

    estrutura = estrutura.strip().lower()
    if estrutura not in {"celeiros", "casernas", "forja"}:
        await ctx.send("Estrutura inválida. Use: `celeiros`, `casernas` ou `forja`.")
        return

    user_id = str(ctx.author.id)
    d = get_or_create_domain(user_id)

    level_key = {"celeiros": "barn_level", "casernas": "barracks_level", "forja": "forge_level"}[estrutura]
    level = d[level_key]
    if level >= MAX_BUILDING_TIER:
        await ctx.send(f"❌ {estrutura.title()} já está no nível máximo (T{MAX_BUILDING_TIER}).")
        return
    cost = building_upgrade_cost(level, estrutura)
    if d["gold"] < cost:
        await ctx.send(f"❌ Ouro insuficiente. Falta {(cost - d['gold']):,}.".replace(",", "."))
        return

    new_level = level + 1
    params = {"gold": d["gold"] - cost, level_key: new_level}
    if estrutura in {"casernas", "forja"}:
        barracks_level = new_level if estrutura == "casernas" else d["barracks_level"]
        forge_level = new_level if estrutura == "forja" else d["forge_level"]
        with get_conn() as conn:
            g_bonus, s_bonus = get_slot_bonuses(conn, d["general_id"], d["strategist_id"])
        params["power"] = recalc_power(d["troops"], barracks_level, forge_level, d["doctrine"], g_bonus, s_bonus)

    update_player_state(user_id, **params)
    upgrade_secs = building_upgrade_time_seconds(new_level)

    await ctx.send(
        (
            f"✅ Upgrade concluído: **{estrutura} T{new_level}**.\n"
            f"Δ Ouro: -{cost:,}\n"
            f"⏱️ Referência de tempo (tier alvo): {upgrade_secs // 60} min\n"
            "Próximo: `!dominio` para ver o impacto."
        ).replace(",", ".")
    )


@bot.command(name="doutrina")
async def doutrina(ctx: commands.Context, estilo: str | None = None) -> None:
    if not estilo:
        await ctx.send("Uso: `!doutrina <cerco|choque|furtivo|arcano>`")
        return
    estilo = estilo.strip().lower()
    if estilo not in DOCTRINES:
        await ctx.send("Doutrina inválida. Use `cerco`, `choque`, `furtivo` ou `arcano`.")
        return

    user_id = str(ctx.author.id)
    d = get_or_create_domain(user_id)
    with get_conn() as conn:
        g_bonus, s_bonus = get_slot_bonuses(conn, d["general_id"], d["strategist_id"])
    new_power = recalc_power(d["troops"], d["barracks_level"], d["forge_level"], estilo, g_bonus, s_bonus)
    update_player_state(user_id, doctrine=estilo, power=new_power)
    await ctx.send(f"✅ Doutrina alterada para **{estilo}**. Novo poder: **{new_power:,}**".replace(",", "."))


@bot.command(name="recrutar_general")
async def recrutar_general(ctx: commands.Context, *, nome: str | None = None) -> None:
    if not nome:
        await ctx.send("Uso: `!recrutar_general <nome>`")
        return
    user_id = str(ctx.author.id)
    ts = now_ts()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO generals (user_id, name, rank, equipped, created_at_ts) VALUES (?, ?, 'C', 0, ?)",
            (user_id, nome.strip()[:50], ts),
        )
        conn.commit()
    await ctx.send("✅ General recrutado. Use `!equipar_general <id>` para equipar.")


@bot.command(name="equipar_general")
async def equipar_general(ctx: commands.Context, general_id: int | None = None) -> None:
    if not general_id:
        await ctx.send("Uso: `!equipar_general <id>`")
        return
    user_id = str(ctx.author.id)
    d = get_or_create_domain(user_id)
    with get_conn() as conn:
        g = conn.execute("SELECT id FROM generals WHERE id = ? AND user_id = ?", (general_id, user_id)).fetchone()
        if not g:
            await ctx.send("❌ General não encontrado para este jogador.")
            return
        conn.execute("UPDATE generals SET equipped = 0 WHERE user_id = ?", (user_id,))
        conn.execute("UPDATE generals SET equipped = 1 WHERE id = ?", (general_id,))
        conn.commit()
        g_bonus, s_bonus = get_slot_bonuses(conn, general_id, d["strategist_id"])
    new_power = recalc_power(d["troops"], d["barracks_level"], d["forge_level"], d["doctrine"], g_bonus, s_bonus)
    update_player_state(user_id, general_id=general_id, power=new_power)
    await ctx.send(f"✅ General equipado (id {general_id}). Poder atualizado: {new_power:,}".replace(",", "."))


@bot.command(name="recrutar_estrategista")
async def recrutar_estrategista(ctx: commands.Context, *, nome: str | None = None) -> None:
    if not nome:
        await ctx.send("Uso: `!recrutar_estrategista <nome>`")
        return
    user_id = str(ctx.author.id)
    d = get_or_create_domain(user_id)
    with get_conn() as conn:
        ok, msg = has_strategist_gate(d, conn)
        if not ok:
            await ctx.send(f"❌ {msg}")
            return
        conn.execute(
            "INSERT INTO strategists (user_id, name, rank, equipped, created_at_ts) VALUES (?, ?, 'C', 0, ?)",
            (user_id, nome.strip()[:50], now_ts()),
        )
        conn.commit()
    await ctx.send("✅ Estrategista recrutado. Use `!equipar_estrategista <id>` para equipar.")


@bot.command(name="equipar_estrategista")
async def equipar_estrategista(ctx: commands.Context, strategist_id: int | None = None) -> None:
    if not strategist_id:
        await ctx.send("Uso: `!equipar_estrategista <id>`")
        return
    user_id = str(ctx.author.id)
    d = get_or_create_domain(user_id)
    with get_conn() as conn:
        ok, msg = has_strategist_gate(d, conn)
        if not ok:
            await ctx.send(f"❌ {msg}")
            return
        srow = conn.execute("SELECT id FROM strategists WHERE id = ? AND user_id = ?", (strategist_id, user_id)).fetchone()
        if not srow:
            await ctx.send("❌ Estrategista não encontrado para este jogador.")
            return
        conn.execute("UPDATE strategists SET equipped = 0 WHERE user_id = ?", (user_id,))
        conn.execute("UPDATE strategists SET equipped = 1 WHERE id = ?", (strategist_id,))
        conn.commit()
        g_bonus, s_bonus = get_slot_bonuses(conn, d["general_id"], strategist_id)
    new_power = recalc_power(d["troops"], d["barracks_level"], d["forge_level"], d["doctrine"], g_bonus, s_bonus)
    update_player_state(user_id, strategist_id=strategist_id, power=new_power)
    await ctx.send(f"✅ Estrategista equipado (id {strategist_id}). Poder atualizado: {new_power:,}".replace(",", "."))


@bot.command(name="simular_operacao")
async def simular_operacao(ctx: commands.Context, key: str | None = None) -> None:
    if not key:
        await ctx.send("Uso: `!simular_operacao <tumba_sultao|ruinas_muralha|estrada_cinzas>`")
        return
    user_id = str(ctx.author.id)
    d = get_or_create_domain(user_id)
    with get_conn() as conn:
        op = conn.execute("SELECT * FROM operations WHERE key = ?", (key.strip().lower(),)).fetchone()
        if not op:
            await ctx.send("❌ Operação inválida.")
            return
        if d["barracks_level"] < op["min_barracks_level"]:
            await ctx.send(f"❌ Requisito ausente: Casernas T{op['min_barracks_level']}+.")
            return
        if op["requires_strategist"] and not d["strategist_id"]:
            await ctx.send("❌ Requisito ausente: Estrategista equipado para esta operação.")
            return
        if d["troops"] <= 0:
            await ctx.send("❌ Requisito ausente: sem tropas não há incursão.")
            return
        chance = simulate_operation_success_chance(d["power"], op["difficulty_power"], d["doctrine"], op["preferred_doctrine"])

    outcome = "vitória tática" if random.random() <= chance else "falha tática"
    troops_lost = int(max(1, d["troops"] * op["base_risk_percent"] * (0.4 if outcome == "vitória tática" else 0.8)))
    base_gold_delta = int(op["base_gold_reward"] * (1.0 if outcome == "vitória tática" else 0.2))
    forge_mult = 1.0 + (d["forge_level"] - 1) * 0.03
    gold_delta = int(base_gold_delta * forge_mult)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO operation_runs (user_id, operation_id, outcome, troops_lost, gold_delta, created_at_ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, op["id"], outcome, troops_lost, gold_delta, now_ts()),
        )
        conn.commit()

    relic_line = "Nenhum achado relevante."
    if d["forge_level"] >= 4 and random.random() <= min(0.20, 0.04 + d["forge_level"] * 0.01):
        relic_line = "Achado: fragmento relicário encontrado na incursão."

    await ctx.send(
        (
            f"🧪 Simulação `{op['title']}`\n"
            f"Poder atual: {d['power']:,} | Dificuldade: {op['difficulty_power']:,}\n"
            f"Chance estimada: {chance*100:.1f}%\n"
            f"Resultado simulado: **{outcome}**\n"
            f"Registro: perdas estimadas {troops_lost:,} tropas | recompensa base {gold_delta:,} ouro\n"
            f"{relic_line}"
        ).replace(",", ".")
    )



@bot.command(name="forjar")
async def forjar(ctx: commands.Context) -> None:
    user_id = str(ctx.author.id)
    d = get_or_create_domain(user_id)
    cost = 50_000 + (d["forge_level"] - 1) * 35_000
    if d["gold"] < cost:
        await ctx.send(f"❌ Ouro insuficiente para forja. Falta {(cost - d['gold']):,}.".replace(",", "."))
        return

    tier = d["forge_level"]
    chance_fragmento = min(0.85, 0.35 + tier * 0.04)
    chance_reliquia = min(0.25, 0.01 + tier * 0.015)
    roll = random.random()

    achado = "Escória comum (sem valor)."
    if roll <= chance_reliquia:
        achado = "Relíquia menor forjada (R)."
    elif roll <= chance_fragmento:
        achado = "Fragmento arcano recuperado (C)."

    update_player_state(user_id, gold=d["gold"] - cost)
    await ctx.send(
        (
            f"🔨 Forja concluída (T{tier}).\n"
            f"Δ Ouro: -{cost:,}\n"
            f"Resultado: {achado}\n"
            "Próximo: `!simular_operacao` para buscar achados em campo."
        ).replace(",", ".")
    )




@bot.command(name="rank")
async def rank(ctx: commands.Context) -> None:
    await ctx.send(embed=build_rank_embed())


@bot.command(name="economia_teste")
@commands.has_permissions(administrator=True)
async def economia_teste(ctx: commands.Context) -> None:
    fake = economy_snapshot(barn_level=4, barracks_level=3, forge_level=2, troops=1750)
    window_seconds = 6 * 3600
    net_window = net_balance_for_window_seconds(fake, window_seconds)
    cost_barn_t4 = building_upgrade_cost(4, "celeiros")

    await ctx.send(
        (
            "🧪 Fase 1 • teste com jogador fake\n"
            f"Produção/h: {fake.production_per_hour:,}\n"
            f"Manutenção edifícios/h: {fake.building_maintenance_per_hour:,}\n"
            f"Manutenção militar/h: {fake.military_maintenance_per_hour:,}\n"
            f"Manutenção total/h: {fake.total_maintenance_per_hour:,}\n"
            f"Saldo líquido/h: {fake.net_per_hour:+,}\n"
            f"Custo upgrade celeiros (nível 4->5): {cost_barn_t4:,}\n"
            f"Saldo líquido em 6h: {net_window:+,}"
        ).replace(",", ".")
    )


@economia_teste.error
async def economia_teste_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Apenas administradores podem usar `!economia_teste`.")
        return
    logger.exception("Erro em !economia_teste", exc_info=error)
    await ctx.send("Erro interno no teste de economia.")


@bot.command(name="guia")
async def guia(ctx: commands.Context) -> None:
    await ctx.send(
        "**Núcleo C — Fase 1 ativa.**\n"
        "Comandos: `!dominio`, `!coletar`, `!treinar`, `!melhorar`, `!doutrina`, `!recrutar_general`, `!equipar_general`, `!recrutar_estrategista`, `!equipar_estrategista`, `!forjar`, `!simular_operacao`, `!rank`, `!economia_teste`, `!diagnostico`, `!guia`.\n"
        "Loop: Coletar → Melhorar → Treinar → Rank."
    )


@bot.command(name="diagnostico")
@commands.has_permissions(administrator=True)
async def diagnostico(ctx: commands.Context) -> None:
    with get_conn() as conn:
        counts = {}
        for table in [
            "domains", "domain_buildings", "resources", "army", "generals", "strategists", "operations",
            "operation_runs", "items", "inventories", "season_state", "season_scores", "panel_events",
        ]:
            counts[table] = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]

    lines = [f"{k}: {v}" for k, v in counts.items()]
    await ctx.send(f"Diagnóstico Fase 1\nDB: `{DB_PATH}`\n" + "\n".join(lines))


@bot.command(name="painel_kpis")
@commands.has_permissions(administrator=True)
async def painel_kpis(ctx: commands.Context) -> None:
    week_ago = now_ts() - (7 * 24 * 3600)
    with get_conn() as conn:
        opens = conn.execute(
            "SELECT COUNT(*) c FROM panel_events WHERE event_name = 'panel_open' AND created_at_ts >= ?",
            (week_ago,),
        ).fetchone()["c"]
        errors = conn.execute(
            "SELECT COUNT(*) c FROM panel_events WHERE event_name = 'panel_error' AND created_at_ts >= ?",
            (week_ago,),
        ).fetchone()["c"]
        actions = conn.execute(
            "SELECT COUNT(*) c FROM panel_events WHERE event_name = 'panel_action' AND created_at_ts >= ?",
            (week_ago,),
        ).fetchone()["c"]
        unique_open_users = conn.execute(
            "SELECT COUNT(DISTINCT user_id) c FROM panel_events WHERE event_name = 'panel_open' AND created_at_ts >= ?",
            (week_ago,),
        ).fetchone()["c"]
        active_users = conn.execute(
            "SELECT COUNT(DISTINCT user_id) c FROM panel_events WHERE created_at_ts >= ?",
            (week_ago,),
        ).fetchone()["c"]
        by_button = conn.execute(
            """
            SELECT event_action, COUNT(*) c
            FROM panel_events
            WHERE event_name = 'panel_action' AND created_at_ts >= ?
            GROUP BY event_action
            ORDER BY c DESC
            """,
            (week_ago,),
        ).fetchall()

    adoption = (unique_open_users / active_users * 100.0) if active_users else 0.0
    error_rate = (errors / (actions + errors) * 100.0) if (actions + errors) else 0.0
    action_per_open = (actions / opens) if opens else 0.0

    lines = [f"• {r['event_action']}: {r['c']}" for r in by_button] if by_button else ["• sem dados"]
    await ctx.send(
        "📊 KPIs do Painel (7 dias)\n"
        f"Adoção painel: {adoption:.1f}% (meta ≥ 70%)\n"
        f"Erro de uso: {error_rate:.1f}% (meta ≤ 15%)\n"
        f"Ações por sessão: {action_per_open:.2f} (meta ≥ 2.5)\n"
        f"Usuários com panel_open: {unique_open_users} | Usuários ativos: {active_users}\n"
        "Ações por botão:\n" + "\n".join(lines)
    )


@painel_kpis.error
async def painel_kpis_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Apenas administradores podem usar `!painel_kpis`.")
        return
    logger.exception("Erro em !painel_kpis", exc_info=error)
    await ctx.send("Erro interno no relatório de KPIs.")


@diagnostico.error
async def diagnostico_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Apenas administradores podem usar `!diagnostico`.")
        return
    logger.exception("Erro em !diagnostico", exc_info=error)
    await ctx.send("Erro interno no diagnóstico.")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    logger.exception("Erro de comando", exc_info=error)
    await ctx.send("Erro interno ao executar comando.")


@bot.event
async def on_ready() -> None:
    logger.info("Conectado como %s", bot.user)


def main() -> None:
    init_db()
    try:
        token = resolve_token()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    bot.run(token)


if __name__ == "__main__":
    main()
