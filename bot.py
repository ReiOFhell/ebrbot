import logging
import os
import sqlite3
import time
from pathlib import Path

import discord
from discord.ext import commands

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("ebr.nucleoc")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "nucleoc.db"

DISCORD_TOKEN_FALLBACK = ""  # opcional: cole aqui apenas para teste local


def resolve_token() -> str:
    token = (os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN") or DISCORD_TOKEN_FALLBACK or "").strip()
    if not token:
        raise RuntimeError(
            "Token não encontrado. Defina a variável de ambiente DISCORD_TOKEN (ou BOT_TOKEN)."
        )
    return token

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

BARN_BASE_PROD = 12000  # ouro/h no nível 1
BARRACKS_BASE_TRAIN = 10  # tropas a cada 30 min no nível 1
TRAIN_COOLDOWN_SECONDS = 30 * 60
COLLECT_CAP_SECONDS = 24 * 60 * 60


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS domains (
                user_id TEXT PRIMARY KEY,
                gold INTEGER NOT NULL DEFAULT 100000,
                prestige INTEGER NOT NULL DEFAULT 0,
                power INTEGER NOT NULL DEFAULT 0,
                barn_level INTEGER NOT NULL DEFAULT 1,
                barracks_level INTEGER NOT NULL DEFAULT 1,
                forge_level INTEGER NOT NULL DEFAULT 1,
                troops INTEGER NOT NULL DEFAULT 0,
                last_collect_ts INTEGER NOT NULL,
                last_train_ts INTEGER NOT NULL,
                created_at_ts INTEGER NOT NULL
            )
            """
        )
        conn.commit()


def now_ts() -> int:
    return int(time.time())


def get_or_create_domain(user_id: str) -> sqlite3.Row:
    ts = now_ts()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM domains WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            return row
        conn.execute(
            """
            INSERT INTO domains (user_id, last_collect_ts, last_train_ts, created_at_ts)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, ts, ts, ts),
        )
        conn.commit()
        return conn.execute("SELECT * FROM domains WHERE user_id = ?", (user_id,)).fetchone()


def building_upgrade_cost(level: int, base: int) -> int:
    return int(base * (2.55 ** (level - 1)))


def barn_production_per_hour(level: int) -> int:
    return int(BARN_BASE_PROD * (2.2 ** (level - 1)))


def barracks_train_amount(level: int) -> int:
    return int(BARRACKS_BASE_TRAIN * (2.2 ** (level - 1)))


def recalc_power(troops: int, barracks_level: int, forge_level: int) -> int:
    return int(troops + (barracks_level * 50) + (forge_level * 30))


def update_domain(user_id: str, **fields: int) -> None:
    if not fields:
        return
    keys = list(fields.keys())
    assignments = ", ".join(f"{k} = ?" for k in keys)
    values = [fields[k] for k in keys]
    with get_conn() as conn:
        conn.execute(f"UPDATE domains SET {assignments} WHERE user_id = ?", (*values, user_id))
        conn.commit()


@bot.command(name="dominio")
async def dominio(ctx: commands.Context) -> None:
    user_id = str(ctx.author.id)
    d = get_or_create_domain(user_id)
    prod_h = barn_production_per_hour(d["barn_level"])
    next_barn = building_upgrade_cost(d["barn_level"], 100_000)
    next_barracks = building_upgrade_cost(d["barracks_level"], 120_000)
    next_forge = building_upgrade_cost(d["forge_level"], 90_000)

    embed = discord.Embed(title="🏰 Domínio Imperial", color=discord.Color.dark_gold())
    embed.add_field(
        name="Recursos",
        value=f"🪙 Ouro: **{d['gold']:,}**\n🏆 Prestígio: **{d['prestige']:,}**\n⚔️ Poder: **{d['power']:,}".replace(",", "."),
        inline=False,
    )
    embed.add_field(
        name="Estruturas",
        value=(
            f"🌾 Celeiros T{d['barn_level']} (produção {prod_h:,}/h)\n"
            f"🛡️ Casernas T{d['barracks_level']}\n"
            f"🔨 Forja T{d['forge_level']}"
        ).replace(",", "."),
        inline=False,
    )
    embed.add_field(
        name="Militar",
        value=f"👥 Tropas: **{d['troops']:,}**".replace(",", "."),
        inline=False,
    )
    embed.add_field(
        name="Próximos upgrades",
        value=(
            f"`!melhorar celeiros` → {next_barn:,} ouro\n"
            f"`!melhorar casernas` → {next_barracks:,} ouro\n"
            f"`!melhorar forja` → {next_forge:,} ouro"
        ).replace(",", "."),
        inline=False,
    )
    embed.set_footer(text="Ações: !coletar • !treinar • !melhorar <celeiros|casernas|forja> • !rank")
    await ctx.send(embed=embed)


@bot.command(name="coletar")
async def coletar(ctx: commands.Context) -> None:
    user_id = str(ctx.author.id)
    d = get_or_create_domain(user_id)
    now = now_ts()
    elapsed = max(0, min(now - d["last_collect_ts"], COLLECT_CAP_SECONDS))
    gold_gain = int(barn_production_per_hour(d["barn_level"]) * (elapsed / 3600))

    new_gold = d["gold"] + gold_gain
    update_domain(user_id, gold=new_gold, last_collect_ts=now)

    await ctx.send(
        f"✅ Coleta concluída.\n"
        f"Δ Ouro: +{gold_gain:,}\n"
        f"Saldo: {new_gold:,}\n"
        f"Próximo: `!melhorar celeiros` ou `!treinar`".replace(",", ".")
    )


@bot.command(name="treinar")
async def treinar(ctx: commands.Context) -> None:
    user_id = str(ctx.author.id)
    d = get_or_create_domain(user_id)
    now = now_ts()
    delta = now - d["last_train_ts"]
    if delta < TRAIN_COOLDOWN_SECONDS:
        rest = TRAIN_COOLDOWN_SECONDS - delta
        minutes = max(1, rest // 60)
        await ctx.send(f"⏳ Casernas em cooldown. Tenta novamente em {minutes} min.")
        return

    troops_gain = barracks_train_amount(d["barracks_level"])
    new_troops = d["troops"] + troops_gain
    new_power = recalc_power(new_troops, d["barracks_level"], d["forge_level"])
    update_domain(user_id, troops=new_troops, power=new_power, last_train_ts=now)

    await ctx.send(
        f"✅ Treino concluído.\n"
        f"Δ Tropas: +{troops_gain:,}\n"
        f"⚔️ Poder atual: {new_power:,}\n"
        f"Próximo: `!rank` ou `!melhorar casernas`".replace(",", ".")
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

    if estrutura == "celeiros":
        level_key, base = "barn_level", 100_000
    elif estrutura == "casernas":
        level_key, base = "barracks_level", 120_000
    else:
        level_key, base = "forge_level", 90_000

    level = d[level_key]
    cost = building_upgrade_cost(level, base)
    if d["gold"] < cost:
        await ctx.send(f"❌ Ouro insuficiente. Falta {(cost - d['gold']):,}.".replace(",", "."))
        return

    new_level = level + 1
    fields = {"gold": d["gold"] - cost, level_key: new_level}
    if estrutura == "casernas" or estrutura == "forja":
        fields["power"] = recalc_power(d["troops"], new_level if estrutura == "casernas" else d["barracks_level"], new_level if estrutura == "forja" else d["forge_level"])
    update_domain(user_id, **fields)

    await ctx.send(
        f"✅ Upgrade concluído: **{estrutura} T{new_level}**.\n"
        f"Δ Ouro: -{cost:,}\n"
        f"Próximo: `!dominio` para ver o impacto.".replace(",", ".")
    )


@bot.command(name="rank")
async def rank(ctx: commands.Context) -> None:
    with get_conn() as conn:
        rich = conn.execute("SELECT user_id, gold FROM domains ORDER BY gold DESC LIMIT 5").fetchall()
        war = conn.execute("SELECT user_id, power FROM domains ORDER BY power DESC LIMIT 5").fetchall()
        prest = conn.execute("SELECT user_id, prestige FROM domains ORDER BY prestige DESC LIMIT 5").fetchall()

    def fmt(rows: list[sqlite3.Row], metric: str) -> str:
        if not rows:
            return "Sem dados."
        out = []
        for i, r in enumerate(rows, start=1):
            out.append(f"{i}. <@{r['user_id']}> — {r[metric]:,}".replace(",", "."))
        return "\n".join(out)

    embed = discord.Embed(title="🏛️ Rankings Imperiais", color=discord.Color.blurple())
    embed.add_field(name="Magnatas (Ouro)", value=fmt(rich, "gold"), inline=False)
    embed.add_field(name="Senhores de Guerra (Poder)", value=fmt(war, "power"), inline=False)
    embed.add_field(name="Lendas (Prestígio)", value=fmt(prest, "prestige"), inline=False)
    await ctx.send(embed=embed)


@bot.command(name="guia")
async def guia(ctx: commands.Context) -> None:
    await ctx.send(
        "**Núcleo C ativo (estrutura limpa).**\n"
        "Comandos atuais: `!dominio`, `!coletar`, `!treinar`, `!melhorar`, `!rank`, `!diagnostico`, `!guia`.\n"
        "Loop: Coletar → Melhorar → Treinar → Rank."
    )


@bot.command(name="diagnostico")
@commands.has_permissions(administrator=True)
async def diagnostico(ctx: commands.Context) -> None:
    with get_conn() as conn:
        players = conn.execute("SELECT COUNT(*) c FROM domains").fetchone()["c"]

    await ctx.send(
        f"Diagnóstico:\n"
        f"DB: `{DB_PATH}`\n"
        f"Domínios: {players}\n"
        f"Estrutura: Núcleo C limpa (sem comandos legados)."
    )


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
