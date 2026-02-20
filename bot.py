import logging
import os
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


def now_ts() -> int:
    return int(time.time())


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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

        conn.execute("CREATE INDEX IF NOT EXISTS idx_operation_runs_user ON operation_runs(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_generals_user ON generals(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_strategists_user ON strategists(user_id)")

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
                   a.troops, a.doctrine, a.power, a.last_train_ts
            FROM domains d
            JOIN domain_buildings b ON b.user_id = d.user_id
            JOIN resources r ON r.user_id = d.user_id
            JOIN army a ON a.user_id = d.user_id
            WHERE d.user_id = ?
            """,
            (user_id,),
        ).fetchone()


def update_player_state(user_id: str, *, gold: int | None = None, last_collect_ts: int | None = None,
                        accumulated_maintenance: int | None = None, troops: int | None = None,
                        last_train_ts: int | None = None, power: int | None = None,
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

        if troops is not None or last_train_ts is not None or power is not None:
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


@bot.command(name="dominio")
async def dominio(ctx: commands.Context) -> None:
    d = get_or_create_domain(str(ctx.author.id))
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
    embed.add_field(name="Militar", value=f"👥 Tropas: **{d['troops']:,}**\n⚔️ Poder: **{d['power']:,}**".replace(",", "."), inline=False)
    embed.set_footer(text="Ações: !coletar • !treinar • !melhorar <celeiros|casernas|forja> • !rank")
    await ctx.send(embed=embed)


@bot.command(name="coletar")
async def coletar(ctx: commands.Context) -> None:
    user_id = str(ctx.author.id)
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

    new_gold = d["gold"] + net_gain
    if new_gold < 0:
        new_gold = 0
    update_player_state(
        user_id,
        gold=new_gold,
        last_collect_ts=now,
        accumulated_maintenance=d["accumulated_maintenance"] + max(0, maintenance_cost),
    )

    await ctx.send(
        (
            "✅ Coleta concluída.\n"
            f"Δ Ouro bruto: +{gross_gain:,}\n"
            f"Δ Manutenção: -{maintenance_cost:,}\n"
            f"Δ Líquido: {net_gain:+,}\n"
            f"Saldo: {new_gold:,}\n"
            "Próximo: `!melhorar celeiros` ou `!treinar`"
        ).replace(",", ".")
    )


@bot.command(name="treinar")
async def treinar(ctx: commands.Context) -> None:
    user_id = str(ctx.author.id)
    d = get_or_create_domain(user_id)
    now = now_ts()
    delta = now - d["last_train_ts"]
    if delta < TRAIN_COOLDOWN_SECONDS:
        rest = TRAIN_COOLDOWN_SECONDS - delta
        await ctx.send(f"⏳ Casernas em cooldown. Tenta novamente em {max(1, rest // 60)} min.")
        return

    troops_gain = barracks_train_amount(d["barracks_level"])
    new_troops = d["troops"] + troops_gain
    new_power = recalc_power(new_troops, d["barracks_level"], d["forge_level"])
    update_player_state(user_id, troops=new_troops, power=new_power, last_train_ts=now)

    await ctx.send(
        (
            "✅ Treino concluído.\n"
            f"Δ Tropas: +{troops_gain:,}\n"
            f"⚔️ Poder atual: {new_power:,}\n"
            "Próximo: `!rank` ou `!melhorar casernas`"
        ).replace(",", ".")
    )


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
    cost = building_upgrade_cost(level, estrutura)
    if d["gold"] < cost:
        await ctx.send(f"❌ Ouro insuficiente. Falta {(cost - d['gold']):,}.".replace(",", "."))
        return

    new_level = level + 1
    params = {"gold": d["gold"] - cost, level_key: new_level}
    if estrutura in {"casernas", "forja"}:
        barracks_level = new_level if estrutura == "casernas" else d["barracks_level"]
        forge_level = new_level if estrutura == "forja" else d["forge_level"]
        params["power"] = recalc_power(d["troops"], barracks_level, forge_level)

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


@bot.command(name="rank")
async def rank(ctx: commands.Context) -> None:
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
    await ctx.send(embed=embed)


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
        "Comandos: `!dominio`, `!coletar`, `!treinar`, `!melhorar`, `!rank`, `!economia_teste`, `!diagnostico`, `!guia`.\n"
        "Loop: Coletar → Melhorar → Treinar → Rank."
    )


@bot.command(name="diagnostico")
@commands.has_permissions(administrator=True)
async def diagnostico(ctx: commands.Context) -> None:
    with get_conn() as conn:
        counts = {}
        for table in [
            "domains", "domain_buildings", "resources", "army", "generals", "strategists", "operations",
            "operation_runs", "items", "inventories", "season_state", "season_scores",
        ]:
            counts[table] = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]

    lines = [f"{k}: {v}" for k, v in counts.items()]
    await ctx.send(f"Diagnóstico Fase 1\nDB: `{DB_PATH}`\n" + "\n".join(lines))


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
