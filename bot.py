# ============================================================
# 1) IMPORTS
# ============================================================
import hashlib
import logging
import os
import sqlite3
from datetime import datetime, timezone
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
        await ctx.send(embed=embed, view=ClasseView(author_id=ctx.author.id))
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
        embed = discord.Embed(title="GRIMÓRIO DO DESTINO", description=canon_line("abertura"), color=EMBED_COLOR)
        embed.add_field(name="Identidade", value=f"**Nome:** {ctx.author.display_name}\n**Classe:** {classe_nome}\n**Título:** {player['titulo']}", inline=False)
        embed.add_field(name="Essência", value=f"**FOR:** {player['forca']} | **RES:** {player['resistencia']} | **AGI:** {player['agilidade']} | **INT:** {player['inteligencia']} | **MAN:** {player['mana']}", inline=False)
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
    embed.description = (
        "**Etapa 0 — Fundação técnica e padrão canônico**\n"
        "• Observabilidade com Selo de Falha persistente\n"
        "• Migração segura do SQLite sem alterar experiência\n"
        "• Voz ritualística padronizada (abertura/sucesso/recusa)"
    )
    embed.set_footer(text="EBR • Base estável")
    await ctx.send(embed=embed)


@bot.command(name="guia")
async def guia(ctx: commands.Context) -> None:
    embed = discord.Embed(
        title="Guia do Grimório — EBR",
        description="Fase estável ativa: identidade canônica e registros persistentes.",
        color=EMBED_COLOR,
    )
    embed.add_field(name="Comandos", value="`!iniciar` • `!classe` • `!perfil` • `!resetar @membro` • `!eu` • `!changelog` • `!guia`", inline=False)
    embed.add_field(name="Estado Atual", value="Etapa 0: fundação técnica e padrão canônico. Sem novos loops de gameplay/social.", inline=False)
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
