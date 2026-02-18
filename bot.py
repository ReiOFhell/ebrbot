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
# 3) CONSTANTES (INKOSI_ID, PATHS, TOKENS)
# ============================================================
INKOSI_ID = "1187734043236778027"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "players.db"

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_TOKEN_FALLBACK = "COLE_SEU_TOKEN_AQUI"

EMBED_COLOR = discord.Color.from_rgb(45, 18, 54)
ERROR_TEXT = "O Grimório está em silêncio."


def resolve_token() -> str:
    token_env = (DISCORD_TOKEN or "").strip().strip('"').strip("'")
    token_fallback = (DISCORD_TOKEN_FALLBACK or "").strip().strip('"').strip("'")

    token = token_env if token_env else token_fallback
    if not token or token == "COLE_SEU_TOKEN_AQUI":
        raise RuntimeError(
            "Token ausente. Defina DISCORD_TOKEN no ambiente ou preencha DISCORD_TOKEN_FALLBACK com um token válido."
        )

    if token.count(".") < 2:
        raise RuntimeError(
            "Token Discord parece inválido (formato inesperado). Verifique se há espaços, aspas extras ou token incorreto."
        )

    return token


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
        conn.execute("DELETE FROM annals WHERE user_id = ?", (user_id,))
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


def add_annal_entry(user_id: str, entrada: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO annals (user_id, entrada, criado_em) VALUES (?, ?, ?)",
            (user_id, entrada, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def get_annals(user_id: str, limit: int = 5) -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT entrada, criado_em FROM annals WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_player_counts_by_class() -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT classe, COUNT(*) AS total FROM players GROUP BY classe ORDER BY total DESC"
        ).fetchall()
        return [dict(r) for r in rows]


# ============================================================
# 5) DADOS CANÔNICOS (CLASSES, LORE, CRÔNICA)
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

WORLD_CHRONICLE = [
    (
        "I — O Pacto de Ônix",
        "Antes dos calendários, sete casas juraram sangue e silêncio para erguer EBR sobre ruínas consagradas.",
    ),
    (
        "II — A Noite dos Arquivos",
        "O Grimório nasceu quando a memória humana falhou. Desde então, destino é escritura, não opinião.",
    ),
    (
        "III — A Fenda Velada",
        "Ao norte, o céu rasgou-se em vidro negro. De lá ecoam nomes sem boca e promessas sem dono.",
    ),
    (
        "IV — O Trono Sem Rostro",
        "Diz-se que a Coroa governa, mas ninguém recorda o rosto do primeiro soberano desde a Última Vigília.",
    ),
]

FACTIONS = {
    "ordem-vigilia": {
        "titulo": "Ordem da Vigília Rubra",
        "resumo": "Guarda noturna dos portões internos, juramentada a impedir que o caos atravesse o mármore imperial.",
        "dogma": "Vigiar é amar o Império mais do que o próprio descanso.",
    },
    "conclave-obsidiano": {
        "titulo": "Conclave Obsidiano",
        "resumo": "Magistrados arcanos que interpretam presságios e codificam o interdito.",
        "dogma": "Toda magia deve uma dívida ao silêncio.",
    },
    "legiao-cinzenta": {
        "titulo": "Legião Cinzenta",
        "resumo": "Força militar imperial enviada aos limites da cartografia para conter insurgências e anomalias.",
        "dogma": "A fronteira existe onde a Legião decide permanecer.",
    },
    "cartografos-fenda": {
        "titulo": "Cartógrafos da Fenda",
        "resumo": "Exploradores e escribas de campo que desenham mapas de zonas mutáveis e locais proibidos.",
        "dogma": "Nomear é dominar, registrar é sobreviver.",
    },
}

REGIONS = [
    "**Palácio de Basalto** — centro político e ritual do EBR.",
    "**Bastião da Vigília** — fortaleza da guarda imperial noturna.",
    "**Jardins da Cinza Branca** — memorial dos juramentos quebrados.",
    "**Fenda de Vesper** — anomalia celeste e berço de horrores sem forma.",
    "**Estrada dos Sinos Mudos** — rota onde nenhum mensageiro fala após o pôr do sol.",
]

PHASE_2_FOUNDATIONS = [
    "Tabela `players` já contém campos narrativos e progressão textual (`nivel`, `crescimento`, `pressagio`).",
    "Tabela `annals` permite histórico pessoal persistente para futuras campanhas e arcos de personagem.",
    "Funções de agregação por classe prontas para eventos de facção e guerra narrativa.",
]


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
            user_id = str(interaction.user.id)
            if user_id == INKOSI_ID:
                await interaction.response.send_message(
                    "A assinatura ABSOLUTA não pode ser replicada por escolha ritual.",
                    ephemeral=True,
                )
                return

            if player_exists(user_id):
                await interaction.response.send_message(
                    "Teu destino já foi inscrito. O Grimório não aceita duplicatas.",
                    ephemeral=True,
                )
                return

            base = CLASSES[classe_id]
            attrs = base["atributos"]
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
                crescimento=base["crescimento"],
                titulo=base["titulo"],
                lore_texto=base["lore_texto"],
                pressagio=base["pressagio"],
            )

            add_annal_entry(
                user_id,
                f"Ritual do Despertar concluído. Caminho selado: {base['nome']}.",
            )

            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True

            confirm = discord.Embed(
                title="RITUAL CONCLUÍDO",
                description=(
                    f"**{interaction.user.display_name}** foi inscrito no Grimório como **{base['nome']}**.\n"
                    "Que os corredores do EBR testemunhem o primeiro selo do teu destino."
                ),
                color=EMBED_COLOR,
            )
            confirm.add_field(name="Título", value=base["titulo"], inline=False)
            confirm.set_footer(text="FASE 1 — Núcleo do Jogador • Juramento selado")

            await interaction.response.edit_message(view=self)
            await interaction.followup.send(embed=confirm)
        except Exception:
            logger.exception("Falha ao escolher classe")
            if interaction.response.is_done():
                await interaction.followup.send(ERROR_TEXT, ephemeral=True)
            else:
                await interaction.response.send_message(ERROR_TEXT, ephemeral=True)

    @discord.ui.button(label="Guerreiro", style=discord.ButtonStyle.danger)
    async def guerreiro_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        del button
        await self.escolher_classe(interaction, "guerreiro")

    @discord.ui.button(label="Mago", style=discord.ButtonStyle.primary)
    async def mago_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        del button
        await self.escolher_classe(interaction, "mago")

    @discord.ui.button(label="Caçador", style=discord.ButtonStyle.secondary)
    async def cacador_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        del button
        await self.escolher_classe(interaction, "cacador")

    @discord.ui.button(label="Soldado", style=discord.ButtonStyle.success)
    async def soldado_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        del button
        await self.escolher_classe(interaction, "soldado")

    @discord.ui.button(label="Explorador", style=discord.ButtonStyle.secondary)
    async def explorador_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        del button
        await self.escolher_classe(interaction, "explorador")


# ============================================================
# 7) COMANDOS PRINCIPAIS E NOVOS COMANDOS DE LORE
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
            embed.add_field(name="Designação", value="Aquele que Não se Submete", inline=False)
            embed.add_field(name="Classificação", value="Não Indexável", inline=False)
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

        for data in CLASSES.values():
            embed.add_field(name=f"{data['icone']} {data['nome']}", value=data["frase"], inline=False)

        embed.set_footer(text="FASE 1 — Núcleo do Jogador • O destino começa aqui")
        await ctx.send(embed=embed, view=ClasseView(author_id=ctx.author.id))
    except Exception:
        logger.exception("Falha no comando !iniciar")
        await ctx.send(ERROR_TEXT)


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
                f"**Título:** {player['titulo']}\n"
                f"**Nível Ritual:** {player['nivel']}"
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
        await ctx.send(ERROR_TEXT)


@bot.command(name="resetar")
@commands.has_permissions(administrator=True)
async def resetar(ctx: commands.Context, membro: discord.Member) -> None:
    try:
        alvo_id = str(membro.id)

        if not player_exists(alvo_id):
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
        await ctx.send(ERROR_TEXT)


@resetar.error
async def resetar_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Somente administradores podem decretar a Revogação do Registro.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Uso correto: `!resetar @membro`")
    else:
        logger.exception("Erro não tratado em !resetar", exc_info=error)
        await ctx.send(ERROR_TEXT)


@bot.command(name="eu")
async def eu(ctx: commands.Context) -> None:
    await ctx.send("Sou o Grimório de EBR: registro destinos, não promessas.")


@bot.command(name="changelog")
async def changelog(ctx: commands.Context) -> None:
    embed = discord.Embed(title="Changelog — Núcleo Expandido", color=EMBED_COLOR)
    embed.description = (
        "**Base Fase 1**\n"
        "• Criação única de personagem (`!iniciar`)\n"
        "• Registro canônico persistente (`!perfil`)\n"
        "• Revogação administrativa (`!resetar`)\n"
        "• Exceção absoluta para Lord Inkosi\n\n"
        "**Expansões de lore e mundo**\n"
        "• Crônica oficial (`!cronica`)\n"
        "• Facções canônicas (`!faccoes`, `!faccao`)\n"
        "• Mapa textual de regiões (`!mapaebr`)\n"
        "• Enciclopédia de classes (`!classeinfo`)\n"
        "• Diário persistente (`!diario`, `!anais`)\n"
        "• Relatório administrativo (`!relatorio`)"
    )
    embed.set_footer(text="EBR • Grimório de Destinos")
    await ctx.send(embed=embed)


@bot.command(name="guia")
async def guia(ctx: commands.Context) -> None:
    embed = discord.Embed(
        title="Guia do Grimório — EBR",
        description="Sistema social-RPG com foco narrativo, identidade persistente e lore imperial/dark.",
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="Comandos de Identidade",
        value=(
            "`!iniciar` • `!perfil` • `!resetar @membro`\n"
            "`!eu` • `!changelog` • `!guia`"
        ),
        inline=False,
    )
    embed.add_field(
        name="Comandos de Lore",
        value=(
            "`!prologo` • `!cronica` • `!lore`\n"
            "`!faccoes` • `!faccao <id>` • `!mapaebr` • `!classeinfo <classe>`"
        ),
        inline=False,
    )
    embed.add_field(
        name="Comandos de Registro Pessoal",
        value=(
            "`!diario <texto>` — grava entrada no teu histórico\n"
            "`!anais [@membro]` — exibe últimas entradas\n"
            "`!relatorio` (admin) — visão geral do Grimório"
        ),
        inline=False,
    )
    embed.add_field(
        name="Linha Criativa",
        value="Narrativa robusta, tom ritualístico e evolução pronta para campanhas da Fase 2.",
        inline=False,
    )
    embed.set_footer(text="EBR • Orientação oficial")
    await ctx.send(embed=embed)


@bot.command(name="prologo")
async def prologo(ctx: commands.Context) -> None:
    embed = discord.Embed(
        title="PRÓLOGO — ETERNAL BRAZILIAN ROYAL",
        description=(
            "Quando o mundo comum se partiu, EBR ergueu colunas de basalto sobre a própria memória.\n"
            "Aqui, nomes são selos; promessas, moedas; silêncio, lei.\n"
            "Tu não nasceste para assistir ao destino — nasceste para ser inscrito nele."
        ),
        color=EMBED_COLOR,
    )
    embed.set_footer(text="EBR • O mundo recorda os que juram")
    await ctx.send(embed=embed)


@bot.command(name="cronica")
async def cronica(ctx: commands.Context) -> None:
    embed = discord.Embed(title="CRÔNICA IMPERIAL", color=EMBED_COLOR)
    for capitulo, texto in WORLD_CHRONICLE:
        embed.add_field(name=capitulo, value=texto, inline=False)
    embed.set_footer(text="EBR • Arquivo canônico do mundo")
    await ctx.send(embed=embed)


@bot.command(name="lore")
async def lore(ctx: commands.Context) -> None:
    await cronica(ctx)


@bot.command(name="faccoes")
async def faccoes(ctx: commands.Context) -> None:
    embed = discord.Embed(
        title="FACÇÕES CANÔNICAS",
        description="Cada facção sustenta uma parte do equilíbrio imperial.",
        color=EMBED_COLOR,
    )
    for fid, data in FACTIONS.items():
        embed.add_field(name=f"{data['titulo']} (`{fid}`)", value=data["resumo"], inline=False)
    embed.set_footer(text="Use !faccao <id> para detalhes")
    await ctx.send(embed=embed)


@bot.command(name="faccao")
async def faccao(ctx: commands.Context, *, faccao_id: str | None = None) -> None:
    if not faccao_id:
        await ctx.send("Uso: `!faccao <id>` • Exemplo: `!faccao ordem-vigilia`")
        return

    key = faccao_id.strip().lower()
    data = FACTIONS.get(key)
    if not data:
        await ctx.send("Facção não encontrada. Use `!faccoes` para listar IDs válidos.")
        return

    embed = discord.Embed(title=data["titulo"], description=data["resumo"], color=EMBED_COLOR)
    embed.add_field(name="Dogma", value=data["dogma"], inline=False)
    embed.set_footer(text="EBR • Dossiê de Facção")
    await ctx.send(embed=embed)


@bot.command(name="mapaebr")
async def mapaebr(ctx: commands.Context) -> None:
    embed = discord.Embed(
        title="MAPA TEXTUAL DO EBR",
        description="Regiões de relevância canônica para futuras campanhas.",
        color=EMBED_COLOR,
    )
    for local in REGIONS:
        embed.add_field(name="Região", value=local, inline=False)
    embed.set_footer(text="EBR • Cartografia ritual")
    await ctx.send(embed=embed)


@bot.command(name="classeinfo")
async def classeinfo(ctx: commands.Context, *, classe_id: str | None = None) -> None:
    if not classe_id:
        await ctx.send("Uso: `!classeinfo <guerreiro|mago|cacador|soldado|explorador>`")
        return

    cid = classe_id.strip().lower()
    data = CLASSES.get(cid)
    if not data:
        await ctx.send("Classe inválida. Opções: guerreiro, mago, cacador, soldado, explorador.")
        return

    attrs = data["atributos"]
    embed = discord.Embed(
        title=f"{data['icone']} {data['nome']}",
        description=data["descricao"],
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="Essência Inicial",
        value=(
            f"**FOR:** {attrs['FOR']} | **RES:** {attrs['RES']} | **AGI:** {attrs['AGI']} | "
            f"**INT:** {attrs['INT']} | **MAN:** {attrs['MAN']}"
        ),
        inline=False,
    )
    embed.add_field(name="Título", value=data["titulo"], inline=False)
    embed.add_field(name="Caminho", value=data["lore_texto"], inline=False)
    embed.add_field(name="Crescimento", value=data["crescimento"], inline=False)
    embed.add_field(name="Presságio", value=data["pressagio"], inline=False)
    embed.set_footer(text="EBR • Enciclopédia de Classes")
    await ctx.send(embed=embed)


@bot.command(name="diario")
async def diario(ctx: commands.Context, *, texto: str | None = None) -> None:
    try:
        user_id = str(ctx.author.id)
        if not texto:
            await ctx.send("Uso: `!diario <texto>`")
            return

        if len(texto) > 500:
            await ctx.send("Tua entrada excede 500 caracteres. Seja preciso no juramento.")
            return

        if not player_exists(user_id) and user_id != INKOSI_ID:
            await ctx.send("Primeiro sela tua identidade em `!iniciar` para escrever nos Anais.")
            return

        if user_id == INKOSI_ID:
            create_inkosi_record_if_needed(user_id)

        add_annal_entry(user_id, texto)
        await ctx.send("Entrada gravada nos Anais. O Grimório testemunhou tuas palavras.")
    except Exception:
        logger.exception("Falha no comando !diario")
        await ctx.send(ERROR_TEXT)


@bot.command(name="anais")
async def anais(ctx: commands.Context, membro: discord.Member | None = None) -> None:
    try:
        alvo = membro or ctx.author
        user_id = str(alvo.id)

        if not player_exists(user_id) and user_id != INKOSI_ID:
            await ctx.send("Este nome não possui registro no Grimório.")
            return

        entries = get_annals(user_id, limit=5)
        if not entries:
            await ctx.send("Nenhuma entrada foi gravada nos Anais deste nome.")
            return

        embed = discord.Embed(
            title=f"ANAIS DE {alvo.display_name.upper()}",
            description="Últimas 5 entradas do registro pessoal.",
            color=EMBED_COLOR,
        )
        for idx, item in enumerate(entries, start=1):
            embed.add_field(
                name=f"Entrada {idx} • {item['criado_em'][:19].replace('T', ' ')} UTC",
                value=item["entrada"],
                inline=False,
            )
        embed.set_footer(text="EBR • Memória persistente")
        await ctx.send(embed=embed)
    except Exception:
        logger.exception("Falha no comando !anais")
        await ctx.send(ERROR_TEXT)


@bot.command(name="relatorio")
@commands.has_permissions(administrator=True)
async def relatorio(ctx: commands.Context) -> None:
    try:
        data = get_player_counts_by_class()
        total = sum(int(item["total"]) for item in data)

        embed = discord.Embed(
            title="RELATÓRIO DO GRIMÓRIO",
            description="Painel administrativo de registros canônicos.",
            color=EMBED_COLOR,
        )

        if not data:
            embed.add_field(name="Registros", value="Nenhum personagem inscrito.", inline=False)
        else:
            linhas = [f"• **{item['classe']}**: {item['total']}" for item in data]
            embed.add_field(name="Distribuição por Classe", value="\n".join(linhas), inline=False)

        embed.add_field(name="Total de Registros", value=str(total), inline=False)
        embed.add_field(name="Base para Fase 2", value="\n".join(PHASE_2_FOUNDATIONS), inline=False)
        embed.set_footer(text="EBR • Uso administrativo")
        await ctx.send(embed=embed)
    except Exception:
        logger.exception("Falha no comando !relatorio")
        await ctx.send(ERROR_TEXT)


@relatorio.error
async def relatorio_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Somente administradores podem invocar `!relatorio`.")
    else:
        logger.exception("Erro não tratado em !relatorio", exc_info=error)
        await ctx.send(ERROR_TEXT)


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

    try:
        token = resolve_token()
    except RuntimeError as exc:
        logger.error("Inicialização abortada: %s", exc)
        raise SystemExit(1) from exc

    try:
        bot.run(token)
    except discord.LoginFailure:
        logger.error(
            "Falha de autenticação Discord (401 Unauthorized). Corrija DISCORD_TOKEN e reinicie o bot."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
