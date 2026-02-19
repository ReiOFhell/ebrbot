# ============================================================
# 1) IMPORTS
# ============================================================
import logging
import os
import random
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
COOLDOWN_MINUTES = 20


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


def ensure_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(players)").fetchall()}
    required = {
        "ouro": "INTEGER NOT NULL DEFAULT 0",
        "prestigio": "INTEGER NOT NULL DEFAULT 0",
        "last_aventura_at": "TEXT",
        "streak_aventura": "INTEGER NOT NULL DEFAULT 0",
        "total_aventuras": "INTEGER NOT NULL DEFAULT 0",
    }
    for col, ddl in required.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE players ADD COLUMN {col} {ddl}")


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
        conn.commit()


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
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO players (
                user_id, classe, is_excecao, nivel, criado_em,
                forca, resistencia, agilidade, inteligencia, mana,
                crescimento, titulo, lore_texto, pressagio,
                ouro, prestigio, last_aventura_at, streak_aventura, total_aventuras
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      COALESCE((SELECT ouro FROM players WHERE user_id = ?), 0),
                      COALESCE((SELECT prestigio FROM players WHERE user_id = ?), 0),
                      (SELECT last_aventura_at FROM players WHERE user_id = ?),
                      COALESCE((SELECT streak_aventura FROM players WHERE user_id = ?), 0),
                      COALESCE((SELECT total_aventuras FROM players WHERE user_id = ?), 0))
            """,
            (
                user_id,
                classe_id,
                is_excecao,
                nivel,
                datetime.now(timezone.utc).isoformat(),
                forca,
                resistencia,
                agilidade,
                inteligencia,
                mana,
                crescimento,
                titulo,
                lore_texto,
                pressagio,
                user_id,
                user_id,
                user_id,
                user_id,
                user_id,
            ),
        )
        conn.commit()


def delete_player(user_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM players WHERE user_id = ?", (user_id,))
        conn.commit()


def player_exists(user_id: str) -> bool:
    return get_player(user_id) is not None


def update_player_currency(user_id: str, delta_ouro: int, delta_prestigio: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE players SET ouro = ouro + ?, prestigio = prestigio + ? WHERE user_id = ?",
            (delta_ouro, delta_prestigio, user_id),
        )
        conn.commit()


def set_last_aventura(user_id: str, iso_datetime: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE players SET last_aventura_at = ? WHERE user_id = ?", (iso_datetime, user_id))
        conn.commit()


def increment_stats(user_id: str, *, streak: int | None = None, total_inc: int = 0) -> None:
    with get_conn() as conn:
        if streak is None:
            conn.execute(
                "UPDATE players SET total_aventuras = total_aventuras + ? WHERE user_id = ?",
                (total_inc, user_id),
            )
        else:
            conn.execute(
                "UPDATE players SET streak_aventura = ?, total_aventuras = total_aventuras + ? WHERE user_id = ?",
                (streak, total_inc, user_id),
            )
        conn.commit()


def get_cooldown_remaining(user_id: str) -> int:
    player = get_player(user_id)
    if not player or not player.get("last_aventura_at"):
        return 0

    last_time = datetime.fromisoformat(player["last_aventura_at"])
    now = datetime.now(timezone.utc)
    if last_time.tzinfo is None:
        last_time = last_time.replace(tzinfo=timezone.utc)

    diff = now - last_time
    remaining = int(timedelta(minutes=COOLDOWN_MINUTES).total_seconds() - diff.total_seconds())
    return max(0, remaining)


def format_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}m {s}s"


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

FASE2_ENVIRONMENTS = ["ruínas", "bosque selado", "estradas imperiais", "biblioteca vetusta", "fronteira sombria"]
FASE2_TEXTS = {
    "guerreiro": "Teu aço impôs respeito nas {ambiente}.",
    "mago": "Teus selos brilharam nas {ambiente}.",
    "cacador": "Teu faro conduziu o destino pelas {ambiente}.",
    "soldado": "Teu passo disciplinado sustentou ordem nas {ambiente}.",
    "explorador": "Teu mapa abriu passagem pelas {ambiente}.",
    "inkosi": "As {ambiente} ajustaram-se em silêncio à tua presença.",
}


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
        except Exception:
            logger.exception("Falha em botão de classe")
            if interaction.response.is_done():
                await interaction.followup.send("O Grimório está em silêncio.", ephemeral=True)
            else:
                await interaction.response.send_message("O Grimório está em silêncio.", ephemeral=True)

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
            create_inkosi_record_if_needed(user_id)
            embed = discord.Embed(
                title="REGISTRO IMPOSSÍVEL DETECTADO",
                description="O Sistema tentou classificar a assinatura presente e falhou por inadequação.",
                color=discord.Color.dark_red(),
            )
            embed.add_field(name="Designação", value="Aquele que Não se Submete", inline=False)
            embed.add_field(name="Classificação", value="Não Indexável", inline=False)
            embed.set_footer(text="FASE 1 — Núcleo do Jogador • Exceção canônica")
            await ctx.send(embed=embed)
            return

        if player_exists(user_id):
            await ctx.send("Teu nome já repousa no Grimório. Usa `!perfil`.")
            return

        embed = discord.Embed(
            title="RITUAL DO DESPERTAR",
            description=(
                "**Ato I — O Mundo**\nNo EBR, juramentos moldam a noite.\n\n"
                "**Ato II — A Testemunha**\nO Grimório recolhe teu primeiro voto.\n\n"
                "**Ato III — A Escolha**\nA escolha é única."
            ),
            color=EMBED_COLOR,
        )
        for d in CLASSES.values():
            embed.add_field(name=f"{d['icone']} {d['nome']}", value=d["frase"], inline=False)
        embed.set_footer(text="FASE 1 — Núcleo do Jogador • O destino começa aqui")
        await ctx.send(embed=embed, view=ClasseView(ctx.author.id))
    except Exception:
        logger.exception("Falha em !iniciar")
        await ctx.send("O Grimório está em silêncio.")


@bot.command(name="perfil")
async def perfil(ctx: commands.Context) -> None:
    try:
        user_id = str(ctx.author.id)
        player = create_inkosi_record_if_needed(user_id) if user_id == INKOSI_ID else get_player(user_id)
        if not player:
            await ctx.send("Nenhum registro encontrado. Use `!iniciar`.")
            return

        if int(player.get("is_excecao", 0)) == 1:
            embed = discord.Embed(title="REGISTRO ABSOLUTO", color=discord.Color.dark_red())
            embed.add_field(name="Designação", value="Aquele que Não se Submete", inline=False)
            embed.add_field(name="Classificação", value="Não Indexável", inline=False)
            embed.add_field(name="Essência", value="FOR MAX | RES MAX | AGI MAX | INT MAX | MAN MAX", inline=False)
            embed.add_field(
                name="Tesouro Imperial",
                value=f"**Ouro:** {player.get('ouro', 0)}\n**Prestígio:** {player.get('prestigio', 0)}\n**Aventuras:** {player.get('total_aventuras', 0)}",
                inline=False,
            )
            embed.set_footer(text="FASE 2 — Loop Principal • Registro canônico")
            await ctx.send(embed=embed)
            return

        classe_nome = CLASSES.get(player["classe"], {}).get("nome", player["classe"])
        embed = discord.Embed(title="GRIMÓRIO DO DESTINO", color=EMBED_COLOR)
        embed.add_field(
            name="Identidade",
            value=f"**Nome:** {ctx.author.display_name}\n**Classe:** {classe_nome}\n**Título:** {player['titulo']}",
            inline=False,
        )
        embed.add_field(
            name="Essência",
            value=f"FOR {player['forca']} | RES {player['resistencia']} | AGI {player['agilidade']} | INT {player['inteligencia']} | MAN {player['mana']}",
            inline=False,
        )
        embed.add_field(name="Caminho Escolhido", value=player["lore_texto"], inline=False)
        embed.add_field(name="Tendência de Crescimento", value=player["crescimento"], inline=False)
        embed.add_field(name="Presságio", value=player["pressagio"], inline=False)
        # ================= FASE 2 =================
        embed.add_field(
            name="Tesouro Imperial",
            value=f"**Ouro:** {player.get('ouro', 0)}\n**Prestígio:** {player.get('prestigio', 0)}\n**Aventuras:** {player.get('total_aventuras', 0)}",
            inline=False,
        )
        embed.set_footer(text="FASE 2 — Loop Principal • Registro canônico")
        await ctx.send(embed=embed)
    except Exception:
        logger.exception("Falha em !perfil")
        await ctx.send("O Grimório está em silêncio.")


@bot.command(name="resetar")
@commands.has_permissions(administrator=True)
async def resetar(ctx: commands.Context, membro: discord.Member) -> None:
    try:
        uid = str(membro.id)
        if not player_exists(uid):
            await ctx.send("Nenhum selo ativo encontrado.")
            return
        delete_player(uid)
        if uid == INKOSI_ID:
            await ctx.send("⚠️ Revogação do Registro Absoluto executada por decreto administrativo.")
        else:
            await ctx.send(f"Revogação do Registro executada para **{membro.display_name}**.")
    except Exception:
        logger.exception("Falha em !resetar")
        await ctx.send("O Grimório está em silêncio.")


@resetar.error
async def resetar_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Somente administradores podem decretar a Revogação do Registro.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Uso correto: `!resetar @membro`")
    else:
        logger.exception("Erro !resetar", exc_info=error)
        await ctx.send("O Grimório está em silêncio.")


@bot.command(name="eu")
async def eu(ctx: commands.Context) -> None:
    await ctx.send("Sou o Grimório de EBR: registro destinos, não promessas.")


# ================= FASE 2 =================
@bot.command(name="aventurar")
async def aventurar(ctx: commands.Context) -> None:
    try:
        user_id = str(ctx.author.id)
        player = create_inkosi_record_if_needed(user_id) if user_id == INKOSI_ID else get_player(user_id)
        if not player:
            await ctx.send("Teu nome ainda não foi selado. Invoque `!iniciar`.")
            return

        rem = get_cooldown_remaining(user_id)
        if rem > 0:
            embed = discord.Embed(
                title="RITO EM ESPERA",
                description=(
                    f"Teu próximo passo ritualístico abre em **{format_duration(rem)}**.\n"
                    "O mundo não apressa destino."
                ),
                color=EMBED_COLOR,
            )
            await ctx.send(embed=embed)
            return

        roll = random.random()
        if roll < 0.70:
            resultado = "sucesso comum"
            ouro, prestigio = 10, 1
            streak = int(player.get("streak_aventura", 0)) + 1
        elif roll < 0.90:
            resultado = "sucesso grande"
            ouro, prestigio = 25, 3
            streak = int(player.get("streak_aventura", 0)) + 1
        else:
            resultado = "falha"
            ouro, prestigio = 2, 0
            streak = 0

        ambiente = random.choice(FASE2_ENVIRONMENTS)
        classe_id = player.get("classe", "inkosi")
        flavor = FASE2_TEXTS.get(classe_id, FASE2_TEXTS["guerreiro"]).format(ambiente=ambiente)
        if user_id == INKOSI_ID:
            flavor = FASE2_TEXTS["inkosi"].format(ambiente=ambiente)

        now_iso = datetime.now(timezone.utc).isoformat()
        update_player_currency(user_id, ouro, prestigio)
        set_last_aventura(user_id, now_iso)
        increment_stats(user_id, streak=streak, total_inc=1)

        embed = discord.Embed(
            title="AVENTURA CONCLUÍDA",
            description=(
                f"**Resultado:** {resultado}\n"
                f"{flavor}\n"
                f"Recompensa: **+{ouro} ouro** | **+{prestigio} prestígio**"
            ),
            color=EMBED_COLOR,
        )
        embed.set_footer(text="FASE 2 — Loop Principal • O destino responde")
        await ctx.send(embed=embed)
    except Exception:
        logger.exception("Falha em !aventurar")
        await ctx.send("O Grimório está em silêncio.")


# ================= FASE 2 =================
@bot.command(name="status")
async def status(ctx: commands.Context) -> None:
    try:
        user_id = str(ctx.author.id)
        player = create_inkosi_record_if_needed(user_id) if user_id == INKOSI_ID else get_player(user_id)
        if not player:
            await ctx.send("Teu nome ainda não foi selado. Invoque `!iniciar`.")
            return

        embed = discord.Embed(title="STATUS IMPERIAL", color=EMBED_COLOR)
        embed.add_field(name="Ouro", value=str(player.get("ouro", 0)), inline=True)
        embed.add_field(name="Prestígio", value=str(player.get("prestigio", 0)), inline=True)
        embed.add_field(name="Total de Aventuras", value=str(player.get("total_aventuras", 0)), inline=False)
        embed.set_footer(text="FASE 2 — Loop Principal")
        await ctx.send(embed=embed)
    except Exception:
        logger.exception("Falha em !status")
        await ctx.send("O Grimório está em silêncio.")


@bot.command(name="changelog")
async def changelog(ctx: commands.Context) -> None:
    embed = discord.Embed(title="Changelog", color=EMBED_COLOR)
    embed.description = (
        "**FASE 1 — Núcleo do Jogador**\n"
        "Criação única, perfil canônico, reset admin e exceção Inkosi.\n\n"
        "**FASE 2 — Loop Principal**\n"
        "`!aventurar` com cooldown, RNG leve, ouro e prestígio persistentes.\n"
        "`!status` e expansão do `!perfil` com progresso econômico-social."
    )
    await ctx.send(embed=embed)


@bot.command(name="guia")
async def guia(ctx: commands.Context) -> None:
    embed = discord.Embed(
        title="Guia do Grimório — EBR",
        description="FASE 2 ativa: Loop Principal de aventura persistente.",
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="Comandos",
        value=(
            "`!iniciar`, `!perfil`, `!resetar @membro`, `!eu`, `!changelog`, `!guia`\n"
            "`!aventurar`, `!status`"
        ),
        inline=False,
    )
    embed.add_field(
        name="O que ainda NÃO existe",
        value="Sem combate completo, inventário, mercado, guildas, PvP, ranking, temporadas, crafting.",
        inline=False,
    )
    await ctx.send(embed=embed)


# ============================================================
# 8) EVENTOS
# ============================================================
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
