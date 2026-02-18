# ============================================================
# 1) IMPORTS
# ============================================================
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
# 3) CONSTANTES (INKOSI_ID, PATHS, ETC)
# ============================================================
INKOSI_ID = "1187734043236778027"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "players.db"

# Usa DISCORD_TOKEN por ambiente. Se não existir, use o fallback abaixo.
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_TOKEN_FALLBACK = "COLE_SEU_TOKEN_AQUI"

EMBED_COLOR = discord.Color.from_rgb(45, 18, 54)


# ============================================================
# 4) BANCO (SQLITE HELPERS)
# ============================================================
def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
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
        conn.commit()


def get_player(user_id: str) -> dict[str, Any] | None:
    with sqlite3.connect(DB_PATH) as conn:
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
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO players (
                user_id, classe, is_excecao, nivel, criado_em,
                forca, resistencia, agilidade, inteligencia, mana,
                crescimento, titulo, lore_texto, pressagio
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        conn.commit()


def delete_player(user_id: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM players WHERE user_id = ?", (user_id,))
        conn.commit()


def player_exists(user_id: str) -> bool:
    return get_player(user_id) is not None


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
# 5) DADOS CANÔNICOS (CLASSES, LORE_CLASSES)
# ============================================================
CLASSES: dict[str, dict[str, Any]] = {
    "guerreiro": {
        "nome": "Guerreiro",
        "icone": "⚔️",
        "frase": "Onde a noite avança, ele ergue o aço e dita fronteiras.",
        "descricao": "Guardião de muralhas e juramentos. Sua presença é sentença.",
        "atributos": {"FOR": "12", "RES": "10", "AGI": "6", "INT": "4", "MAN": "3"},
        "crescimento": "Cresce pelo rigor, tornando-se muralha viva diante do caos.",
        "titulo": "Sentinela do Trono Velado",
        "lore_texto": "Escolheu o aço para conter a ruína que ronda os salões do Império.",
        "pressagio": "Seu passo anuncia ordem; seu silêncio, juízo.",
    },
    "mago": {
        "nome": "Mago",
        "icone": "🜂",
        "frase": "Lê os ecos do invisível e escreve decretos no vazio.",
        "descricao": "Erudito arcano que dobra símbolos e desvela o interdito.",
        "atributos": {"FOR": "3", "RES": "5", "AGI": "6", "INT": "12", "MAN": "12"},
        "crescimento": "Cresce pela contemplação proibida, ampliando o alcance dos selos.",
        "titulo": "Arcanista da Coroa Obscura",
        "lore_texto": "Aceitou o fardo de traduzir o indizível para manter o Reino desperto.",
        "pressagio": "Onde ele fixa os olhos, o véu aprende a ceder.",
    },
    "cacador": {
        "nome": "Caçador",
        "icone": "🏹",
        "frase": "Não persegue presas; persegue destinos que tentam fugir.",
        "descricao": "Predador de sombras, paciente e inevitável.",
        "atributos": {"FOR": "8", "RES": "7", "AGI": "11", "INT": "6", "MAN": "4"},
        "crescimento": "Cresce na precisão ritual, tornando-se sentença antes do impacto.",
        "titulo": "Perseguidor dos Ecos",
        "lore_texto": "Jurou caçar aquilo que ameaça a memória dos antigos pactos.",
        "pressagio": "Quando a trilha some, é porque ele já chegou.",
    },
    "soldado": {
        "nome": "Soldado",
        "icone": "🛡️",
        "frase": "Marcha onde o medo manda recuar.",
        "descricao": "Braço disciplinado do Império, firme na linha e no dever.",
        "atributos": {"FOR": "9", "RES": "9", "AGI": "7", "INT": "6", "MAN": "3"},
        "crescimento": "Cresce pela disciplina de ferro, elevando-se da fileira ao comando.",
        "titulo": "Lâmina da Legião Eterna",
        "lore_texto": "Nasceu para obedecer ao estandarte e manter viva a vontade imperial.",
        "pressagio": "Onde seu estandarte fincar, a desordem se ajoelha.",
    },
    "explorador": {
        "nome": "Explorador",
        "icone": "🧭",
        "frase": "Abre caminhos onde o mapa termina e o mito começa.",
        "descricao": "Cartógrafo do desconhecido, mensageiro entre ruínas e auroras.",
        "atributos": {"FOR": "6", "RES": "7", "AGI": "10", "INT": "8", "MAN": "5"},
        "crescimento": "Cresce ao decifrar fronteiras perdidas, retornando com rotas impossíveis.",
        "titulo": "Arauto das Fronteiras Mortas",
        "lore_texto": "Foi marcado para atravessar neblinas e nomear o que ninguém ousou tocar.",
        "pressagio": "Quando ele retorna, o mundo já não é o mesmo.",
    },
}


# ============================================================
# 6) UI (CLASSEVIEW)
# ============================================================
class ClasseView(discord.ui.View):
    def __init__(self, author_id: int, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Apenas quem iniciou o ritual pode selar esta escolha.", ephemeral=True
            )
            return False
        return True

    async def escolher_classe(self, interaction: discord.Interaction, classe_id: str) -> None:
        try:
            if str(interaction.user.id) == INKOSI_ID:
                await interaction.response.send_message(
                    "A assinatura ABSOLUTA não pode ser replicada por escolha ritual.",
                    ephemeral=True,
                )
                return

            if player_exists(str(interaction.user.id)):
                await interaction.response.send_message(
                    "Teu destino já foi inscrito. O Grimório não aceita duplicatas.",
                    ephemeral=True,
                )
                return

            base = CLASSES[classe_id]
            attrs = base["atributos"]
            create_player(
                user_id=str(interaction.user.id),
                classe_id=classe_id,
                is_excecao=0,
                nivel="1",
                forca=attrs["FOR"],
                resistencia=attrs["RES"],
                agilidade=attrs["AGI"],
                inteligencia=attrs["INT"],
                mana=attrs["MAN"],
                crescimento=base["crescimento"],
                titulo=base["titulo"],
                lore_texto=base["lore_texto"],
                pressagio=base["pressagio"],
            )

            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True

            confirm = discord.Embed(
                title="RITUAL CONCLUÍDO",
                description=(
                    f"**{interaction.user.display_name}** foi inscrito no Grimório como "
                    f"**{base['nome']}**.\n"
                    "Que os corredores do EBR testemunhem o primeiro selo do teu destino."
                ),
                color=EMBED_COLOR,
            )
            confirm.set_footer(text="FASE 1 — Núcleo do Jogador • Juramento selado")

            await interaction.response.edit_message(view=self)
            await interaction.followup.send(embed=confirm)
        except Exception:
            logger.exception("Falha ao escolher classe")
            if interaction.response.is_done():
                await interaction.followup.send("O Grimório está em silêncio.", ephemeral=True)
            else:
                await interaction.response.send_message("O Grimório está em silêncio.", ephemeral=True)

    @discord.ui.button(label="Guerreiro", style=discord.ButtonStyle.danger)
    async def guerreiro_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.escolher_classe(interaction, "guerreiro")

    @discord.ui.button(label="Mago", style=discord.ButtonStyle.primary)
    async def mago_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.escolher_classe(interaction, "mago")

    @discord.ui.button(label="Caçador", style=discord.ButtonStyle.secondary)
    async def cacador_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.escolher_classe(interaction, "cacador")

    @discord.ui.button(label="Soldado", style=discord.ButtonStyle.success)
    async def soldado_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.escolher_classe(interaction, "soldado")

    @discord.ui.button(label="Explorador", style=discord.ButtonStyle.secondary)
    async def explorador_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.escolher_classe(interaction, "explorador")


# ============================================================
# 7) COMANDOS (!iniciar, !perfil, !resetar, !eu, !changelog, !guia)
# ============================================================
@bot.command(name="iniciar")
async def iniciar(ctx: commands.Context) -> None:
    try:
        user_id = str(ctx.author.id)

        if user_id == INKOSI_ID:
            create_inkosi_record_if_needed(user_id)
            embed = discord.Embed(
                title="REGISTRO IMPOSSÍVEL DETECTADO",
                description=(
                    "O Sistema tentou classificar a assinatura presente e falhou por inadequação.\n\n"
                    "Não há classe, não há rito, não há moldura que contenha este nome.\n"
                    "O Grimório reconhece somente: **ABSOLUTO**."
                ),
                color=discord.Color.dark_red(),
            )
            embed.add_field(
                name="Designação",
                value="Aquele que Não se Submete",
                inline=False,
            )
            embed.add_field(
                name="Classificação",
                value="Não Indexável",
                inline=False,
            )
            embed.set_footer(text="FASE 1 — Núcleo do Jogador • Exceção canônica")
            await ctx.send(embed=embed)
            return

        if player_exists(user_id):
            await ctx.send("Teu nome já repousa no Grimório. Usa `!perfil` para contemplar teu registro.")
            return

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

        for cid, data in CLASSES.items():
            embed.add_field(
                name=f"{data['icone']} {data['nome']}",
                value=data["frase"],
                inline=False,
            )

        embed.set_footer(text="FASE 1 — Núcleo do Jogador • O destino começa aqui")
        await ctx.send(embed=embed, view=ClasseView(author_id=ctx.author.id))
    except Exception:
        logger.exception("Falha no comando !iniciar")
        await ctx.send("O Grimório está em silêncio.")


@bot.command(name="perfil")
async def perfil(ctx: commands.Context) -> None:
    try:
        user_id = str(ctx.author.id)

        if user_id == INKOSI_ID:
            player = create_inkosi_record_if_needed(user_id)
        else:
            player = get_player(user_id)

        if not player:
            await ctx.send("Nenhum registro foi encontrado. Invoque `!iniciar` para despertar.")
            return

        if int(player.get("is_excecao", 0)) == 1:
            embed = discord.Embed(
                title="REGISTRO ABSOLUTO",
                description=(
                    "Os arquivos tentaram ordenar esta presença e foram reduzidos ao silêncio.\n"
                    "Não há catálogo para aquilo que antecede o catálogo."
                ),
                color=discord.Color.dark_red(),
            )
            embed.add_field(name="Designação", value="Aquele que Não se Submete", inline=False)
            embed.add_field(name="Classificação", value="Não Indexável", inline=False)
            embed.add_field(
                name="Essência",
                value="**FOR:** MAX | **RES:** MAX | **AGI:** MAX | **INT:** MAX | **MAN:** MAX",
                inline=False,
            )
            embed.add_field(
                name="Presságio",
                value="Quando seu nome ecoa, o próprio destino altera a postura.",
                inline=False,
            )
            embed.set_footer(text="FASE 1 — Núcleo do Jogador • Registro canônico")
            await ctx.send(embed=embed)
            return

        classe_id = player["classe"]
        classe_nome = CLASSES.get(classe_id, {}).get("nome", classe_id.title())

        embed = discord.Embed(
            title="GRIMÓRIO DO DESTINO",
            description="Os sinos internos do Sistema confirmam: teu nome foi preservado no Registro Histórico.",
            color=EMBED_COLOR,
        )
        embed.add_field(
            name="Identidade",
            value=(
                f"**Nome:** {ctx.author.display_name}\n"
                f"**Classe:** {classe_nome}\n"
                f"**Título:** {player['titulo']}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Essência",
            value=(
                f"**FOR:** {player['forca']} | **RES:** {player['resistencia']} | "
                f"**AGI:** {player['agilidade']} | **INT:** {player['inteligencia']} | **MAN:** {player['mana']}"
            ),
            inline=False,
        )
        embed.add_field(name="Caminho Escolhido", value=player["lore_texto"], inline=False)
        embed.add_field(name="Tendência de Crescimento", value=player["crescimento"], inline=False)
        embed.add_field(name="Presságio", value=player["pressagio"], inline=False)
        embed.set_footer(text="FASE 1 — Núcleo do Jogador • Registro canônico")

        await ctx.send(embed=embed)
    except Exception:
        logger.exception("Falha no comando !perfil")
        await ctx.send("O Grimório está em silêncio.")


@bot.command(name="resetar")
@commands.has_permissions(administrator=True)
async def resetar(ctx: commands.Context, membro: discord.Member) -> None:
    try:
        alvo_id = str(membro.id)
        existe = player_exists(alvo_id)

        if not existe:
            await ctx.send(f"Nenhum selo ativo foi encontrado para **{membro.display_name}**.")
            return

        delete_player(alvo_id)

        if alvo_id == INKOSI_ID:
            await ctx.send(
                "⚠️ **REVOGAÇÃO IMPOSSÍVEL, MAS EXECUTADA**\n"
                "Até mesmo o Registro Absoluto foi removido por decreto administrativo."
            )
            return

        await ctx.send(
            f"**Revogação do Registro**: o nome de **{membro.display_name}** foi apagado do Grimório."
        )
    except Exception:
        logger.exception("Falha no comando !resetar")
        await ctx.send("O Grimório está em silêncio.")


@resetar.error
async def resetar_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Somente administradores podem decretar a Revogação do Registro.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Uso correto: `!resetar @membro`")
    else:
        logger.exception("Erro não tratado em !resetar", exc_info=error)
        await ctx.send("O Grimório está em silêncio.")


@bot.command(name="eu")
async def eu(ctx: commands.Context) -> None:
    await ctx.send("Sou o Grimório de EBR: registro destinos, não promessas.")


@bot.command(name="changelog")
async def changelog(ctx: commands.Context) -> None:
    embed = discord.Embed(title="Changelog — Fase 1", color=EMBED_COLOR)
    embed.description = (
        "**Núcleo do Jogador**\n"
        "• Ritual de criação única de personagem (`!iniciar`)\n"
        "• Registro canônico persistente em SQLite (`!perfil`)\n"
        "• Revogação administrativa de registros (`!resetar`)\n"
        "• Comandos base de orientação (`!eu`, `!guia`)\n"
        "• Exceção absoluta para Lord Inkosi (não indexável)\n\n"
        "**Preparação para Fase 2 (não ativa):**\n"
        "Estrutura de dados pronta para expansão de progressão e narrativa futura."
    )
    embed.set_footer(text="FASE 1 — Núcleo do Jogador")
    await ctx.send(embed=embed)


@bot.command(name="guia")
async def guia(ctx: commands.Context) -> None:
    embed = discord.Embed(
        title="Guia do Grimório — EBR",
        description=(
            "A Fase 1 estabelece tua identidade canônica no Reino.\n"
            "Não há ainda missões, combate, exploração, economia ativa ou RNG."
        ),
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="Comandos Disponíveis",
        value=(
            "`!iniciar` — Ritual do Despertar e escolha única de classe\n"
            "`!perfil` — Exibe teu Registro Histórico\n"
            "`!resetar @membro` — Revogação administrativa\n"
            "`!eu` — Frase canônica do sistema\n"
            "`!changelog` — Resumo da fase atual\n"
            "`!guia` — Este painel"
        ),
        inline=False,
    )
    embed.add_field(
        name="Estado do Projeto",
        value="FASE 1 — Núcleo do Jogador ativo. FASE 2 apenas preparada na base.",
        inline=False,
    )
    embed.set_footer(text="FASE 1 — Núcleo do Jogador • Orientação oficial")
    await ctx.send(embed=embed)


# ============================================================
# 8) EVENTOS (on_ready)
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
        logger.exception("Falha ao iniciar banco SQLite")
        raise

    token = DISCORD_TOKEN if DISCORD_TOKEN else DISCORD_TOKEN_FALLBACK
    if not token or token == "COLE_SEU_TOKEN_AQUI":
        raise RuntimeError("Defina DISCORD_TOKEN no ambiente ou preencha DISCORD_TOKEN_FALLBACK.")

    bot.run(token)


if __name__ == "__main__":
    main()
