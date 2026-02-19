# ============================================================
# 1) IMPORTS
# ============================================================
import hashlib
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import discord
from discord.ext import commands


# ============================================================
# 2) CONFIG E INTENTS
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("ebr.grimorio")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ============================================================
# 3) CONSTANTES
# ============================================================
INKOSI_ID = "1187734043236778027"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "players.db"

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_TOKEN_FALLBACK = "COLE_SEU_TOKEN_AQUI"

EMBED_COLOR = discord.Color.from_rgb(45, 18, 54)

VOICE = {
    "abertura": "✦ O Grimório abre suas páginas sob teu nome.",
    "sucesso": "✦ O selo foi aceito pelos arquivos imperiais.",
    "recusa": "✦ O rito foi recusado; o destino exige outro passo.",
    "erro": "O Grimório está em silêncio.",
}


# ============================================================
# 4) BANCO (SQLITE HELPERS + MIGRAÇÕES)
# ============================================================
def resolve_token() -> str:
    token_env = (DISCORD_TOKEN or "").strip().strip('"').strip("'")
    token_fallback = (DISCORD_TOKEN_FALLBACK or "").strip().strip('"').strip("'")
    token = token_env if token_env else token_fallback

    if not token or token == "COLE_SEU_TOKEN_AQUI":
        raise RuntimeError("Defina DISCORD_TOKEN no ambiente ou preencha DISCORD_TOKEN_FALLBACK.")

    if token.count(".") < 2:
        raise RuntimeError("DISCORD_TOKEN parece inválido (formato inesperado).")

    return token


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def canon_line(kind: str, extra: str | None = None) -> str:
    base = VOICE.get(kind, VOICE["erro"])
    return f"{base}\n{extra}" if extra else base


def short_hash(command_name: str, timestamp_utc: str, user_id: str) -> str:
    raw = f"{command_name}|{timestamp_utc}|{user_id}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:8].upper()


def log_failure(command_name: str, user_id: str, error_text: str) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    seal = short_hash(command_name, ts, user_id)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO failure_logs (command_name, timestamp_utc, user_id, hash_curto, error_text)
            VALUES (?, ?, ?, ?, ?)
            """,
            (command_name, ts, user_id, seal, error_text),
        )
        conn.commit()
    return seal


async def send_grimoire_error(
    ctx: commands.Context,
    tag: str,
    *,
    command_name: str | None = None,
    user_id: str | None = None,
    error: Exception | None = None,
) -> None:
    command_ref = command_name or tag
    uid = user_id or str(ctx.author.id if ctx.author else "0")
    err_text = str(error) if error else "erro não informado"
    seal = "SEM_SELO"
    try:
        seal = log_failure(command_ref, uid, err_text)
    except Exception:
        logger.exception("Falha ao registrar failure_logs")

    await ctx.send(f"{VOICE['erro']} Selo de falha: {tag}-{seal}.")


def ensure_columns(conn: sqlite3.Connection) -> None:
    # Etapa 0: garante apenas colunas canônicas da Fase 1 (sem gameplay extra).
    required = {
        "user_id": "TEXT",
        "classe": "TEXT",
        "is_excecao": "INTEGER DEFAULT 0",
        "nivel": "TEXT",
        "criado_em": "TEXT",
        "forca": "TEXT",
        "resistencia": "TEXT",
        "agilidade": "TEXT",
        "inteligencia": "TEXT",
        "mana": "TEXT",
        "crescimento": "TEXT",
        "titulo": "TEXT",
        "lore_texto": "TEXT",
        "pressagio": "TEXT",
        # Compatibilidade com schemas legados de versões anteriores (Fase 2 revertida)
        "ouro": "INTEGER NOT NULL DEFAULT 0",
        "prestigio": "INTEGER NOT NULL DEFAULT 0",
        "last_aventura_at": "TEXT",
        "streak_aventura": "INTEGER NOT NULL DEFAULT 0",
        "total_aventuras": "INTEGER NOT NULL DEFAULT 0",
        "juramento": "TEXT",
        "juramento_escolhido_em": "TEXT",
    }
    cols = {row[1] for row in conn.execute("PRAGMA table_info(players)").fetchall()}
    for name, ddl in required.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE players ADD COLUMN {name} {ddl}")


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS players (
                user_id TEXT PRIMARY KEY,
                classe TEXT NOT NULL,
                is_excecao INTEGER DEFAULT 0,
                nivel TEXT,
                criado_em TEXT,
                forca TEXT,
                resistencia TEXT,
                agilidade TEXT,
                inteligencia TEXT,
                mana TEXT,
                crescimento TEXT,
                titulo TEXT,
                lore_texto TEXT,
                pressagio TEXT
            )
            """
        )
        ensure_columns(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS annals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                entrada TEXT NOT NULL,
                criado_em TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS player_marcos (
                user_id TEXT NOT NULL,
                marco_key TEXT NOT NULL,
                descricao TEXT NOT NULL,
                criado_em TEXT NOT NULL,
                PRIMARY KEY (user_id, marco_key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS world_state (
                singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                epoca_atual TEXT NOT NULL,
                decreto_ativo TEXT NOT NULL,
                tensao_fronteiras TEXT NOT NULL,
                faccao_ascensao TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS council_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                opened_by TEXT,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                winning_option TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS council_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                option_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(session_id, user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS global_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT,
                actor_user_id TEXT,
                created_em TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS failure_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_name TEXT NOT NULL,
                timestamp_utc TEXT NOT NULL,
                user_id TEXT,
                hash_curto TEXT NOT NULL,
                error_text TEXT
            )
            """
        )
        conn.commit()


def get_players_table_info() -> list[sqlite3.Row]:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("PRAGMA table_info(players)").fetchall()


def fallback_value_for_required_column(column: sqlite3.Row) -> Any:
    declared_type = str(column["type"] or "").upper()
    if any(token in declared_type for token in ("INT", "REAL", "NUM")):
        return 0
    return ""


def get_player(user_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def create_player(
    user_id: str,
    classe_id: str,
    *,
    is_excecao: int,
    nivel: str,
    forca: str,
    resistencia: str,
    agilidade: str,
    inteligencia: str,
    mana: str,
    crescimento: str,
    titulo: str,
    lore_texto: str,
    pressagio: str,
) -> None:
    base_values: dict[str, Any] = {
        "user_id": user_id,
        "classe": classe_id,
        "is_excecao": is_excecao,
        "nivel": nivel,
        "criado_em": datetime.now(timezone.utc).isoformat(),
        "forca": forca,
        "resistencia": resistencia,
        "agilidade": agilidade,
        "inteligencia": inteligencia,
        "mana": mana,
        "crescimento": crescimento,
        "titulo": titulo,
        "lore_texto": lore_texto,
        "pressagio": pressagio,
        # compat legada
        "ouro": 0,
        "prestigio": 0,
        "last_aventura_at": "",
        "streak_aventura": 0,
        "total_aventuras": 0,
        "juramento": "",
        "juramento_escolhido_em": "",
    }

    table_info = get_players_table_info()
    columns: list[str] = []
    values: list[Any] = []
    for row in table_info:
        col = row["name"]
        notnull = int(row["notnull"]) == 1
        default = row["dflt_value"]

        if col in base_values:
            columns.append(col)
            values.append(base_values[col])
        elif notnull and default is None:
            columns.append(col)
            values.append(fallback_value_for_required_column(row))

    if not columns:
        raise RuntimeError("Schema inválido: tabela players sem colunas utilizáveis para INSERT.")

    placeholders = ", ".join(["?"] * len(columns))
    sql = f"INSERT OR REPLACE INTO players ({', '.join(columns)}) VALUES ({placeholders})"

    with get_conn() as conn:
        conn.execute(sql, values)
        conn.commit()


def add_annal_entry(user_id: str, entrada: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO annals (user_id, entrada, criado_em) VALUES (?, ?, ?)",
            (user_id, entrada, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def add_player_marco(user_id: str, marco_key: str, descricao: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO player_marcos (user_id, marco_key, descricao, criado_em)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, marco_key, descricao, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def get_player_marcos(user_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT marco_key, descricao, criado_em FROM player_marcos WHERE user_id = ? ORDER BY criado_em ASC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_player_annals_count(user_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) FROM annals WHERE user_id = ?", (user_id,)).fetchone()
        return int(row[0]) if row else 0


def delete_player(user_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM players WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM annals WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM player_marcos WHERE user_id = ?", (user_id,))
        conn.commit()


def player_exists(user_id: str) -> bool:
    return get_player(user_id) is not None


def get_recent_failures(limit: int = 5) -> list[dict[str, Any]]:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT command_name, timestamp_utc, user_id, hash_curto, error_text FROM failure_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def ensure_world_state_row(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR IGNORE INTO world_state (
            singleton_id,
            epoca_atual,
            decreto_ativo,
            tensao_fronteiras,
            faccao_ascensao,
            atualizado_em
        ) VALUES (1, ?, ?, ?, ?, ?)
        """,
        (
            WORLD_STATE_DEFAULTS["epoca_atual"],
            WORLD_STATE_DEFAULTS["decreto_ativo"],
            WORLD_STATE_DEFAULTS["tensao_fronteiras"],
            WORLD_STATE_DEFAULTS["faccao_ascensao"],
            now,
        ),
    )


def get_world_state() -> dict[str, Any]:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        ensure_world_state_row(conn)
        row = conn.execute("SELECT * FROM world_state WHERE singleton_id = 1").fetchone()
        conn.commit()
        if row:
            return dict(row)
    return {"singleton_id": 1, **WORLD_STATE_DEFAULTS, "atualizado_em": datetime.now(timezone.utc).isoformat()}


def build_oraculo_message(world_state: dict[str, Any]) -> str:
    tensao = str(world_state.get("tensao_fronteiras") or "MÉDIA").strip().upper()
    if tensao not in TENSION_ORACLE_LINES:
        tensao = "MÉDIA"

    return (
        f"**Época:** {world_state.get('epoca_atual', WORLD_STATE_DEFAULTS['epoca_atual'])}\n"
        f"**Decreto ativo:** {world_state.get('decreto_ativo', WORLD_STATE_DEFAULTS['decreto_ativo'])}\n"
        f"**Fronteiras:** {tensao}\n"
        f"**Facção em ascensão:** {world_state.get('faccao_ascensao', WORLD_STATE_DEFAULTS['faccao_ascensao'])}\n\n"
        f"{TENSION_ORACLE_LINES[tensao]}"
    )


def add_global_event(event_type: str, title: str, detail: str, actor_user_id: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO global_events (event_type, title, detail, actor_user_id, created_em)
            VALUES (?, ?, ?, ?, ?)
            """,
            (event_type, title, detail, actor_user_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def get_global_events(limit: int = 20) -> list[dict[str, Any]]:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT event_type, title, detail, actor_user_id, created_em FROM global_events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def week_key_utc() -> str:
    now = datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def close_stale_council_sessions(current_week_key: str) -> None:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        stale = conn.execute(
            "SELECT * FROM council_sessions WHERE status = 'open' AND week_key <> ?",
            (current_week_key,),
        ).fetchall()

    for row in stale:
        finalize_council_session(dict(row), actor_user_id="SYSTEM")


def ensure_current_council_session(opened_by: str | None = None) -> dict[str, Any]:
    wk = week_key_utc()
    close_stale_council_sessions(wk)
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM council_sessions WHERE week_key = ?", (wk,)).fetchone()
        if row:
            return dict(row)

        conn.execute(
            "INSERT INTO council_sessions (week_key, status, opened_by, opened_at) VALUES (?, 'open', ?, ?)",
            (wk, opened_by, now),
        )
        conn.commit()
        created = conn.execute("SELECT * FROM council_sessions WHERE week_key = ?", (wk,)).fetchone()
        return dict(created) if created else {}


def get_council_vote_counts(session_id: int) -> dict[str, int]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT option_key, COUNT(*) FROM council_votes WHERE session_id = ? GROUP BY option_key",
            (session_id,),
        ).fetchall()
    counts = {k: 0 for k in COUNCIL_OPTIONS}
    for option_key, qty in rows:
        counts[str(option_key)] = int(qty)
    return counts


def register_council_vote(session_id: int, user_id: str, option_key: str) -> tuple[bool, str]:
    if option_key not in COUNCIL_OPTIONS:
        return False, "Opção de conselho inválida."

    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT 1 FROM council_votes WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if existing:
            return False, "Teu voto nesta semana já foi registrado; o Conselho não aceita duplicatas."

        conn.execute(
            "INSERT INTO council_votes (session_id, user_id, option_key, created_at) VALUES (?, ?, ?, ?)",
            (session_id, user_id, option_key, now),
        )
        conn.commit()
    return True, COUNCIL_OPTIONS[option_key]["label"]


def finalize_council_session(session: dict[str, Any], actor_user_id: str) -> tuple[bool, str]:
    if not session or session.get("status") != "open":
        return False, "Não há votação semanal aberta para encerrar."

    session_id = int(session["id"])
    counts = get_council_vote_counts(session_id)
    winner_key = max(counts, key=lambda key: counts[key])
    winner = COUNCIL_OPTIONS[winner_key]

    with get_conn() as conn:
        conn.execute(
            "UPDATE council_sessions SET status = 'closed', closed_at = ?, winning_option = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), winner_key, session_id),
        )
        ensure_world_state_row(conn)
        conn.execute(
            "UPDATE world_state SET tensao_fronteiras = ?, faccao_ascensao = ?, atualizado_em = ? WHERE singleton_id = 1",
            (winner["tensao"], winner["faccao"], datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

    detail = f"Resultado semanal: {winner['label']} (tensão {winner['tensao']})."
    add_global_event("conselho", "Resultado do Conselho", detail, actor_user_id=actor_user_id)
    return True, detail


def get_db_diagnostics() -> dict[str, Any]:
    db_exists = DB_PATH.exists()
    data_dir_exists = DATA_DIR.exists()
    writable = os.access(DATA_DIR, os.W_OK) if data_dir_exists else False

    details: dict[str, Any] = {
        "db_path": str(DB_PATH),
        "db_exists": db_exists,
        "data_dir_exists": data_dir_exists,
        "data_dir_writable": writable,
        "players_count": 0,
        "failure_count": 0,
        "world_tensao": "-",
        "world_atualizado_em": "-",
    }

    if not db_exists:
        return details

    with get_conn() as conn:
        details["players_count"] = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        details["failure_count"] = conn.execute("SELECT COUNT(*) FROM failure_logs").fetchone()[0]
        ensure_world_state_row(conn)
        world = conn.execute("SELECT tensao_fronteiras, atualizado_em FROM world_state WHERE singleton_id = 1").fetchone()
        conn.commit()

    if world:
        details["world_tensao"] = world[0]
        details["world_atualizado_em"] = world[1]

    return details


def create_inkosi_record_if_needed(user_id: str) -> dict[str, Any]:
    existing = get_player(user_id)
    if existing:
        return existing

    create_player(
        user_id=user_id,
        classe_id="inkosi",
        is_excecao=1,
        nivel="ABSOLUTO",
        forca="MAX",
        resistencia="MAX",
        agilidade="MAX",
        inteligencia="MAX",
        mana="MAX",
        crescimento="Não mensurável pelas leis do Sistema.",
        titulo="Aquele que Não se Submete",
        lore_texto="Entidade anterior ao registro, posterior ao julgamento.",
        pressagio="Quando seu nome é invocado, até os arquivos calam.",
    )
    return get_player(user_id) or {}


# ============================================================
# 5) DADOS CANÔNICOS
# ============================================================
CLASSES: dict[str, dict[str, Any]] = {
    "guerreiro": {
        "nome": "Guerreiro",
        "icone": "⚔️",
        "frase": "Onde a noite avança, ele ergue o aço e dita fronteiras.",
        "descricao": "Guardião de muralhas e juramentos.",
        "atributos": {"FOR": "12", "RES": "10", "AGI": "6", "INT": "4", "MAN": "3"},
        "crescimento": "Cresce pelo rigor.",
        "titulo": "Sentinela do Trono Velado",
        "lore_texto": "Escolheu o aço para conter a ruína.",
        "pressagio": "Seu passo anuncia ordem; seu silêncio, juízo.",
    },
    "mago": {
        "nome": "Mago",
        "icone": "🜂",
        "frase": "Lê os ecos do invisível e escreve decretos no vazio.",
        "descricao": "Erudito arcano do interdito.",
        "atributos": {"FOR": "3", "RES": "5", "AGI": "6", "INT": "12", "MAN": "12"},
        "crescimento": "Cresce pela contemplação proibida.",
        "titulo": "Arcanista da Coroa Obscura",
        "lore_texto": "Traduz o indizível para manter o Reino desperto.",
        "pressagio": "Onde ele fixa os olhos, o véu cede.",
    },
    "cacador": {
        "nome": "Caçador",
        "icone": "🏹",
        "frase": "Não persegue presas; persegue destinos.",
        "descricao": "Predador de sombras.",
        "atributos": {"FOR": "8", "RES": "7", "AGI": "11", "INT": "6", "MAN": "4"},
        "crescimento": "Cresce na precisão ritual.",
        "titulo": "Perseguidor dos Ecos",
        "lore_texto": "Jurou caçar ameaças aos pactos antigos.",
        "pressagio": "Quando a trilha some, ele já chegou.",
    },
    "soldado": {
        "nome": "Soldado",
        "icone": "🛡️",
        "frase": "Marcha onde o medo manda recuar.",
        "descricao": "Braço disciplinado do Império.",
        "atributos": {"FOR": "9", "RES": "9", "AGI": "7", "INT": "6", "MAN": "3"},
        "crescimento": "Cresce pela disciplina de ferro.",
        "titulo": "Lâmina da Legião Eterna",
        "lore_texto": "Nasceu para obedecer ao estandarte.",
        "pressagio": "Onde seu estandarte fincar, a desordem se ajoelha.",
    },
    "explorador": {
        "nome": "Explorador",
        "icone": "🧭",
        "frase": "Abre caminhos onde o mapa termina.",
        "descricao": "Cartógrafo do desconhecido.",
        "atributos": {"FOR": "6", "RES": "7", "AGI": "10", "INT": "8", "MAN": "5"},
        "crescimento": "Cresce ao decifrar fronteiras perdidas.",
        "titulo": "Arauto das Fronteiras Mortas",
        "lore_texto": "Atravessa neblinas e nomeia o impossível.",
        "pressagio": "Quando ele retorna, o mundo já não é o mesmo.",
    },
}

JURAMENTOS: dict[str, str] = {
    "trono": "Ao Trono Velado — Minha lâmina serve a ordem do Império.",
    "verdade": "À Verdade Oculta — Meu espírito busca o que foi interditado.",
    "fronteira": "À Fronteira Eterna — Meu passo protege o limite do mundo.",
    "cinzas": "Às Cinzas da Queda — Minha memória vigia os erros antigos.",
}

TRILHAS: list[tuple[str, int]] = [
    ("Iniciado", 0),
    ("Reconhecido", 3),
    ("Notável", 7),
    ("Venerável", 12),
    ("Lenda", 18),
]

WORLD_STATE_DEFAULTS: dict[str, str] = {
    "epoca_atual": "Época das Brasas Veladas",
    "decreto_ativo": "Decreto do Véu Silencioso",
    "tensao_fronteiras": "MÉDIA",
    "faccao_ascensao": "Casa das Lanternas (observada)",
}

TENSION_ORACLE_LINES: dict[str, str] = {
    "BAIXA": "As muralhas respiram em paz vigiada; o Império acumula fôlego para o próximo ciclo.",
    "MÉDIA": "As fronteiras vibram em alerta disciplinado; cada passo errado pode acender um novo decreto.",
    "ALTA": "As fronteiras ardem sob aço e presságios; o Império exige vigilância absoluta dos despertos.",
}

COUNCIL_OPTIONS: dict[str, dict[str, str]] = {
    "vigia": {"label": "Vigia das Fronteiras", "tensao": "ALTA", "faccao": "Legião da Vigília"},
    "diplomacia": {"label": "Pacto de Diplomacia", "tensao": "BAIXA", "faccao": "Casa das Embaixadas"},
    "equilibrio": {"label": "Trégua Calculada", "tensao": "MÉDIA", "faccao": "Ordem do Equilíbrio"},
}

INTRIGA_TYPES = {"rumor", "denuncia", "alianca", "ameaca"}


def build_iniciar_embed() -> discord.Embed:
    embed = discord.Embed(
        title="RITUAL DO DESPERTAR",
        description=(
            "**Ato I — O Mundo**\n"
            "No EBR, impérios se erguem sobre juramentos antigos e sombras disciplinadas.\n"
            "Cada nome inscrito altera o peso da noite.\n\n"
            "**Ato II — A Testemunha**\n"
            "O Grimório observa teu passo, mede teu silêncio e recolhe teu primeiro voto.\n"
            "Nada do que fores será esquecido.\n\n"
            "**Ato III — A Escolha**\n"
            "Diante dos selos, escolhe teu Caminho.\n"
            "A escolha é única. O destino não admite rascunhos."
        ),
        color=EMBED_COLOR,
    )
    for data in CLASSES.values():
        embed.add_field(name=f"{data['icone']} {data['nome']}", value=data["frase"], inline=False)

    embed.set_footer(text="FASE 1 — Núcleo do Jogador • O destino começa aqui")
    return embed

def normalize_class_input(raw: str) -> str:
    aliases = {
        "guerreiro": "guerreiro",
        "mago": "mago",
        "cacador": "cacador",
        "caçador": "cacador",
        "soldado": "soldado",
        "explorador": "explorador",
    }
    return aliases.get(raw.strip().lower(), "")


def register_class_for_user(user_id: str, classe_id: str) -> tuple[bool, str]:
    if user_id == INKOSI_ID:
        return False, "A assinatura ABSOLUTA não pode ser definida por escolha comum."

    try:
        if player_exists(user_id):
            return False, "Teu destino já foi inscrito. O Grimório não aceita duplicatas."

        data = CLASSES[classe_id]
        attrs = data["atributos"]
        create_player(
            user_id=user_id,
            classe_id=classe_id,
            is_excecao=0,
            nivel="1",
            forca=attrs["FOR"],
            resistencia=attrs["RES"],
            agilidade=attrs["AGI"],
            inteligencia=attrs["INT"],
            mana=attrs["MAN"],
            crescimento=data["crescimento"],
            titulo=data["titulo"],
            lore_texto=data["lore_texto"],
            pressagio=data["pressagio"],
        )
        try:
            add_annal_entry(user_id, f"Ritual do Despertar concluído. Caminho selado: {data['nome']}.")
            add_player_marco(user_id, "despertar", "Despertar concluído")
        except sqlite3.Error:
            logger.exception("Falha ao registrar entrada nos Anais; cadastro principal mantido")
        return True, data["nome"]
    except sqlite3.Error:
        logger.exception("Falha SQLite ao registrar classe")
        return False, "Falha temporária de persistência do Grimório. Tente novamente em alguns segundos."



def parse_iso_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def get_trilha_status(player: dict[str, Any]) -> dict[str, Any]:
    criado_em = parse_iso_datetime(player.get("criado_em"))
    agora = datetime.now(timezone.utc)
    dias_desde_despertar = max((agora - criado_em).days, 0) if criado_em else 0
    annals_count = get_player_annals_count(str(player.get("user_id", "")))
    prestigio = int(player.get("prestigio") or 0)

    score = annals_count + (dias_desde_despertar // 7) + (prestigio // 10)

    atual_nome = TRILHAS[0][0]
    proximo_nome: str | None = None
    progresso_atual = score
    progresso_necessario = TRILHAS[1][1] if len(TRILHAS) > 1 else TRILHAS[0][1]

    for i, (nome, requisito) in enumerate(TRILHAS):
        if score >= requisito:
            atual_nome = nome
            progresso_atual = score - requisito
            if i + 1 < len(TRILHAS):
                proximo_nome = TRILHAS[i + 1][0]
                progresso_necessario = TRILHAS[i + 1][1] - requisito
            else:
                proximo_nome = None
                progresso_necessario = 0

    return {
        "atual": atual_nome,
        "proximo": proximo_nome,
        "score": score,
        "annals": annals_count,
        "dias": dias_desde_despertar,
        "prestigio": prestigio,
        "progresso_atual": progresso_atual,
        "progresso_necessario": progresso_necessario,
    }


def set_player_juramento(user_id: str, juramento_key: str) -> None:
    agora = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE players SET juramento = ?, juramento_escolhido_em = ? WHERE user_id = ?",
            (juramento_key, agora, user_id),
        )
        conn.commit()


def can_change_juramento(player: dict[str, Any], cooldown_days: int = 30) -> tuple[bool, int]:
    escolhido_em = parse_iso_datetime(player.get("juramento_escolhido_em"))
    if not escolhido_em:
        return True, 0

    agora = datetime.now(timezone.utc)
    liberacao = escolhido_em + timedelta(days=cooldown_days)
    restante = liberacao - agora
    if restante.total_seconds() <= 0:
        return True, 0

    dias_restantes = max(restante.days + (1 if restante.seconds > 0 else 0), 1)
    return False, dias_restantes


# ============================================================
# 6) UI
# ============================================================
class ClasseView(discord.ui.View):
    def __init__(self, author_id: int, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Apenas o invocador pode selar este rito.", ephemeral=True)
            return False
        return True

    async def escolher(self, interaction: discord.Interaction, classe_id: str) -> None:
        try:
            user_id = str(interaction.user.id)
            if user_id == INKOSI_ID:
                await interaction.response.send_message("A assinatura ABSOLUTA não nasce por escolha ritual.", ephemeral=True)
                return
            if player_exists(user_id):
                await interaction.response.send_message("Teu destino já foi inscrito.", ephemeral=True)
                return

            data = CLASSES[classe_id]
            a = data["atributos"]
            create_player(
                user_id=user_id,
                classe_id=classe_id,
                is_excecao=0,
                nivel="1",
                forca=a["FOR"],
                resistencia=a["RES"],
                agilidade=a["AGI"],
                inteligencia=a["INT"],
                mana=a["MAN"],
                crescimento=data["crescimento"],
                titulo=data["titulo"],
                lore_texto=data["lore_texto"],
                pressagio=data["pressagio"],
            )
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True

            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f"Rito selado: **{data['nome']}**.")
        except Exception as exc:
            logger.exception("Falha em botão de classe")
            uid = str(interaction.user.id if interaction.user else "0")
            seal = "SEM_SELO"
            try:
                seal = log_failure("BTN", uid, str(exc))
            except Exception:
                logger.exception("Falha ao registrar selo BTN")
            mensagem = f"{VOICE['erro']} Selo de falha: BTN-{seal}."
            if interaction.response.is_done():
                await interaction.followup.send(mensagem, ephemeral=True)
            else:
                await interaction.response.send_message(mensagem, ephemeral=True)

    @discord.ui.button(label="Guerreiro", style=discord.ButtonStyle.danger)
    async def b1(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        del button
        await self.escolher(interaction, "guerreiro")

    @discord.ui.button(label="Mago", style=discord.ButtonStyle.primary)
    async def b2(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        del button
        await self.escolher(interaction, "mago")

    @discord.ui.button(label="Caçador", style=discord.ButtonStyle.secondary)
    async def b3(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        del button
        await self.escolher(interaction, "cacador")

    @discord.ui.button(label="Soldado", style=discord.ButtonStyle.success)
    async def b4(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        del button
        await self.escolher(interaction, "soldado")

    @discord.ui.button(label="Explorador", style=discord.ButtonStyle.secondary)
    async def b5(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        del button
        await self.escolher(interaction, "explorador")


# ============================================================
# 7) COMANDOS (FASE 1 + FASE 2)
# ============================================================
@bot.command(name="iniciar")
async def iniciar(ctx: commands.Context) -> None:
    try:
        user_id = str(ctx.author.id)

        if user_id == INKOSI_ID:
            try:
                create_inkosi_record_if_needed(user_id)
            except sqlite3.Error:
                logger.exception("Falha SQLite no registro Inkosi; tentando auto-reparo")
                init_db()
                try:
                    create_inkosi_record_if_needed(user_id)
                except sqlite3.Error as exc2:
                    logger.exception("Falha persistente no registro Inkosi")
                    await send_grimoire_error(
                        ctx,
                        "iniciar.inkosi",
                        command_name="iniciar",
                        user_id=user_id,
                        error=exc2,
                    )
                    await ctx.send(canon_line("recusa", "O trono oculto recusou o selo neste instante. Tenta novamente em alguns segundos."))
                    return

            embed = discord.Embed(
                title="REGISTRO IMPOSSÍVEL DETECTADO",
                description=canon_line("abertura", "O Sistema tentou classificar a assinatura e aceitou apenas: **ABSOLUTO**."),
                color=discord.Color.dark_red(),
            )
            embed.add_field(name="Designação", value="Aquele que Não se Submete", inline=False)
            embed.add_field(name="Classificação", value="Não Indexável", inline=False)
            embed.set_footer(text="FASE 1 — Núcleo do Jogador • Exceção canônica")
            await ctx.send(embed=embed)
            return

        if player_exists(user_id):
            await ctx.send(canon_line("recusa", "Teu nome já repousa no Grimório. Usa `!perfil`."))
            return

        embed = build_iniciar_embed()
        try:
            await ctx.send(embed=embed, view=ClasseView(author_id=ctx.author.id))
        except Exception as view_exc:
            logger.exception("Falha ao enviar painel de classes; usando fallback textual")
            try:
                await ctx.send(embed=embed)
                await ctx.send(canon_line("recusa", "Painel ritual indisponível. Usa `!classe <guerreiro|mago|cacador|soldado|explorador>`."))
            except Exception:
                logger.exception("Fallback textual do !iniciar também falhou")
                raise view_exc
    except Exception as exc:
        logger.exception("Falha no comando !iniciar")
        await send_grimoire_error(ctx, "iniciar", command_name="iniciar", user_id=str(ctx.author.id), error=exc)


@bot.command(name="classe")
async def classe(ctx: commands.Context, *, classe_id: str | None = None) -> None:
    try:
        if not classe_id:
            await ctx.send(canon_line("recusa", "Uso: `!classe <guerreiro|mago|cacador|soldado|explorador>`."))
            return

        user_id = str(ctx.author.id)
        cid = normalize_class_input(classe_id)
        if not cid or cid not in CLASSES:
            await ctx.send(canon_line("recusa", "Classe inválida."))
            return

        ok, result = register_class_for_user(user_id, cid)
        if not ok:
            await ctx.send(canon_line("recusa", result))
            return

        data = CLASSES[cid]
        embed = discord.Embed(
            title="RITUAL CONCLUÍDO",
            description=canon_line("sucesso", f"**{ctx.author.display_name}** foi inscrito como **{result}**."),
            color=EMBED_COLOR,
        )
        embed.add_field(name="Título", value=data["titulo"], inline=False)
        embed.set_footer(text="FASE 1 — Núcleo do Jogador • Juramento selado")
        await ctx.send(embed=embed)
    except Exception as exc:
        logger.exception("Falha no comando !classe")
        await send_grimoire_error(ctx, "classe", command_name="classe", user_id=str(ctx.author.id), error=exc)


def normalize_juramento_input(raw: str) -> str:
    aliases = {
        "trono": "trono",
        "ao trono": "trono",
        "verdade": "verdade",
        "verdade oculta": "verdade",
        "fronteira": "fronteira",
        "a fronteira": "fronteira",
        "cinzas": "cinzas",
        "as cinzas": "cinzas",
    }
    return aliases.get(raw.strip().lower(), "")


@bot.command(name="juramento")
async def juramento(ctx: commands.Context, *, escolha: str | None = None) -> None:
    try:
        user_id = str(ctx.author.id)
        player = get_player(user_id)
        if not player:
            await ctx.send(canon_line("recusa", "Nenhum registro foi encontrado. Invoque `!iniciar` primeiro."))
            return

        if int(player.get("is_excecao", 0)) == 1:
            await ctx.send(canon_line("recusa", "A assinatura ABSOLUTA não se curva a juramentos comuns."))
            return

        if not escolha:
            opcoes = "\n".join(f"• `{k}` — {v}" for k, v in JURAMENTOS.items())
            await ctx.send(canon_line("abertura", f"Selos canônicos disponíveis:\n{opcoes}\n\nUso: `!juramento <opção>`."))
            return

        juramento_key = normalize_juramento_input(escolha)
        if juramento_key not in JURAMENTOS:
            await ctx.send(canon_line("recusa", "Juramento inválido. Use `!juramento` para listar os selos canônicos."))
            return

        atual = str(player.get("juramento") or "").strip().lower()
        if atual == juramento_key:
            await ctx.send(canon_line("recusa", "Este juramento já está selado em teu nome."))
            return

        if atual:
            permitido, dias_restantes = can_change_juramento(player, cooldown_days=30)
            if not permitido:
                await ctx.send(canon_line("recusa", f"Teu voto ainda ecoa. Nova troca disponível em aproximadamente {dias_restantes} dia(s)."))
                return

        set_player_juramento(user_id, juramento_key)
        add_player_marco(user_id, "juramento_selado", "Juramento selado")
        add_annal_entry(user_id, f"Juramento selado: {JURAMENTOS[juramento_key]}")
        await ctx.send(canon_line("sucesso", f"Juramento inscrito: **{JURAMENTOS[juramento_key]}**"))
    except Exception as exc:
        logger.exception("Falha no comando !juramento")
        await send_grimoire_error(ctx, "juramento", command_name="juramento", user_id=str(ctx.author.id), error=exc)


@bot.command(name="trilha")
async def trilha(ctx: commands.Context) -> None:
    try:
        user_id = str(ctx.author.id)
        player = get_player(user_id)
        if not player:
            await ctx.send(canon_line("recusa", "Nenhum registro foi encontrado. Invoque `!iniciar`."))
            return

        status = get_trilha_status(player)
        if status["proximo"]:
            progresso = f"{status['progresso_atual']}/{status['progresso_necessario']}"
            proximo = f"**Próximo degrau:** {status['proximo']} ({progresso})"
        else:
            proximo = "**Próximo degrau:** nenhum — tua trilha já alcançou o ápice."

        await ctx.send(
            canon_line(
                "abertura",
                (
                    f"**Posição narrativa:** {status['atual']}\n"
                    f"{proximo}\n"
                    f"Critérios atuais: registros `{status['annals']}`, dias desde despertar `{status['dias']}`, prestígio `{status['prestigio']}`."
                ),
            )
        )
    except Exception as exc:
        logger.exception("Falha no comando !trilha")
        await send_grimoire_error(ctx, "trilha", command_name="trilha", user_id=str(ctx.author.id), error=exc)


@bot.command(name="legado")
async def legado(ctx: commands.Context) -> None:
    try:
        user_id = str(ctx.author.id)
        player = get_player(user_id)
        if not player:
            await ctx.send(canon_line("recusa", "Nenhum registro foi encontrado. Invoque `!iniciar`."))
            return

        marcos = get_player_marcos(user_id)
        if not marcos:
            await ctx.send(canon_line("abertura", "Teu legado ainda está em branco. Nenhum marco histórico foi selado."))
            return

        linhas = [f"• {m['descricao']} (`{m['criado_em'][:10]}`)" for m in marcos[:10]]
        await ctx.send(canon_line("abertura", "**Marcas históricas:**\n" + "\n".join(linhas)))
    except Exception as exc:
        logger.exception("Falha no comando !legado")
        await send_grimoire_error(ctx, "legado", command_name="legado", user_id=str(ctx.author.id), error=exc)


@bot.command(name="oraculo")
async def oraculo(ctx: commands.Context) -> None:
    try:
        world_state = get_world_state()
        embed = discord.Embed(
            title="ORÁCULO IMPERIAL",
            description=build_oraculo_message(world_state),
            color=EMBED_COLOR,
        )
        embed.set_footer(text="Etapa 2 — Estado do Mundo")
        await ctx.send(embed=embed)
    except Exception as exc:
        logger.exception("Falha no comando !oraculo")
        await send_grimoire_error(ctx, "oraculo", command_name="oraculo", user_id=str(ctx.author.id), error=exc)


@bot.command(name="conselho")
async def conselho(ctx: commands.Context, *, escolha: str | None = None) -> None:
    try:
        session = ensure_current_council_session(opened_by=str(ctx.author.id))
        if not session:
            await ctx.send(canon_line("erro", "O Conselho não pôde ser convocado."))
            return

        if not escolha:
            counts = get_council_vote_counts(int(session["id"]))
            opcoes = "\n".join(
                f"• `{key}` — {meta['label']} ({counts.get(key, 0)} voto(s))"
                for key, meta in COUNCIL_OPTIONS.items()
            )
            await ctx.send(
                canon_line(
                    "abertura",
                    f"Conselho semanal `{session['week_key']}` aberto.\n{opcoes}\n\nVote com `!conselho <opção>`.",
                )
            )
            return

        escolha_norm = escolha.strip().lower()
        if escolha_norm == "encerrar":
            if not ctx.author.guild_permissions.administrator:
                await ctx.send(canon_line("recusa", "Somente administradores podem encerrar o Conselho semanal."))
                return
            ok, msg = finalize_council_session(session, actor_user_id=str(ctx.author.id))
            await ctx.send(canon_line("sucesso" if ok else "recusa", msg))
            return

        ok, result = register_council_vote(int(session["id"]), str(ctx.author.id), escolha_norm)
        await ctx.send(canon_line("sucesso" if ok else "recusa", result if not ok else f"Voto selado em **{result}**."))
    except Exception as exc:
        logger.exception("Falha no comando !conselho")
        await send_grimoire_error(ctx, "conselho", command_name="conselho", user_id=str(ctx.author.id), error=exc)


@bot.command(name="decreto")
@commands.has_permissions(administrator=True)
async def decreto(ctx: commands.Context, *, texto: str) -> None:
    try:
        conteudo = texto.strip()
        if len(conteudo) < 5:
            await ctx.send(canon_line("recusa", "Informe um decreto mais completo (mínimo de 5 caracteres)."))
            return

        now = datetime.now(timezone.utc).isoformat()
        with get_conn() as conn:
            ensure_world_state_row(conn)
            conn.execute(
                "UPDATE world_state SET decreto_ativo = ?, atualizado_em = ? WHERE singleton_id = 1",
                (conteudo, now),
            )
            conn.commit()

        add_global_event("decreto", "Decreto Imperial", conteudo, actor_user_id=str(ctx.author.id))
        await ctx.send(canon_line("sucesso", f"Novo decreto selado:\n**{conteudo}**"))
    except Exception as exc:
        logger.exception("Falha no comando !decreto")
        await send_grimoire_error(ctx, "decreto", command_name="decreto", user_id=str(ctx.author.id), error=exc)


@decreto.error
async def decreto_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(canon_line("recusa", "Somente administradores podem decretar a vontade imperial."))
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(canon_line("recusa", "Uso: `!decreto <texto>`."))
    else:
        logger.exception("Erro não tratado em !decreto", exc_info=error)
        await send_grimoire_error(ctx, "decreto.error", command_name="decreto.error", user_id=str(ctx.author.id), error=error)


@bot.command(name="intriga")
async def intriga(ctx: commands.Context, *, linha: str | None = None) -> None:
    try:
        if not linha:
            await ctx.send(canon_line("recusa", "Uso: `!intriga <rumor|denuncia|alianca|ameaca> <texto>`."))
            return

        partes = linha.strip().split(maxsplit=1)
        tipo = partes[0].lower()
        texto = partes[1].strip() if len(partes) > 1 else ""

        if tipo not in INTRIGA_TYPES or not texto:
            await ctx.send(canon_line("recusa", "Formato inválido. Exemplo: `!intriga rumor Tropas vistas no norte`."))
            return

        titulo = f"Intriga — {tipo.title()}"
        add_global_event("intriga", titulo, texto, actor_user_id=str(ctx.author.id))
        await ctx.send(canon_line("sucesso", f"Intriga registrada nos Anais Globais como **{tipo}**."))
    except Exception as exc:
        logger.exception("Falha no comando !intriga")
        await send_grimoire_error(ctx, "intriga", command_name="intriga", user_id=str(ctx.author.id), error=exc)


@bot.command(name="anaisglobal")
async def anaisglobal(ctx: commands.Context) -> None:
    try:
        eventos = get_global_events(limit=15)
        if not eventos:
            await ctx.send(canon_line("abertura", "Os Anais Globais ainda não receberam decretos, conselhos ou intrigas."))
            return

        linhas = [
            f"`{e['created_em'][:10]}` • **{e['event_type'].upper()}** • {e['title']}\n{(e['detail'] or '').strip()}"
            for e in eventos
            if e["event_type"] in {"decreto", "conselho", "intriga"}
        ]
        if not linhas:
            await ctx.send(canon_line("abertura", "Nenhum evento político disponível nos Anais Globais."))
            return

        await ctx.send(canon_line("abertura", "**Anais Globais do Império**\n" + "\n\n".join(linhas[:10])))
    except Exception as exc:
        logger.exception("Falha no comando !anaisglobal")
        await send_grimoire_error(ctx, "anaisglobal", command_name="anaisglobal", user_id=str(ctx.author.id), error=exc)


@bot.command(name="perfil")
async def perfil(ctx: commands.Context) -> None:
    try:
        user_id = str(ctx.author.id)
        player = create_inkosi_record_if_needed(user_id) if user_id == INKOSI_ID else get_player(user_id)

        if not player:
            await ctx.send(canon_line("recusa", "Nenhum registro foi encontrado. Invoque `!iniciar`."))
            return

        if int(player.get("is_excecao", 0)) == 1:
            embed = discord.Embed(
                title="REGISTRO ABSOLUTO",
                description="Os arquivos tentaram ordenar esta presença e foram reduzidos ao silêncio.",
                color=discord.Color.dark_red(),
            )
            embed.add_field(name="Designação", value="Aquele que Não se Submete", inline=False)
            embed.add_field(name="Classificação", value="Não Indexável", inline=False)
            embed.add_field(name="Essência", value="**FOR:** MAX | **RES:** MAX | **AGI:** MAX | **INT:** MAX | **MAN:** MAX", inline=False)
            embed.set_footer(text="FASE 1 — Núcleo do Jogador • Registro canônico")
            await ctx.send(embed=embed)
            return

        classe_id = player["classe"]
        classe_nome = CLASSES.get(classe_id, {}).get("nome", classe_id.title())
        juramento_key = str(player.get("juramento") or "").strip().lower()
        juramento_texto = JURAMENTOS.get(juramento_key, "Ainda não selado. Use `!juramento <opção>`.")
        trilha = get_trilha_status(player)

        embed = discord.Embed(title="GRIMÓRIO DO DESTINO", description=canon_line("abertura"), color=EMBED_COLOR)
        embed.add_field(name="Identidade", value=f"**Nome:** {ctx.author.display_name}\n**Classe:** {classe_nome}\n**Título:** {player['titulo']}", inline=False)
        embed.add_field(name="Essência", value=f"**FOR:** {player['forca']} | **RES:** {player['resistencia']} | **AGI:** {player['agilidade']} | **INT:** {player['inteligencia']} | **MAN:** {player['mana']}", inline=False)
        embed.add_field(name="Juramento", value=juramento_texto, inline=False)
        embed.add_field(name="Trilha", value=trilha["atual"], inline=False)
        embed.add_field(name="Caminho Escolhido", value=player["lore_texto"], inline=False)
        embed.add_field(name="Tendência de Crescimento", value=player["crescimento"], inline=False)
        embed.add_field(name="Presságio", value=player["pressagio"], inline=False)
        embed.set_footer(text="FASE 1 — Núcleo do Jogador • Registro canônico")
        await ctx.send(embed=embed)
    except Exception as exc:
        logger.exception("Falha no comando !perfil")
        await send_grimoire_error(ctx, "perfil", command_name="perfil", user_id=str(ctx.author.id), error=exc)


@bot.command(name="resetar")
@commands.has_permissions(administrator=True)
async def resetar(ctx: commands.Context, membro: discord.Member) -> None:
    try:
        alvo_id = str(membro.id)
        if not player_exists(alvo_id):
            await ctx.send(canon_line("recusa", f"Nenhum selo ativo foi encontrado para **{membro.display_name}**."))
            return

        delete_player(alvo_id)
        if alvo_id == INKOSI_ID:
            await ctx.send("⚠️ **REVOGAÇÃO IMPOSSÍVEL, MAS EXECUTADA**\nAté mesmo o Registro Absoluto foi removido por decreto administrativo.")
            return

        await ctx.send(canon_line("sucesso", f"Revogação do Registro executada para **{membro.display_name}**."))
    except Exception as exc:
        logger.exception("Falha no comando !resetar")
        await send_grimoire_error(ctx, "resetar", command_name="resetar", user_id=str(ctx.author.id), error=exc)


@resetar.error
async def resetar_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(canon_line("recusa", "Somente administradores podem decretar a Revogação do Registro."))
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(canon_line("recusa", "Uso correto: `!resetar @membro`"))
    else:
        logger.exception("Erro não tratado em !resetar", exc_info=error)
        await send_grimoire_error(ctx, "resetar.error", command_name="resetar.error", user_id=str(ctx.author.id), error=error)


@bot.command(name="eu")
async def eu(ctx: commands.Context) -> None:
    await ctx.send("Sou o Grimório de EBR: registro destinos, não promessas.")


@bot.command(name="changelog")
async def changelog(ctx: commands.Context) -> None:
    embed = discord.Embed(title="Changelog — Núcleo do Jogador", color=EMBED_COLOR)
    embed.description = """**Etapa 3 — Política semanal**
• `!conselho` abre votação semanal com opções fixas e evita voto duplicado
• `!decreto <texto>` (admin) altera o mundo e entra nos Anais Globais
• `!intriga` e `!anaisglobal` consolidam os eventos políticos do Império"""
    embed.set_footer(text="EBR • Base estável")
    await ctx.send(embed=embed)




@bot.command(name="diagnostico")
@commands.has_permissions(administrator=True)
async def diagnostico(ctx: commands.Context) -> None:
    try:
        info = get_db_diagnostics()
        failures = get_recent_failures(limit=5)

        embed = discord.Embed(
            title="DIAGNÓSTICO DO GRIMÓRIO",
            description="Painel técnico para investigar selos de falha recentes.",
            color=EMBED_COLOR,
        )
        embed.add_field(
            name="Banco SQLite",
            value=(
                f"**Path:** `{info['db_path']}`\n"
                f"**Arquivo existe:** {info['db_exists']}\n"
                f"**Diretório existe:** {info['data_dir_exists']}\n"
                f"**Diretório gravável:** {info['data_dir_writable']}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Contadores",
            value=(
                f"**Players:** {info['players_count']}\n"
                f"**Falhas registradas:** {info['failure_count']}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Estado do Mundo",
            value=(
                f"**Tensão nas fronteiras:** {info['world_tensao']}\n"
                f"**Última atualização:** {str(info['world_atualizado_em'])[:19]}"
            ),
            inline=False,
        )

        if failures:
            lines = []
            for row in failures:
                lines.append(
                    f"`{row['timestamp_utc'][:19]}` • `{row['command_name']}` • `{row['hash_curto']}` • uid `{row['user_id']}`"
                )
            embed.add_field(name="Últimos selos", value="\n".join(lines[:5]), inline=False)

        embed.set_footer(text="Etapa 2 • Estado do Mundo")
        await ctx.send(embed=embed)
    except Exception as exc:
        logger.exception("Falha no comando !diagnostico")
        await send_grimoire_error(ctx, "diagnostico", command_name="diagnostico", user_id=str(ctx.author.id), error=exc)

@diagnostico.error
async def diagnostico_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(canon_line("recusa", "Somente administradores podem invocar `!diagnostico`."))
    else:
        logger.exception("Erro não tratado em !diagnostico", exc_info=error)
        await send_grimoire_error(ctx, "diagnostico.error", command_name="diagnostico.error", user_id=str(ctx.author.id), error=error)

@bot.command(name="guia")
async def guia(ctx: commands.Context) -> None:
    embed = discord.Embed(
        title="Guia do Grimório — EBR",
        description="Fase estável ativa: identidade canônica e registros persistentes.",
        color=EMBED_COLOR,
    )
    embed.add_field(name="Comandos", value="`!iniciar` • `!classe` • `!juramento` • `!trilha` • `!legado` • `!oraculo` • `!conselho` • `!decreto` • `!intriga` • `!anaisglobal` • `!perfil` • `!resetar @membro` • `!eu` • `!changelog` • `!guia` • `!diagnostico`", inline=False)
    embed.add_field(name="Estado Atual", value="Etapa 3: política semanal com Conselho, Decreto e Intriga persistentes.", inline=False)
    embed.set_footer(text="EBR • Orientação oficial")
    await ctx.send(embed=embed)

# ============================================================
# 8) EVENTOS
# ============================================================


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandNotFound):
        return

    logger.exception("Erro global de comando: %s", error)
    await send_grimoire_error(
        ctx,
        "global",
        command_name=(ctx.command.qualified_name if ctx.command else "global"),
        user_id=str(ctx.author.id if ctx.author else "0"),
        error=error,
    )

@bot.event
async def on_ready() -> None:
    logger.info("Bot conectado como %s (%s)", bot.user, bot.user.id if bot.user else "?")


# ============================================================
# 9) MAIN/RUN
# ============================================================
def main() -> None:
    try:
        init_db()
    except Exception:
        logger.exception("Falha ao inicializar banco")
        raise

    try:
        token = resolve_token()
    except RuntimeError as exc:
        logger.error("Inicialização abortada: %s", exc)
        raise SystemExit(1) from exc

    try:
        bot.run(token)
    except discord.LoginFailure:
        logger.error("Falha de autenticação Discord (token inválido).")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
