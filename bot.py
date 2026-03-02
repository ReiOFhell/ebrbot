import logging
import os
import random
import sqlite3
import time
from pathlib import Path

import discord
from discord.ext import commands

from bets import setup_bets
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
logger = logging.getLogger("nexar.bot")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "nucleoc.db"

APP_NAME = "NEXAR"
APP_SLOGAN = "Aposte no seu progresso."
APP_PRESENCE = f"{APP_NAME} | !dominio"
APP_SHORT_DESCRIPTION = (
    "Bot global de progressão estratégica: domínio, operações reais e ranking de riqueza/poder/prestígio."
)

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
raffles_service = None
raffles_loop = None

DOCTRINES = {"cerco", "choque", "furtivo", "arcano"}
GENERAL_RANK_BONUS = {"C": 0.02, "B": 0.04, "A": 0.06, "S": 0.10}
STRATEGIST_RANK_BONUS = {"C": 0.015, "B": 0.03, "A": 0.05, "S": 0.08}
MAX_BUILDING_TIER = 10


def now_ts() -> int:
    return int(time.time())


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, col: str, ddl: str) -> None:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")




def build_legacy_safe_insert_values(conn: sqlite3.Connection, table: str, *, user_id: str, ts: int) -> dict[str, object]:
    values: dict[str, object] = {}
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    for col in cols:
        name = str(col[1])
        notnull = int(col[3] or 0) == 1
        default = col[4]

        if name == "user_id":
            values[name] = user_id
            continue
        if name == "created_at_ts":
            values[name] = ts
            continue

        if notnull and default is None:
            lname = name.lower()
            if lname.endswith("_ts"):
                values[name] = ts
            elif lname.endswith("_id"):
                values[name] = user_id
            elif lname.startswith("is_"):
                values[name] = 0
            else:
                values[name] = 0

    return values


def insert_row_legacy_safe(conn: sqlite3.Connection, table: str, *, user_id: str, ts: int) -> None:
    values = build_legacy_safe_insert_values(conn, table, user_id=user_id, ts=ts)
    cols = ", ".join(values.keys())
    placeholders = ", ".join("?" for _ in values)
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", tuple(values.values()))

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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS unit_name_parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                part_type TEXT NOT NULL,
                value TEXT NOT NULL,
                UNIQUE(role, part_type, value)
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
                route_mode TEXT NOT NULL DEFAULT 'full',
                success_chance REAL NOT NULL DEFAULT 0,
                troops_lost INTEGER NOT NULL DEFAULT 0,
                gold_delta INTEGER NOT NULL DEFAULT 0,
                prestige_gain INTEGER NOT NULL DEFAULT 0,
                power_before INTEGER NOT NULL DEFAULT 0,
                power_after INTEGER NOT NULL DEFAULT 0,
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
                updated_at_ts INTEGER NOT NULL DEFAULT 0,
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

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS command_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                command_name TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_text TEXT NOT NULL,
                created_at_ts INTEGER NOT NULL
            )
            """
        )

        # Compatibilidade incremental base (fundação do domínio)
        ensure_column(conn, "domains", "created_at_ts", "INTEGER NOT NULL DEFAULT 0")

        ensure_column(conn, "domain_buildings", "barn_level", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "domain_buildings", "barracks_level", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "domain_buildings", "forge_level", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "domain_buildings", "building_upgrade_ends_at_ts", "INTEGER")
        ensure_column(conn, "domain_buildings", "updated_at_ts", "INTEGER NOT NULL DEFAULT 0")

        ensure_column(conn, "resources", "gold", "INTEGER NOT NULL DEFAULT 100000")
        ensure_column(conn, "resources", "accumulated_maintenance", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "resources", "last_collect_ts", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "resources", "updated_at_ts", "INTEGER NOT NULL DEFAULT 0")

        ensure_column(conn, "army", "troops", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "army", "doctrine", "TEXT NOT NULL DEFAULT 'choque'")
        ensure_column(conn, "army", "power", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "army", "last_train_ts", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "army", "updated_at_ts", "INTEGER NOT NULL DEFAULT 0")

        # Compatibilidade incremental de colunas da Fase 3
        ensure_column(conn, "army", "general_id", "INTEGER")
        ensure_column(conn, "army", "strategist_id", "INTEGER")
        ensure_column(conn, "operations", "difficulty_power", "INTEGER NOT NULL DEFAULT 1000")
        ensure_column(conn, "operations", "preferred_doctrine", "TEXT")
        ensure_column(conn, "operations", "requires_general", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "operations", "prestige_reward", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "operations", "partial_without_strategist", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "operations", "min_barn_level", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "operations", "min_forge_level", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "operations", "min_feudo_tier", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "operations", "required_doctrine", "TEXT")
        ensure_column(conn, "operations", "min_troops", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "operations", "requires_arcane_general", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "operations", "required_legion_set_pieces", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "operation_runs", "route_mode", "TEXT NOT NULL DEFAULT 'full'")
        ensure_column(conn, "operation_runs", "success_chance", "REAL NOT NULL DEFAULT 0")
        ensure_column(conn, "operation_runs", "prestige_gain", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "operation_runs", "power_before", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "operation_runs", "power_after", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "season_scores", "updated_at_ts", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "season_state", "decree_name", "TEXT")
        ensure_column(conn, "season_state", "decree_description", "TEXT")
        ensure_column(conn, "season_state", "decree_started_at_ts", "INTEGER")
        ensure_column(conn, "season_state", "decree_ends_at_ts", "INTEGER")
        ensure_column(conn, "season_state", "economy_pct", "REAL NOT NULL DEFAULT 0")
        ensure_column(conn, "season_state", "operation_reward_pct", "REAL NOT NULL DEFAULT 0")
        ensure_column(conn, "season_state", "operation_risk_pct", "REAL NOT NULL DEFAULT 0")
        ensure_column(conn, "season_state", "prestige_pct", "REAL NOT NULL DEFAULT 0")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_operation_runs_user ON operation_runs(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_generals_user ON generals(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_strategists_user ON strategists(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_unit_name_parts_role ON unit_name_parts(role, part_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_panel_events_user ON panel_events(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_panel_events_name ON panel_events(event_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_command_errors_ts ON command_errors(created_at_ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discoveries_user ON discoveries_log(user_id)")

        now = now_ts()
        season_end = now + (30 * 24 * 3600)
        conn.execute(
            """
            INSERT OR IGNORE INTO season_state (
                id, season_number, started_at_ts, ends_at_ts, status,
                decree_name, decree_description, decree_started_at_ts, decree_ends_at_ts,
                economy_pct, operation_reward_pct, operation_risk_pct, prestige_pct
            )
            VALUES (1, 1, ?, ?, 'ativa', NULL, NULL, NULL, NULL, 0, 0, 0, 0)
            """,
            (now, season_end),
        )

        # seeds mínimos
        conn.execute(
            """
            INSERT OR IGNORE INTO operations (
                key, title, min_barracks_level, min_barn_level, min_forge_level, min_feudo_tier,
                min_troops, requires_general, requires_arcane_general, requires_strategist,
                partial_without_strategist, required_doctrine, required_legion_set_pieces,
                base_gold_reward, base_risk_percent, difficulty_power, preferred_doctrine, prestige_reward
            )
            VALUES
            ('tumba_sultao', 'Tumba do Sultão da Caravana', 3, 1, 1, 1, 300, 1, 0, 1, 1, NULL, 0, 300000, 0.12, 2200, 'furtivo', 10),
            ('ruinas_muralha', 'Ruínas da Muralha Viva', 4, 4, 1, 1, 500, 0, 0, 0, 0, 'cerco', 0, 450000, 0.09, 3500, 'cerco', 14),
            ('poco_nomes', 'Poço dos Nomes Perdidos', 3, 1, 4, 1, 600, 1, 1, 0, 0, 'arcano', 0, 380000, 0.11, 3300, 'arcano', 18),
            ('estrada_cinzas', 'Estrada das Sete Cinzas', 2, 1, 1, 1, 250, 0, 0, 0, 0, 'furtivo', 0, 180000, 0.10, 1600, 'choque', 6),
            ('fortim_sol_negro', 'Fortim do Sol Negro', 5, 1, 1, 6, 900, 1, 0, 1, 0, NULL, 3, 520000, 0.14, 4200, 'choque', 22)
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO items (key, name, rarity, lore)
            VALUES
            ('pergaminho_rasgado_i', 'Pergaminho Rasgado I — O Trono Silenciou', 'C', 'Juraram lealdade ao Trono. O Trono não respondeu.'),
            ('pergaminho_rasgado_ii', 'Pergaminho Rasgado II — Cinza no Estandarte', 'C', 'A bandeira queimou antes da batalha começar.'),
            ('elmo_basalto', 'Elmo do Basalto', 'R', 'Usado quando a muralha ainda respirava.'),
            ('lamina_juramento_quebrado', 'Lâmina do Juramento Quebrado', 'SSS', 'Quem a empunha vence; quem vence paga.'),
            ('insignia_setima_caravana', 'Insígnia da Sétima Caravana', 'R', 'Ninguém viu a sétima partir. Todos viram ela chegar.'),
            ('manopla_lorde_demonio_tanque', 'Manopla do Lorde-Demônio de Tanque', '99999', 'Não foi forjada. Foi lembrada.'),
            ('mascara_estrategista_cego', 'Máscara do Estrategista Cego', 'SSS+', 'Ele não via o mapa; via o fim.'),
            ('cronica_heroi_sem_tumulo', 'Crônica do Herói Sem Túmulo', 'SSS+', 'Salvou o mundo e perdeu o nome.'),
            ('selo_sal_nahr', 'Selo de Sal de Nahr', 'SS', 'Onde o sal cai, a memória acorda.'),
            ('fragmento_pacto_primordial', 'Fragmento do Pacto Primordial', '99999', 'O primeiro pacto não foi assinado por mãos humanas.')
            """
        )

        conn.executemany(
            "INSERT OR IGNORE INTO unit_name_parts (role, part_type, value) VALUES (?, ?, ?)",
            [
                ("general", "prefix", "Aço"),
                ("general", "prefix", "Ferro"),
                ("general", "prefix", "Ígneo"),
                ("general", "prefix", "Grifo"),
                ("general", "prefix", "Rubro"),
                ("general", "core", "Vanguarda"),
                ("general", "core", "Martelo"),
                ("general", "core", "Estandarte"),
                ("general", "core", "Bastião"),
                ("general", "core", "Centurião"),
                ("general", "title", "da Aurora"),
                ("general", "title", "do Cerco"),
                ("general", "title", "de Kharon"),
                ("general", "title", "do Juramento"),
                ("general", "title", "da Legião"),
                ("strategist", "prefix", "Silente"),
                ("strategist", "prefix", "Velado"),
                ("strategist", "prefix", "Lúcido"),
                ("strategist", "prefix", "Nebuloso"),
                ("strategist", "prefix", "Prístino"),
                ("strategist", "core", "Arquivista"),
                ("strategist", "core", "Cartógrafo"),
                ("strategist", "core", "Oráculo"),
                ("strategist", "core", "Cronista"),
                ("strategist", "core", "Teórico"),
                ("strategist", "title", "do Conselho"),
                ("strategist", "title", "das Cinzas"),
                ("strategist", "title", "da Vigília"),
                ("strategist", "title", "de Nahr"),
                ("strategist", "title", "do Eclipse"),
            ],
        )

        # Canonização dos 10 micro-lores (compatível com bases já existentes)
        conn.execute(
            """
            UPDATE items SET name = 'Pergaminho Rasgado I — O Trono Silenciou', rarity = 'C',
                lore = 'Juraram lealdade ao Trono. O Trono não respondeu.'
            WHERE key = 'pergaminho_rasgado_i'
            """
        )
        conn.execute(
            """
            UPDATE items SET name = 'Crônica do Herói Sem Túmulo', rarity = 'SSS+',
                lore = 'Salvou o mundo e perdeu o nome.'
            WHERE key = 'cronica_heroi_sem_tumulo'
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


def log_command_error(user_id: str | None, command_name: str, error: Exception) -> None:
    try:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO command_errors (user_id, command_name, error_type, error_text, created_at_ts)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, command_name, error.__class__.__name__, str(error)[:500], now_ts()),
            )
            conn.commit()
    except Exception:
        logger.exception("Falha ao persistir command_errors")


def get_global_modifiers() -> dict[str, float]:
    now = now_ts()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT economy_pct, operation_reward_pct, operation_risk_pct, prestige_pct,
                   decree_name, decree_description, decree_started_at_ts, decree_ends_at_ts
            FROM season_state
            WHERE id = 1
            """
        ).fetchone()

    if not row:
        return {
            "economy_pct": 0.0,
            "operation_reward_pct": 0.0,
            "operation_risk_pct": 0.0,
            "prestige_pct": 0.0,
        }

    ends = row["decree_ends_at_ts"]
    if ends is not None and now > int(ends):
        # Decreto expirou: ignora efeito até soberano renovar
        return {
            "economy_pct": 0.0,
            "operation_reward_pct": 0.0,
            "operation_risk_pct": 0.0,
            "prestige_pct": 0.0,
        }

    return {
        "economy_pct": float(row["economy_pct"] or 0.0),
        "operation_reward_pct": float(row["operation_reward_pct"] or 0.0),
        "operation_risk_pct": float(row["operation_risk_pct"] or 0.0),
        "prestige_pct": float(row["prestige_pct"] or 0.0),
    }


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
            "99999": "registro lendário permanente nas Crônicas",
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
        f"Registro nas Crônicas: {fragment}"
    )


def compose_unit_name(conn: sqlite3.Connection, role: str) -> str:
    prefix = conn.execute(
        "SELECT value FROM unit_name_parts WHERE role = ? AND part_type = 'prefix' ORDER BY RANDOM() LIMIT 1",
        (role,),
    ).fetchone()
    core = conn.execute(
        "SELECT value FROM unit_name_parts WHERE role = ? AND part_type = 'core' ORDER BY RANDOM() LIMIT 1",
        (role,),
    ).fetchone()
    title = conn.execute(
        "SELECT value FROM unit_name_parts WHERE role = ? AND part_type = 'title' ORDER BY RANDOM() LIMIT 1",
        (role,),
    ).fetchone()

    if not prefix or not core or not title:
        return "General do Feudo" if role == "general" else "Estrategista do Feudo"
    return f"{prefix['value']} {core['value']} {title['value']}"


def get_or_create_domain(user_id: str) -> sqlite3.Row:
    ts = now_ts()
    with get_conn() as conn:
        # Migração defensiva: contas antigas podem existir em `domains` sem linhas irmãs.
        domain = conn.execute("SELECT * FROM domains WHERE user_id = ?", (user_id,)).fetchone()
        if not domain:
            insert_row_legacy_safe(conn, "domains", user_id=user_id, ts=ts)

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

        # Slots canônicos: todo feudo nasce com 1 General e 1 Estrategista equipados.
        general_count = conn.execute("SELECT COUNT(*) c FROM generals WHERE user_id = ?", (user_id,)).fetchone()["c"]
        if general_count == 0:
            general_name = compose_unit_name(conn, "general")
            conn.execute(
                "INSERT INTO generals (user_id, name, rank, equipped, created_at_ts) VALUES (?, ?, 'C', 1, ?)",
                (user_id, general_name, ts),
            )
        strategist_count = conn.execute("SELECT COUNT(*) c FROM strategists WHERE user_id = ?", (user_id,)).fetchone()["c"]
        if strategist_count == 0:
            strategist_name = compose_unit_name(conn, "strategist")
            conn.execute(
                "INSERT INTO strategists (user_id, name, rank, equipped, created_at_ts) VALUES (?, ?, 'C', 1, ?)",
                (user_id, strategist_name, ts),
            )

        gid_row = conn.execute(
            "SELECT id FROM generals WHERE user_id = ? ORDER BY equipped DESC, id ASC LIMIT 1", (user_id,)
        ).fetchone()
        sid_row = conn.execute(
            "SELECT id FROM strategists WHERE user_id = ? ORDER BY equipped DESC, id ASC LIMIT 1", (user_id,)
        ).fetchone()
        if gid_row:
            conn.execute(
                "UPDATE generals SET equipped = CASE WHEN id = ? THEN 1 ELSE 0 END WHERE user_id = ?",
                (gid_row["id"], user_id),
            )
            conn.execute("UPDATE army SET general_id = ? WHERE user_id = ?", (gid_row["id"], user_id))
        if sid_row:
            conn.execute(
                "UPDATE strategists SET equipped = CASE WHEN id = ? THEN 1 ELSE 0 END WHERE user_id = ?",
                (sid_row["id"], user_id),
            )
            conn.execute("UPDATE army SET strategist_id = ? WHERE user_id = ?", (sid_row["id"], user_id))

        conn.commit()

        return conn.execute(
            """
            SELECT d.user_id, COALESCE(d.created_at_ts, 0) AS created_at_ts,
                   COALESCE(b.barn_level, 1) AS barn_level,
                   COALESCE(b.barracks_level, 1) AS barracks_level,
                   COALESCE(b.forge_level, 1) AS forge_level,
                   COALESCE(r.gold, 100000) AS gold,
                   COALESCE(r.accumulated_maintenance, 0) AS accumulated_maintenance,
                   COALESCE(r.last_collect_ts, 0) AS last_collect_ts,
                   COALESCE(a.troops, 0) AS troops,
                   COALESCE(a.doctrine, 'choque') AS doctrine,
                   COALESCE(a.power, 0) AS power,
                   COALESCE(a.last_train_ts, 0) AS last_train_ts,
                   a.general_id, a.strategist_id
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
        return False, "Requisito: concluir ao menos 1 operação (ex.: `!operacao estrada_cinzas`) para desbloquear estrategista."
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


def build_gameplay_service() -> GameplayService:
    """Compatibilidade defensiva entre versões do GameplayService.

    Alguns ambientes podem estar com versão anterior de services/gameplay.py
    (sem o parâmetro get_global_modifiers no __init__).
    """

    base_kwargs = dict(
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

    try:
        return GameplayService(**base_kwargs, get_global_modifiers=get_global_modifiers)
    except TypeError as exc:
        logger.warning(
            "GameplayService sem suporte a get_global_modifiers no __init__; aplicando fallback compatível: %s",
            exc,
        )
        service = GameplayService(**base_kwargs)
        # Injeção dinâmica para versões antigas do serviço.
        setattr(service, "get_global_modifiers", get_global_modifiers)
        return service


gameplay = build_gameplay_service()

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


def do_upgrade_general(user_id: str) -> str:
    return gameplay.do_upgrade_general(user_id)


def do_upgrade_strategist(user_id: str) -> str:
    return gameplay.do_upgrade_strategist(user_id)


def do_operacao(user_id: str, key: str) -> str:
    return gameplay.do_operacao(user_id, key)


def do_simular_operacao(user_id: str, key: str) -> str:
    return gameplay.do_simular_operacao(user_id, key)


def get_operation_status(user_id: str, key: str) -> str:
    return gameplay.get_operation_status(user_id, key)


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


def build_temporada_embed() -> discord.Embed:
    now = now_ts()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT season_number, started_at_ts, ends_at_ts, status,
                   decree_name, decree_description, decree_started_at_ts, decree_ends_at_ts,
                   economy_pct, operation_reward_pct, operation_risk_pct, prestige_pct
            FROM season_state
            WHERE id = 1
            """
        ).fetchone()

    embed = discord.Embed(title="👑 Temporada Imperial", color=discord.Color.dark_magenta())
    if not row:
        embed.description = "Temporada não inicializada."
        return embed

    remaining = max(0, int(row["ends_at_ts"] or 0) - now)
    remaining_h = remaining // 3600
    embed.add_field(
        name="Estado da temporada",
        value=(
            f"Temporada: **{row['season_number']}**\n"
            f"Status: **{row['status']}**\n"
            f"Tempo restante: **{remaining_h}h**"
        ),
        inline=False,
    )

    decree_name = row["decree_name"] or "Nenhum decreto ativo"
    decree_desc = row["decree_description"] or "—"
    decree_end = row["decree_ends_at_ts"]
    decree_state = "expirado"
    if decree_end and int(decree_end) >= now:
        decree_state = f"ativo por {(int(decree_end) - now) // 3600}h"

    embed.add_field(
        name="Decreto soberano",
        value=(
            f"Nome: **{decree_name}**\n"
            f"Descrição: {decree_desc}\n"
            f"Estado: **{decree_state}**"
        ),
        inline=False,
    )
    embed.add_field(
        name="Impactos globais (moderados)",
        value=(
            f"Economia: **{float(row['economy_pct'] or 0.0)*100:+.1f}%**\n"
            f"Recompensa operações: **{float(row['operation_reward_pct'] or 0.0)*100:+.1f}%**\n"
            f"Risco operações: **{float(row['operation_risk_pct'] or 0.0)*100:+.1f}%**\n"
            f"Prestígio: **{float(row['prestige_pct'] or 0.0)*100:+.1f}%**"
        ),
        inline=False,
    )
    embed.set_footer(text="Transparência imperial: todo bônus/ônus tem prazo fixo")
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

    g_name, g_rank = get_general_info(user_id, d["general_id"])
    s_name, s_rank = get_strategist_info(user_id, d["strategist_id"])

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
            f"🎖️ General: **{g_name}** (Rank {g_rank})\n"
            f"📐 Estrategista: **{s_name}** (Rank {s_rank})"
        ).replace(",", "."),
        inline=False,
    )
    embed.set_footer(text="Botões: Resgatar • Treinar • Construções • Militar • Operações • Rank")
    return embed




def get_general_info(user_id: str, general_id: int | None) -> tuple[str, str]:
    if not general_id:
        return "—", "C"
    with get_conn() as conn:
        row = conn.execute("SELECT name, rank FROM generals WHERE id = ? AND user_id = ?", (general_id, user_id)).fetchone()
        if not row:
            return "General do Feudo", "C"
        return str(row["name"] or "General do Feudo"), str(row["rank"] or "C")


def get_strategist_info(user_id: str, strategist_id: int | None) -> tuple[str, str]:
    if not strategist_id:
        return "—", "C"
    with get_conn() as conn:
        row = conn.execute(
            "SELECT name, rank FROM strategists WHERE id = ? AND user_id = ?",
            (strategist_id, user_id),
        ).fetchone()
        if not row:
            return "Estrategista do Feudo", "C"
        return str(row["name"] or "Estrategista do Feudo"), str(row["rank"] or "C")

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
    g_name, g_rank = get_general_info(user_id, d["general_id"])
    s_name, s_rank = get_strategist_info(user_id, d["strategist_id"])
    embed = discord.Embed(title="🛡️ Painel Militar", color=discord.Color.dark_teal())
    embed.description = (
        f"Doutrina: **{d['doctrine']}**\n"
        f"General: **{g_name}** (Rank {g_rank})\n"
        f"Estrategista: **{s_name}** (Rank {s_rank})\n"
        f"Poder atual: **{d['power']:,}**"
    ).replace(",", ".")
    if notice:
        embed.add_field(name="Ação", value=notice, inline=False)
    embed.add_field(
        name="Fluxo",
        value=(
            "✅ Composição militar pronta\n"
            "Δ Evoluir General + Estrategista amplia bônus de poder\n"
            "Próximo: evolua ambos e avance para Operações"
        ),
        inline=False,
    )
    embed.set_footer(text="Use os botões para gerir doutrina e evolução")
    return embed


def build_operacoes_embed(user_id: str, notice: str | None = None) -> discord.Embed:
    d = get_or_create_domain(user_id)
    with get_conn() as conn:
        ops = conn.execute("SELECT * FROM operations ORDER BY id").fetchall()
    lines: list[str] = []
    for op in ops:
        status = get_operation_status(user_id, op["key"])
        lines.append(f"• `{op['key']}` — {status}")

    embed = discord.Embed(title="⚔️ Painel de Operações", color=discord.Color.dark_red())
    embed.description = "\n".join(lines) if lines else "Nenhuma operação cadastrada."
    if notice:
        embed.add_field(name="Ação", value=notice, inline=False)
    embed.add_field(
        name="Fluxo",
        value=(
            "✅ Operações verificadas por requisito\n"
            "Δ Operações reais gravam histórico e impacto em operation_runs\n"
            "Próximo: escolha uma operação no seletor"
        ),
        inline=False,
    )
    mods = get_global_modifiers()
    embed.set_footer(
        text=(
            "Operações usam requisitos reais • "
            f"decreto: recompensa {mods.get('operation_reward_pct', 0.0)*100:+.1f}% / risco {mods.get('operation_risk_pct', 0.0)*100:+.1f}%"
        )
    )
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
        log_command_error=log_command_error,
    )


@bot.command(name="dominio")
async def dominio(ctx: commands.Context) -> None:
    try:
        log_panel_event(
            user_id=str(ctx.author.id),
            guild_id=str(ctx.guild.id) if ctx.guild else None,
            event_name="panel_open",
            event_action="dominio",
        )
        embed = build_dominio_embed(str(ctx.author.id))
        await ctx.send(content=f"<@{ctx.author.id}>", embed=embed, view=UIDominioView(author_id=ctx.author.id, deps=build_panel_deps()))
    except Exception as exc:
        log_command_error(str(ctx.author.id), "dominio", exc)
        logger.exception("Erro no comando !dominio", exc_info=exc)
        await ctx.send(f"<@{ctx.author.id}> Erro interno ao executar comando. Use `!diagnostico` (admin) para detalhes.")


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


@bot.command(name="evoluir_general", hidden=True)
async def evoluir_general(ctx: commands.Context) -> None:
    await ctx.send(do_upgrade_general(str(ctx.author.id)))


@bot.command(name="evoluir_estrategista", hidden=True)
async def evoluir_estrategista(ctx: commands.Context) -> None:
    await ctx.send(do_upgrade_strategist(str(ctx.author.id)))


@bot.command(name="operacao", hidden=True)
async def operacao(ctx: commands.Context, key: str | None = None) -> None:
    if not key:
        await ctx.send("Uso: `!operacao <tumba_sultao|ruinas_muralha|poco_nomes|estrada_cinzas|fortim_sol_negro>`")
        return
    await ctx.send(do_operacao(str(ctx.author.id), key))


@bot.command(name="simular_operacao", hidden=True)
async def simular_operacao(ctx: commands.Context, key: str | None = None) -> None:
    if not key:
        await ctx.send("Uso legado: `!simular_operacao <chave>` (preferencial: `!operacao <chave>`)")
        return
    await ctx.send(do_operacao(str(ctx.author.id), key))



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
            "Próximo: `!operacao` para buscar achados em campo."
        ).replace(",", ".")
    )


@bot.command(name="cronicas", hidden=True)
async def cronicas(ctx: commands.Context) -> None:
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
        await ctx.send("Nenhum registro encontrado nas Crônicas. A lore ainda não te encontrou.")
        return

    lines = []
    for r in rows:
        lines.append(
            f"• [{r['rarity']}] {r['fragment_text']}\n"
            f"  ↳ Impacto: {r['impact_text']}"
        )
    await ctx.send("📖 Crônicas de Descobertas\n" + "\n".join(lines))




@bot.command(name="rank")
async def rank(ctx: commands.Context) -> None:
    await ctx.send(embed=build_rank_embed())


@bot.command(name="temporada")
async def temporada(ctx: commands.Context) -> None:
    await ctx.send(embed=build_temporada_embed())


@bot.command(name="decreto_soberano", hidden=True)
@commands.has_permissions(administrator=True)
async def decreto_soberano(
    ctx: commands.Context,
    nome: str | None = None,
    duracao_horas: int | None = None,
    economia_pct: float = 0.0,
    recompensa_ops_pct: float = 0.0,
    risco_ops_pct: float = 0.0,
    prestigio_pct: float = 0.0,
) -> None:
    if not nome or duracao_horas is None:
        await ctx.send(
            "Uso: `!decreto_soberano <nome> <duracao_horas> [economia_pct] [recompensa_ops_pct] [risco_ops_pct] [prestigio_pct]`\n"
            "Exemplo: `!decreto_soberano Vigília_Rubra 24 0.05 0.08 0.04 0.03`"
        )
        return

    if duracao_horas < 1 or duracao_horas > 72:
        await ctx.send("❌ Duração inválida. Use entre 1h e 72h.")
        return

    # Limites moderados para não quebrar competitividade
    for v, label in [
        (economia_pct, "economia_pct"),
        (recompensa_ops_pct, "recompensa_ops_pct"),
        (risco_ops_pct, "risco_ops_pct"),
        (prestigio_pct, "prestigio_pct"),
    ]:
        if v < -0.25 or v > 0.25:
            await ctx.send(f"❌ `{label}` fora do limite moderado (-0.25 a +0.25).")
            return

    now = now_ts()
    end_ts = now + duracao_horas * 3600
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE season_state
            SET decree_name = ?, decree_description = ?,
                decree_started_at_ts = ?, decree_ends_at_ts = ?,
                economy_pct = ?, operation_reward_pct = ?, operation_risk_pct = ?, prestige_pct = ?
            WHERE id = 1
            """,
            (
                nome,
                f"Decreto de {ctx.author.display_name}",
                now,
                end_ts,
                economia_pct,
                recompensa_ops_pct,
                risco_ops_pct,
                prestigio_pct,
            ),
        )
        conn.commit()

    await ctx.send(
        f"<@{ctx.author.id}> ✅ Decreto soberano aplicado: **{nome}** por {duracao_horas}h\n"
        f"Δ Economia {economia_pct*100:+.1f}% | Recompensa Ops {recompensa_ops_pct*100:+.1f}% | "
        f"Risco Ops {risco_ops_pct*100:+.1f}% | Prestígio {prestigio_pct*100:+.1f}%\n"
        "Próximo: use `!temporada` para transparência pública."
    )


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




@bot.command(name="addouro", hidden=True)
@commands.has_permissions(administrator=True)
async def addouro(ctx: commands.Context, membro: discord.Member | None = None, quantidade: int | None = None) -> None:
    if membro is None or quantidade is None:
        await ctx.send("Uso: `!addouro @membro <quantidade>`")
        return
    if quantidade <= 0:
        await ctx.send("❌ A quantidade deve ser maior que zero.")
        return

    alvo_id = str(membro.id)
    d = get_or_create_domain(alvo_id)
    novo_saldo = int(d["gold"] or 0) + quantidade
    update_player_state(alvo_id, gold=novo_saldo)

    await ctx.send(
        (
            f"<@{ctx.author.id}> ✅ Ouro adicionado para <@{membro.id}>.\n"
            f"Δ Ouro: +{quantidade:,}\n"
            f"Saldo atual do alvo: {novo_saldo:,}"
        ).replace(",", ".")
    )


@addouro.error
async def addouro_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Apenas administradores podem usar `!addouro`.")
        return
    logger.exception("Erro em !addouro", exc_info=error)
    await ctx.send("Erro interno ao adicionar ouro.")


def delete_domain_data(user_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM season_scores WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM operation_runs WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM inventories WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM discoveries_log WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM panel_events WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM command_errors WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM strategists WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM generals WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM army WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM resources WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM domain_buildings WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM domains WHERE user_id = ?", (user_id,))
        conn.commit()


@bot.command(name="excluirdominio", hidden=True)
@commands.has_permissions(administrator=True)
async def excluirdominio(ctx: commands.Context, membro: discord.Member | None = None) -> None:
    if membro is None:
        await ctx.send("Uso: `!excluirdominio @membro`")
        return

    alvo_id = str(membro.id)
    with get_conn() as conn:
        existe = conn.execute("SELECT 1 FROM domains WHERE user_id = ?", (alvo_id,)).fetchone() is not None

    if not existe:
        await ctx.send(f"<@{ctx.author.id}> ❌ O membro <@{membro.id}> não possui domínio ativo.")
        return

    delete_domain_data(alvo_id)
    await ctx.send(f"<@{ctx.author.id}> ✅ Domínio de <@{membro.id}> foi removido com sucesso.")


@excluirdominio.error
async def excluirdominio_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Apenas administradores podem usar `!excluirdominio`.")
        return
    logger.exception("Erro em !excluirdominio", exc_info=error)
    await ctx.send("Erro interno ao excluir domínio.")


def build_admin_embed() -> discord.Embed:
    embed = discord.Embed(
        title=f"🛠️ Painel de Administração — {APP_NAME}",
        description="Hub administrativo com comandos completos, uso e finalidade.",
        color=discord.Color.dark_red(),
    )

    embed.add_field(
        name="Economia / Conta",
        value=(
            "`!addouro @membro <quantidade>`\n"
            "Adiciona ouro diretamente ao feudo de qualquer jogador."
        ),
        inline=False,
    )

    embed.add_field(
        name="Observabilidade",
        value=(
            "`!diagnostico`\n"
            "Mostra saúde do banco e últimos erros registrados.\n\n"
            "`!painel_kpis`\n"
            "Métricas operacionais do painel (7 dias).\n\n"
            "`!economia_teste`\n"
            "Snapshot de fórmula econômica para validação técnica."
        ),
        inline=False,
    )

    embed.add_field(
        name="Governança",
        value=(
            "`!decreto_soberano <nome> <duracao_horas> [economia_pct] [recompensa_ops_pct] [risco_ops_pct] [prestigio_pct]`\n"
            "Aplica modificadores globais temporários com limites moderados."
        ),
        inline=False,
    )

    embed.add_field(
        name="Comandos de Jogador (núcleo)",
        value=(
            "`!dominio` • `!rank` • `!guia` • `!temporada`\n"
            "Fluxo recomendado: abrir painel, executar ações e comparar ranking."
        ),
        inline=False,
    )

    embed.add_field(
        name="Comandos avançados/ocultos (debug e atalho)",
        value=(
            "`!coletar` • `!treinar` • `!melhorar <estrutura>` • `!doutrina <estilo>`\n"
            "`!evoluir_general` • `!evoluir_estrategista`\n"
            "`!operacao <chave>` (alias: `!simular_operacao`) • `!forjar` • `!cronicas`"
        ),
        inline=False,
    )

    embed.set_footer(text="Comando admin recomendado para consulta completa: !admin")
    return embed


@bot.command(name="admin", hidden=True)
@commands.has_permissions(administrator=True)
async def admin_panel(ctx: commands.Context) -> None:
    await ctx.send(embed=build_admin_embed())


@admin_panel.error
async def admin_panel_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Apenas administradores podem usar `!admin`.")
        return
    logger.exception("Erro em !admin", exc_info=error)
    await ctx.send("Erro interno no painel administrativo.")

@economia_teste.error
async def economia_teste_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Apenas administradores podem usar `!economia_teste`.")
        return
    logger.exception("Erro em !economia_teste", exc_info=error)
    await ctx.send("Erro interno no teste de economia.")


GUIDE_PAGES: list[tuple[str, str]] = [
    (
        f"📘 Guia do {APP_NAME} — Página 1/3",
        "**Comece aqui (10 segundos)**\n"
        "1) Use `!dominio` para abrir o painel central.\n"
        "2) Clique em **Resgatar** para gerar ouro e ritmo de progresso.\n"
        "3) Clique em **Construções** para melhorar Celeiros/Casernas/Forja.\n\n"
        "**Próximo passo claro:** fortalecer economia e voltar ao painel.",
    ),
    (
        f"📘 Guia do {APP_NAME} — Página 2/3",
        "**Progressão visível (3 eixos)**\n"
        "• **Riqueza**: ouro para upgrades e manutenção.\n"
        "• **Poder**: tropas + doutrina + General e Estrategista nativos do domínio.\n"
        "• **Prestígio**: pontuação sazonal por operações.\n\n"
        "**Próximo passo claro:** ajuste doutrina no painel Militar e simule Operações.",
    ),
    (
        f"📘 Guia do {APP_NAME} — Página 3/3",
        "**Comandos públicos**\n"
        "`!dominio` → jogar o núcleo inteiro por clique\n"
        "`!rank` → comparar riqueza/poder/prestígio\n"
        "`!guia` → onboarding por páginas\n\n"
        f"**{APP_NAME}:** {APP_SLOGAN}\n"
        "**Admin (oculto):** `!admin`, `!addouro`, `!excluirdominio`, `!diagnostico`, `!painel_kpis`, `!economia_teste`, `!decreto_soberano`\n"
        "**Dica:** se uma view expirar, use `🔄 Reabrir Painel`.",
    ),
]


def build_guia_embed(page_index: int) -> discord.Embed:
    idx = max(0, min(page_index, len(GUIDE_PAGES) - 1))
    title, text = GUIDE_PAGES[idx]
    embed = discord.Embed(title=title, description=text, color=discord.Color.dark_gold())
    embed.set_footer(text="Navegação: ◀️ Anterior • ▶️ Próxima")
    return embed


class GuiaView(discord.ui.View):
    def __init__(self, author_id: int, page_index: int = 0):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.page_index = max(0, min(page_index, len(GUIDE_PAGES) - 1))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Apenas quem abriu o guia pode navegar nesta mensagem.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.page_index = (self.page_index - 1) % len(GUIDE_PAGES)
        await interaction.response.edit_message(embed=build_guia_embed(self.page_index), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.page_index = (self.page_index + 1) % len(GUIDE_PAGES)
        await interaction.response.edit_message(embed=build_guia_embed(self.page_index), view=self)


@bot.command(name="guia")
async def guia(ctx: commands.Context) -> None:
    await ctx.send(embed=build_guia_embed(0), view=GuiaView(author_id=ctx.author.id, page_index=0))


@bot.command(name="diagnostico", hidden=True)
@commands.has_permissions(administrator=True)
async def diagnostico(ctx: commands.Context) -> None:
    with get_conn() as conn:
        counts = {}
        for table in [
            "domains", "domain_buildings", "resources", "army", "generals", "strategists", "operations",
            "operation_runs", "items", "inventories", "season_state", "season_scores", "panel_events", "command_errors",
        ]:
            counts[table] = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]

        recent_errors = conn.execute(
            """
            SELECT command_name, error_type, error_text, created_at_ts, user_id
            FROM command_errors
            ORDER BY id DESC
            LIMIT 5
            """
        ).fetchall()

    lines = [f"{k}: {v}" for k, v in counts.items()]
    err_lines = [
        f"• {r['command_name']} | {r['error_type']} | uid={r['user_id'] or '-'} | {r['error_text'][:120]}"
        for r in recent_errors
    ] or ["• sem erros registrados"]

    await ctx.send(
        f"Diagnóstico Fase 1\nDB: `{DB_PATH}`\n" + "\n".join(lines) +
        "\n\nÚltimos erros de comando:\n" + "\n".join(err_lines)
    )


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


@decreto_soberano.error
async def decreto_soberano_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Apenas administradores podem usar `!decreto_soberano`.")
        return
    logger.exception("Erro em !decreto_soberano", exc_info=error)
    await ctx.send("Erro interno no decreto soberano.")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    logger.exception("Erro de comando", exc_info=error)
    cmd_name = ctx.command.qualified_name if ctx.command else "desconhecido"
    log_command_error(str(ctx.author.id), cmd_name, error)
    await ctx.send(f"<@{ctx.author.id}> Erro interno ao executar comando.")


@bot.event
async def on_ready() -> None:
    activity = discord.Game(name=APP_PRESENCE)
    await bot.change_presence(activity=activity)
    logger.info("Conectado como %s | %s", bot.user, APP_SHORT_DESCRIPTION)
    if raffles_loop is not None:
        raffles_loop.start()


def main() -> None:
    global raffles_service, raffles_loop
    init_db()
    raffles_service, raffles_loop = setup_bets(
        bot=bot,
        get_conn=get_conn,
        get_or_create_domain=get_or_create_domain,
        update_player_state=update_player_state,
        now_ts=now_ts,
        logger=logger,
    )
    try:
        token = resolve_token()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    bot.run(token)


if __name__ == "__main__":
    main()
