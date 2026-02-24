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
from services.gameplay import GameplayService
from ui.views import DominioView as UIDominioView, PanelDeps

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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS discoveries_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                source TEXT NOT NULL,
                item_id INTEGER,
                rarity TEXT NOT NULL,
                fragment_text TEXT NOT NULL,
                impact_text TEXT NOT NULL,
                created_at_ts INTEGER NOT NULL,
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
        ensure_column(conn, "operations", "requires_general", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "operations", "prestige_reward", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "operations", "partial_without_strategist", "INTEGER NOT NULL DEFAULT 0")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_operation_runs_user ON operation_runs(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_generals_user ON generals(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_strategists_user ON strategists(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_panel_events_user ON panel_events(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_panel_events_name ON panel_events(event_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discoveries_user ON discoveries_log(user_id)")

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
            ('cronica_heroi_sem_tumulo', 'Crônica do Herói Sem Túmulo', 'L', 'Salvou o mundo e perdeu o nome.'),
            ('selo_legiao_ss', 'Selo Quebrado da Legião', 'SS', 'Um juramento que ainda sangra no metal.'),
            ('estandarte_sss', 'Estandarte da Vigília Ausente', 'SSS', 'Quando caiu, ninguém ousou recolher.'),
            ('lamina_sssp', 'Lâmina da Era Velada', 'SSS+', 'A lâmina lembra nomes que o mundo apagou.'),
            ('trono_99999', 'Fragmento do Trono Impronunciável', '99999', 'Não foi encontrado. Foi permitido.')
            """
        )

        conn.execute(
            """
            UPDATE operations
            SET difficulty_power = 2200,
                preferred_doctrine = 'furtivo',
                requires_general = 1,
                requires_strategist = 1,
                partial_without_strategist = 1,
                prestige_reward = 10
            WHERE key = 'tumba_sultao'
            """
        )
        conn.execute(
            """
            UPDATE operations
            SET difficulty_power = 3500,
                preferred_doctrine = 'cerco',
                requires_general = 1,
                prestige_reward = 14
            WHERE key = 'ruinas_muralha'
            """
        )
        conn.execute(
            """
            UPDATE operations
            SET difficulty_power = 1600,
                preferred_doctrine = 'choque',
                prestige_reward = 6
            WHERE key = 'estrada_cinzas'
            """
        )

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


def resolve_discovery(user_id: str, source: str, forge_level: int) -> str:
    roll = random.random()
    rarity = "C"
    if roll <= 1e-10:
        rarity = "99999"
    elif roll <= 1e-8:
        rarity = "SSS+"
    elif roll <= 1e-5:
        rarity = "SSS"
    elif roll <= 1e-4:
        rarity = "SS"
    elif roll <= min(0.02, 0.003 + forge_level * 0.001):
        rarity = "R"
    elif roll <= min(0.70, 0.28 + forge_level * 0.03):
        rarity = "C"
    else:
        return "Nenhum achado relevante."

    with get_conn() as conn:
        item = conn.execute(
            "SELECT id, name, lore FROM items WHERE rarity = ? ORDER BY RANDOM() LIMIT 1", (rarity,)
        ).fetchone()
        if not item:
            return "Nenhum achado relevante."

        conn.execute(
            "INSERT INTO inventories (user_id, item_id, quantity) VALUES (?, ?, 1) "
            "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + 1",
            (user_id, item["id"]),
        )

        impact = {
            "C": "+1% ouro da próxima coleta",
            "R": "+2% recompensa base na próxima operação",
            "SS": "+1% poder temporário narrativo",
            "SSS": "+2% poder temporário narrativo",
            "SSS+": "+3% poder temporário narrativo",
            "99999": "registro lendário permanente nos Anais",
        }.get(rarity, "eco narrativo")

        fragment = f"{item['name']}: {item['lore']}"
        conn.execute(
            """
            INSERT INTO discoveries_log (user_id, source, item_id, rarity, fragment_text, impact_text, created_at_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, source, item["id"], rarity, fragment, impact, now_ts()),
        )
        conn.commit()

    return (
        f"📜 Descoberta: **{item['name']}** [{rarity}]\n"
        f"Impacto: {impact}\n"
        f"Registro nos Anais: {fragment}"
    )


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


gameplay = GameplayService(
    max_building_tier=MAX_BUILDING_TIER,
    doctrines=DOCTRINES,
    get_or_create_domain=get_or_create_domain,
    get_conn=get_conn,
    update_player_state=update_player_state,
    get_slot_bonuses=get_slot_bonuses,
    has_strategist_gate=has_strategist_gate,
    now_ts=now_ts,
    resolve_discovery=resolve_discovery,
)

def do_collect(user_id: str) -> str:
    return gameplay.do_collect(user_id)


def do_train(user_id: str) -> str:
    return gameplay.do_train(user_id)


def do_upgrade(user_id: str, estrutura: str) -> str:
    return gameplay.do_upgrade(user_id, estrutura)


def do_set_doctrine(user_id: str, doctrine: str) -> str:
    return gameplay.do_set_doctrine(user_id, doctrine)


def do_recruit_general_auto(user_id: str) -> str:
    return gameplay.do_recruit_general_auto(user_id)


def do_equip_general(user_id: str, general_id: int) -> str:
    return gameplay.do_equip_general(user_id, general_id)


def do_recruit_strategist_auto(user_id: str) -> str:
    return gameplay.do_recruit_strategist_auto(user_id)


def do_equip_strategist(user_id: str, strategist_id: int) -> str:
    return gameplay.do_equip_strategist(user_id, strategist_id)


def do_simular_operacao(user_id: str, key: str) -> str:
    return gameplay.do_simular_operacao(user_id, key)


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

    now = now_ts()
    elapsed = effective_collect_seconds(now - d["last_collect_ts"])
    pending_gross = int(snap.production_per_hour * (elapsed / 3600))
    pending_maint = int(snap.total_maintenance_per_hour * (elapsed / 3600))
    pending_net = pending_gross - pending_maint

    embed = discord.Embed(title="🏰 Domínio Imperial", color=discord.Color.dark_gold())
    embed.add_field(
        name="Recursos",
        value=(
            f"🪙 Ouro: **{d['gold']:,}**\n"
            f"💰 Ouro resgatável: **{pending_net:+,}**\n"
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


def build_construcoes_embed(user_id: str, notice: str | None = None) -> discord.Embed:
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
    if notice:
        embed.add_field(name="Ação", value=notice, inline=False)
    embed.add_field(
        name="Fluxo",
        value=(
            "✅ Painel de construções aberto\n"
            "Δ Visualização de tiers e custos carregada\n"
            "Próximo: `!melhorar <celeiros|casernas|forja>` ou clique em ⬅️ Voltar"
        ),
        inline=False,
    )
    return embed


def build_militar_embed(user_id: str, notice: str | None = None) -> discord.Embed:
    d = get_or_create_domain(user_id)
    embed = discord.Embed(title="🛡️ Painel Militar", color=discord.Color.dark_teal())
    embed.description = (
        f"Doutrina: **{d['doctrine']}**\n"
        f"General slot: **{d['general_id'] or 'vazio'}**\n"
        f"Estrategista slot: **{d['strategist_id'] or 'vazio'}**\n"
        f"Poder atual: **{d['power']:,}**"
    ).replace(",", ".")
    if notice:
        embed.add_field(name="Ação", value=notice, inline=False)
    embed.add_field(
        name="Fluxo",
        value=(
            "✅ Composição militar pronta\n"
            "Δ Doutrina e slots alteram o poder\n"
            "Próximo: ajuste doutrina/slots e volte ao Domínio"
        ),
        inline=False,
    )
    embed.set_footer(text="Use os botões para gerir doutrina e slots")
    return embed


def build_operacoes_embed(user_id: str, notice: str | None = None) -> discord.Embed:
    d = get_or_create_domain(user_id)
    with get_conn() as conn:
        ops = conn.execute("SELECT * FROM operations ORDER BY id").fetchall()
    lines: list[str] = []
    for op in ops:
        status = "✅ disponível"
        if d["barracks_level"] < op["min_barracks_level"]:
            status = f"🔒 Casernas T{op['min_barracks_level']}+"
        elif op["requires_general"] and not d["general_id"]:
            status = "🔒 requer general equipado"
        elif op["requires_strategist"] and not d["strategist_id"]:
            if op["partial_without_strategist"]:
                status = "⚠️ sem estrategista: apenas rota parcial"
            else:
                status = "🔒 requer estrategista equipado"
        lines.append(f"• `{op['key']}` — {status}")

    embed = discord.Embed(title="⚔️ Painel de Operações", color=discord.Color.dark_red())
    embed.description = "\n".join(lines) if lines else "Nenhuma operação cadastrada."
    if notice:
        embed.add_field(name="Ação", value=notice, inline=False)
    embed.add_field(
        name="Fluxo",
        value=(
            "✅ Operações verificadas por requisito\n"
            "Δ Simulação grava histórico em operation_runs\n"
            "Próximo: escolha uma operação no seletor"
        ),
        inline=False,
    )
    embed.set_footer(text="Operações usam barracks tier, tropas e slot de estrategista")
    return embed


def build_panel_deps() -> PanelDeps:
    return PanelDeps(
        service=gameplay,
        build_dominio_embed=build_dominio_embed,
        build_construcoes_embed=build_construcoes_embed,
        build_militar_embed=build_militar_embed,
        build_operacoes_embed=build_operacoes_embed,
        build_rank_embed=build_rank_embed,
        get_conn=get_conn,
        get_or_create_domain=get_or_create_domain,
        log_panel_event=log_panel_event,
    )


@bot.command(name="dominio")
async def dominio(ctx: commands.Context) -> None:
    log_panel_event(
        user_id=str(ctx.author.id),
        guild_id=str(ctx.guild.id) if ctx.guild else None,
        event_name="panel_open",
        event_action="dominio",
    )
    embed = build_dominio_embed(str(ctx.author.id))
    await ctx.send(embed=embed, view=UIDominioView(author_id=ctx.author.id, deps=build_panel_deps()))


@bot.command(name="coletar", hidden=True)
async def coletar(ctx: commands.Context) -> None:
    await ctx.send(do_collect(str(ctx.author.id)))


@bot.command(name="treinar", hidden=True)
async def treinar(ctx: commands.Context) -> None:
    await ctx.send(do_train(str(ctx.author.id)))


@bot.command(name="melhorar", hidden=True)
async def melhorar(ctx: commands.Context, estrutura: str | None = None) -> None:
    if not estrutura:
        await ctx.send("Uso: `!melhorar <celeiros|casernas|forja>`")
        return
    await ctx.send(do_upgrade(str(ctx.author.id), estrutura.strip().lower()))


@bot.command(name="doutrina", hidden=True)
async def doutrina(ctx: commands.Context, estilo: str | None = None) -> None:
    if not estilo:
        await ctx.send("Uso: `!doutrina <cerco|choque|furtivo|arcano>`")
        return
    await ctx.send(do_set_doctrine(str(ctx.author.id), estilo))


@bot.command(name="recrutar_general", hidden=True)
async def recrutar_general(ctx: commands.Context, *, nome: str | None = None) -> None:
    if not nome:
        await ctx.send("Uso: `!recrutar_general <nome>`")
        return
    await ctx.send(do_recruit_general_auto(str(ctx.author.id)))


@bot.command(name="equipar_general", hidden=True)
async def equipar_general(ctx: commands.Context, general_id: int | None = None) -> None:
    if not general_id:
        await ctx.send("Uso: `!equipar_general <id>`")
        return
    await ctx.send(do_equip_general(str(ctx.author.id), general_id))


@bot.command(name="recrutar_estrategista", hidden=True)
async def recrutar_estrategista(ctx: commands.Context, *, nome: str | None = None) -> None:
    if not nome:
        await ctx.send("Uso: `!recrutar_estrategista <nome>`")
        return
    await ctx.send(do_recruit_strategist_auto(str(ctx.author.id)))


@bot.command(name="equipar_estrategista", hidden=True)
async def equipar_estrategista(ctx: commands.Context, strategist_id: int | None = None) -> None:
    if not strategist_id:
        await ctx.send("Uso: `!equipar_estrategista <id>`")
        return
    await ctx.send(do_equip_strategist(str(ctx.author.id), strategist_id))


@bot.command(name="simular_operacao", hidden=True)
async def simular_operacao(ctx: commands.Context, key: str | None = None) -> None:
    if not key:
        await ctx.send("Uso: `!simular_operacao <tumba_sultao|ruinas_muralha|estrada_cinzas>`")
        return
    await ctx.send(do_simular_operacao(str(ctx.author.id), key))



@bot.command(name="forjar", hidden=True)
async def forjar(ctx: commands.Context) -> None:
    user_id = str(ctx.author.id)
    d = get_or_create_domain(user_id)
    cost = 50_000 + (d["forge_level"] - 1) * 35_000
    if d["gold"] < cost:
        await ctx.send(f"❌ Ouro insuficiente para forja. Falta {(cost - d['gold']):,}.".replace(",", "."))
        return

    tier = d["forge_level"]
    achado = resolve_discovery(user_id, "forja", tier)

    update_player_state(user_id, gold=d["gold"] - cost)
    await ctx.send(
        (
            f"🔨 Forja concluída (T{tier}).\n"
            f"Δ Ouro: -{cost:,}\n"
            f"Resultado: {achado}\n"
            "Próximo: `!simular_operacao` para buscar achados em campo."
        ).replace(",", ".")
    )


@bot.command(name="anais", hidden=True)
async def anais(ctx: commands.Context) -> None:
    user_id = str(ctx.author.id)
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT rarity, fragment_text, impact_text, created_at_ts
            FROM discoveries_log
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 8
            """,
            (user_id,),
        ).fetchall()

    if not rows:
        await ctx.send("Nenhum registro encontrado nos Anais. A lore ainda não te encontrou.")
        return

    lines = []
    for r in rows:
        lines.append(
            f"• [{r['rarity']}] {r['fragment_text']}\n"
            f"  ↳ Impacto: {r['impact_text']}"
        )
    await ctx.send("📖 Anais de Descobertas\n" + "\n".join(lines))




@bot.command(name="rank")
async def rank(ctx: commands.Context) -> None:
    await ctx.send(embed=build_rank_embed())


@bot.command(name="economia_teste", hidden=True)
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
    embed = discord.Embed(
        title="📘 Guia do Feudo — EBR Núcleo C",
        description=(
            "Entrada recomendada: `!dominio` (painel central).\n"
            "Você joga quase tudo por botões: **Resgatar → Construções/Militar → Operações → Rank**."
        ),
        color=discord.Color.dark_gold(),
    )
    embed.add_field(
        name="Comece em 30 segundos",
        value=(
            "1) `!dominio` abre seu painel\n"
            "2) clique em **Resgatar** para gerar ouro\n"
            "3) clique em **Construções** e use `🛠️ Melhorar`\n"
            "4) clique em **Militar** para definir doutrina/slots\n"
            "5) clique em **Operações** para simular incursões"
        ),
        inline=False,
    )
    embed.add_field(
        name="Comandos públicos (uso normal)",
        value=(
            "`!dominio` → painel principal do feudo\n"
            "`!rank` → ranking de riqueza e poder\n"
            "`!guia` → este guia"
        ),
        inline=False,
    )
    embed.add_field(
        name="Comandos avançados (atalhos textuais)",
        value=(
            "`!coletar` • `!treinar` • `!melhorar <celeiros|casernas|forja>`\n"
            "`!doutrina <cerco|choque|furtivo|arcano>`\n"
            "`!recrutar_general <nome>` • `!equipar_general <id>`\n"
            "`!recrutar_estrategista <nome>` • `!equipar_estrategista <id>`\n"
            "`!simular_operacao <tumba_sultao|ruinas_muralha|estrada_cinzas>`\n"
            "`!forjar` • `!anais`"
        ),
        inline=False,
    )
    embed.add_field(
        name="Como evoluir rápido",
        value=(
            "• Sem ouro, seu progresso trava (priorize **Resgatar** + **Celeiros**)\n"
            "• Sem tropa, não há incursão (fortaleça **Casernas**)\n"
            "• Sem forja, menos chance de achados raros (suba **Forja**)\n"
            "• Operações exigem composição real (General/Estrategista em gates)"
        ),
        inline=False,
    )
    embed.add_field(
        name="Operações (raids narrativas)",
        value=(
            "Cada operação tem **requisito + risco + recompensa**.\n"
            "Ex.: `tumba_sultao` pede Casernas T3+, General e Estrategista para rota completa."
        ),
        inline=False,
    )
    embed.add_field(
        name="Comandos admin",
        value="`!diagnostico` • `!painel_kpis` • `!economia_teste`",
        inline=False,
    )
    embed.set_footer(text="Dica: se uma subview expirar, use o botão 🔄 Reabrir Painel")
    await ctx.send(embed=embed)


@bot.command(name="diagnostico", hidden=True)
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


@bot.command(name="painel_kpis", hidden=True)
@commands.has_permissions(administrator=True)
async def painel_kpis(ctx: commands.Context) -> None:
    week_ago = now_ts() - (7 * 24 * 3600)
    day_seconds = 24 * 3600
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
        requirement_errors = conn.execute(
            """
            SELECT COUNT(*) c
            FROM panel_events
            WHERE event_name = 'panel_error'
              AND error_code = 'requirement_missing'
              AND created_at_ts >= ?
            """,
            (week_ago,),
        ).fetchone()["c"]

        users_3x_day = conn.execute(
            """
            SELECT COUNT(*) c FROM (
                SELECT user_id
                FROM panel_events
                WHERE event_name = 'panel_open' AND created_at_ts >= ?
                GROUP BY user_id, (created_at_ts / ?)
                HAVING COUNT(*) >= 3
            )
            """,
            (week_ago, day_seconds),
        ).fetchone()["c"]

        avg_time_first_action = conn.execute(
            """
            WITH first_open AS (
                SELECT user_id, MIN(created_at_ts) AS open_ts
                FROM panel_events
                WHERE event_name = 'panel_open' AND created_at_ts >= ?
                GROUP BY user_id
            ), first_action AS (
                SELECT p.user_id, MIN(p.created_at_ts) AS action_ts
                FROM panel_events p
                JOIN first_open o ON o.user_id = p.user_id
                WHERE p.event_name = 'panel_action' AND p.created_at_ts >= o.open_ts
                GROUP BY p.user_id
            )
            SELECT AVG(action_ts - open_ts) AS avg_delta
            FROM first_open o
            JOIN first_action a ON a.user_id = o.user_id
            """,
            (week_ago,),
        ).fetchone()["avg_delta"]

        d1 = conn.execute(
            """
            WITH first_open AS (
                SELECT user_id, MIN(created_at_ts) AS first_ts
                FROM panel_events
                WHERE event_name = 'panel_open'
                GROUP BY user_id
            ), returned AS (
                SELECT DISTINCT f.user_id
                FROM first_open f
                JOIN panel_events p ON p.user_id = f.user_id
                WHERE p.event_name = 'panel_open'
                  AND p.created_at_ts >= f.first_ts + ?
                  AND p.created_at_ts <  f.first_ts + ?
            )
            SELECT
                (SELECT COUNT(*) FROM returned) AS returned_users,
                (SELECT COUNT(*) FROM first_open) AS total_users
            """,
            (day_seconds, 2 * day_seconds),
        ).fetchone()

        d7 = conn.execute(
            """
            WITH first_open AS (
                SELECT user_id, MIN(created_at_ts) AS first_ts
                FROM panel_events
                WHERE event_name = 'panel_open'
                GROUP BY user_id
            ), returned AS (
                SELECT DISTINCT f.user_id
                FROM first_open f
                JOIN panel_events p ON p.user_id = f.user_id
                WHERE p.event_name = 'panel_open'
                  AND p.created_at_ts >= f.first_ts + ?
                  AND p.created_at_ts <  f.first_ts + ?
            )
            SELECT
                (SELECT COUNT(*) FROM returned) AS returned_users,
                (SELECT COUNT(*) FROM first_open) AS total_users
            """,
            (7 * day_seconds, 8 * day_seconds),
        ).fetchone()

    adoption = (unique_open_users / active_users * 100.0) if active_users else 0.0
    error_rate = (errors / (actions + errors) * 100.0) if (actions + errors) else 0.0
    action_per_open = (actions / opens) if opens else 0.0
    requirement_error_rate = (requirement_errors / (actions + requirement_errors) * 100.0) if (actions + requirement_errors) else 0.0
    usage_3x_day_pct = (users_3x_day / unique_open_users * 100.0) if unique_open_users else 0.0
    avg_time_first_action_s = float(avg_time_first_action or 0.0)
    d1_rate = (d1["returned_users"] / d1["total_users"] * 100.0) if d1["total_users"] else 0.0
    d7_rate = (d7["returned_users"] / d7["total_users"] * 100.0) if d7["total_users"] else 0.0

    lines = [f"• {r['event_action']}: {r['c']}" for r in by_button] if by_button else ["• sem dados"]
    await ctx.send(
        "📊 KPIs do Painel (7 dias)\n"
        f"Uso `!dominio` 3x/dia: {usage_3x_day_pct:.1f}% ({users_3x_day}/{unique_open_users})\n"
        f"Adoção painel: {adoption:.1f}% (meta ≥ 70%)\n"
        f"Erro de uso: {error_rate:.1f}% (meta ≤ 15%)\n"
        f"Erro por requisito ausente: {requirement_error_rate:.1f}%\n"
        f"Ações por sessão: {action_per_open:.2f} (meta ≥ 2.5)\n"
        f"Tempo médio open→1ª ação: {avg_time_first_action_s:.1f}s\n"
        f"Retenção D1/D7: {d1_rate:.1f}% / {d7_rate:.1f}%\n"
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
