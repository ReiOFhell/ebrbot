from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass
from typing import Callable

from core.economy import (
    TRAIN_COOLDOWN_SECONDS,
    barracks_train_amount,
    building_upgrade_cost,
    building_upgrade_time_seconds,
    economy_snapshot,
    effective_collect_seconds,
    recalc_power,
    simulate_operation_success_chance,
)


@dataclass
class GameplayService:
    max_building_tier: int
    doctrines: set[str]
    get_or_create_domain: Callable[[str], sqlite3.Row]
    get_conn: Callable[[], sqlite3.Connection]
    update_player_state: Callable[..., None]
    get_slot_bonuses: Callable[[sqlite3.Connection, int | None, int | None], tuple[float, float]]
    has_strategist_gate: Callable[[sqlite3.Row, sqlite3.Connection], tuple[bool, str]]
    now_ts: Callable[[], int]
    resolve_discovery: Callable[[str, str, int], str]
    get_global_modifiers: Callable[[], dict[str, float]]

    @staticmethod
    def _who(user_id: str) -> str:
        return f"<@{user_id}>"

    def do_collect(self, user_id: str) -> str:
        who = self._who(user_id)
        d = self.get_or_create_domain(user_id)
        now = self.now_ts()
        elapsed = effective_collect_seconds(now - d["last_collect_ts"])

        snap = economy_snapshot(
            barn_level=d["barn_level"],
            barracks_level=d["barracks_level"],
            forge_level=d["forge_level"],
            troops=d["troops"],
        )

        modifiers = self.get_global_modifiers()
        eco_mult = max(0.5, 1.0 + float(modifiers.get("economy_pct", 0.0)))

        gross_gain = int(snap.production_per_hour * (elapsed / 3600) * eco_mult)
        maintenance_cost = int(snap.total_maintenance_per_hour * (elapsed / 3600))
        net_gain = gross_gain - maintenance_cost

        new_gold = max(0, d["gold"] + net_gain)
        self.update_player_state(
            user_id,
            gold=new_gold,
            last_collect_ts=now,
            accumulated_maintenance=d["accumulated_maintenance"] + max(0, maintenance_cost),
        )

        decree_line = ""
        if eco_mult != 1.0:
            decree_line = f"\nDecreto imperial ativo: economia x{eco_mult:.2f}"

        return (
            f"{who} ✅ Coleta concluída.\n"
            f"Δ Ouro bruto: +{gross_gain:,} | Manutenção: -{maintenance_cost:,} | Líquido: {net_gain:+,}\n"
            f"Próximo: clique em **Treinar** ou abra **Construções**{decree_line}"
        ).replace(",", ".")

    def do_train(self, user_id: str) -> str:
        who = self._who(user_id)
        d = self.get_or_create_domain(user_id)
        now = self.now_ts()
        delta = now - d["last_train_ts"]
        if delta < TRAIN_COOLDOWN_SECONDS:
            rest = TRAIN_COOLDOWN_SECONDS - delta
            return f"{who} ❌ Treino indisponível\nΔ Cooldown restante: {max(1, rest // 60)} min\nPróximo: aguarde e clique novamente"

        troops_gain = barracks_train_amount(d["barracks_level"])
        new_troops = d["troops"] + troops_gain
        with self.get_conn() as conn:
            g_bonus, s_bonus = self.get_slot_bonuses(conn, d["general_id"], d["strategist_id"])
        new_power = recalc_power(new_troops, d["barracks_level"], d["forge_level"], d["doctrine"], g_bonus, s_bonus)
        self.update_player_state(user_id, troops=new_troops, power=new_power, last_train_ts=now)

        return (
            f"{who} ✅ Treino concluído.\n"
            f"Δ Tropas: +{troops_gain:,} | Poder: {new_power:,}\n"
            "Próximo: clique em **Operações** ou **Rank**"
        ).replace(",", ".")

    def do_upgrade(self, user_id: str, estrutura: str) -> str:
        who = self._who(user_id)
        if estrutura not in {"celeiros", "casernas", "forja"}:
            return f"{who} ❌ Upgrade indisponível\nΔ Estrutura inválida\nPróximo: escolha celeiros, casernas ou forja"

        d = self.get_or_create_domain(user_id)
        level_key = {"celeiros": "barn_level", "casernas": "barracks_level", "forja": "forge_level"}[estrutura]
        level = d[level_key]
        if level >= self.max_building_tier:
            return f"{who} ❌ Upgrade indisponível\nΔ {estrutura.title()} já está no T{self.max_building_tier}\nPróximo: melhore outra construção"

        cost = building_upgrade_cost(level, estrutura)
        if d["gold"] < cost:
            falta = cost - d["gold"]
            return f"{who} ❌ Upgrade indisponível\nΔ Ouro insuficiente (falta {falta:,})\nPróximo: clique em **Resgatar**".replace(",", ".")

        new_level = level + 1
        params = {"gold": d["gold"] - cost, level_key: new_level}
        if estrutura in {"casernas", "forja"}:
            barracks_level = new_level if estrutura == "casernas" else d["barracks_level"]
            forge_level = new_level if estrutura == "forja" else d["forge_level"]
            with self.get_conn() as conn:
                g_bonus, s_bonus = self.get_slot_bonuses(conn, d["general_id"], d["strategist_id"])
            params["power"] = recalc_power(d["troops"], barracks_level, forge_level, d["doctrine"], g_bonus, s_bonus)

        self.update_player_state(user_id, **params)
        upgrade_secs = building_upgrade_time_seconds(new_level)
        return (
            f"{who} ✅ Upgrade concluído ({estrutura.title()} T{new_level})\n"
            f"Δ Ouro: -{cost:,} | Tempo ref: {upgrade_secs // 60} min\n"
            "Próximo: continue em Construções ou volte ao Domínio"
        ).replace(",", ".")

    def do_set_doctrine(self, user_id: str, doctrine: str) -> str:
        who = self._who(user_id)
        doctrine = doctrine.strip().lower()
        if doctrine not in self.doctrines:
            return f"{who} ❌ Doutrina inválida. Escolha: cerco, choque, furtivo ou arcano."

        d = self.get_or_create_domain(user_id)
        with self.get_conn() as conn:
            g_bonus, s_bonus = self.get_slot_bonuses(conn, d["general_id"], d["strategist_id"])
        new_power = recalc_power(d["troops"], d["barracks_level"], d["forge_level"], doctrine, g_bonus, s_bonus)
        self.update_player_state(user_id, doctrine=doctrine, power=new_power)
        return f"{who} ✅ Doutrina alterada para **{doctrine}**.\nΔ Poder: {new_power:,}\nPróximo: ajuste slots ou volte ao Domínio".replace(",", ".")

    def do_recruit_general_auto(self, user_id: str) -> str:
        who = self._who(user_id)
        return (
            f"{who} ✅ General canônico já está vinculado ao seu feudo.\n"
            "Δ Você evolui este mesmo General ao longo da progressão\n"
            "Próximo: fortaleça Casernas/Forja e avance em Operações"
        )

    def do_upgrade_general(self, user_id: str) -> str:
        who = self._who(user_id)
        d = self.get_or_create_domain(user_id)
        rank_order = ["C", "B", "A", "S", "SS"]
        rank_cost = {"C": 250_000, "B": 650_000, "A": 1_800_000, "S": 4_500_000}

        with self.get_conn() as conn:
            gid = d["general_id"]
            if not gid:
                return f"{who} ❌ General não encontrado no feudo."
            grow = conn.execute("SELECT id, rank FROM generals WHERE id = ? AND user_id = ?", (gid, user_id)).fetchone()
            if not grow:
                return f"{who} ❌ General não encontrado no feudo."

            current = str(grow["rank"] or "C")
            if current not in rank_order:
                current = "C"
            if current == "SS":
                return f"{who} ❌ General já alcançou o ápice (SS).\nPróximo: elevar tropas e forja para ampliar poder"

            cost = rank_cost[current]
            if d["gold"] < cost:
                falta = cost - d["gold"]
                return f"{who} ❌ Ouro insuficiente para evolução do General (falta {falta:,}).\nPróximo: clique em **Resgatar**".replace(",", ".")

            new_rank = rank_order[rank_order.index(current)+1]
            conn.execute("UPDATE generals SET rank = ? WHERE id = ?", (new_rank, gid))
            conn.commit()

            g_bonus, s_bonus = self.get_slot_bonuses(conn, gid, d["strategist_id"])

        new_power = recalc_power(d["troops"], d["barracks_level"], d["forge_level"], d["doctrine"], g_bonus, s_bonus)
        self.update_player_state(user_id, gold=d["gold"] - cost, power=new_power)
        return (
            f"{who} ✅ General evoluído: **{current} → {new_rank}**.\n"
            f"Δ Ouro: -{cost:,} | Poder: {new_power:,}\n"
            "Próximo: abra **Operações** para validar o novo patamar"
        ).replace(",", ".")

    def do_upgrade_strategist(self, user_id: str) -> str:
        who = self._who(user_id)
        d = self.get_or_create_domain(user_id)
        rank_order = ["C", "B", "A", "S", "SS"]
        rank_cost = {"C": 220_000, "B": 560_000, "A": 1_500_000, "S": 3_700_000}

        with self.get_conn() as conn:
            sid = d["strategist_id"]
            if not sid:
                return f"{who} ❌ Estrategista não encontrado no feudo."

            srow = conn.execute("SELECT id, rank FROM strategists WHERE id = ? AND user_id = ?", (sid, user_id)).fetchone()
            if not srow:
                return f"{who} ❌ Estrategista não encontrado no feudo."

            current = str(srow["rank"] or "C")
            if current not in rank_order:
                current = "C"
            if current == "SS":
                return f"{who} ❌ Estrategista já alcançou o ápice (SS).\nPróximo: evolua tropas/forja para ampliar poder"

            cost = rank_cost[current]
            if d["gold"] < cost:
                falta = cost - d["gold"]
                return f"{who} ❌ Ouro insuficiente para evolução do Estrategista (falta {falta:,}).\nPróximo: clique em **Resgatar**".replace(",", ".")

            new_rank = rank_order[rank_order.index(current) + 1]
            conn.execute("UPDATE strategists SET rank = ? WHERE id = ?", (new_rank, sid))
            conn.commit()

            g_bonus, s_bonus = self.get_slot_bonuses(conn, d["general_id"], sid)

        new_power = recalc_power(d["troops"], d["barracks_level"], d["forge_level"], d["doctrine"], g_bonus, s_bonus)
        self.update_player_state(user_id, gold=d["gold"] - cost, power=new_power)
        return (
            f"{who} ✅ Estrategista evoluído: **{current} → {new_rank}**.\n"
            f"Δ Ouro: -{cost:,} | Poder: {new_power:,}\n"
            "Próximo: abra **Operações** para testar a composição"
        ).replace(",", ".")

    def _normalize_operation_key(self, raw_key: str) -> str:
        key = raw_key.strip().lower()
        aliases = {
            "estrada_cinza": "estrada_cinzas",
            "estrada-das-cinzas": "estrada_cinzas",
            "ruinas_muralhas": "ruinas_muralha",
        }
        return aliases.get(key, key)

    def _operation_fields(self, op: sqlite3.Row) -> dict[str, object]:
        return {
            "key": op["key"],
            "title": op["title"],
            "min_barracks_level": int(op["min_barracks_level"] or 1),
            "min_barn_level": int(op["min_barn_level"] or 1),
            "min_forge_level": int(op["min_forge_level"] or 1),
            "min_feudo_tier": int(op["min_feudo_tier"] or 1),
            "requires_general": int(op["requires_general"] or 0),
            "requires_arcane_general": int(op["requires_arcane_general"] or 0),
            "requires_strategist": int(op["requires_strategist"] or 0),
            "partial_without_strategist": int(op["partial_without_strategist"] or 0),
            "required_doctrine": op["required_doctrine"],
            "required_legion_set_pieces": int(op["required_legion_set_pieces"] or 0),
            "min_troops": int(op["min_troops"] or 0),
            "difficulty_power": int(op["difficulty_power"] or 1000),
            "base_risk_percent": float(op["base_risk_percent"] or 0.1),
            "base_gold_reward": int(op["base_gold_reward"] or 0),
            "prestige_reward": int(op["prestige_reward"] or 0),
            "preferred_doctrine": op["preferred_doctrine"],
        }

    def _count_legion_set_pieces(self, conn: sqlite3.Connection, user_id: str) -> int:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT i.key) AS c
            FROM inventories inv
            JOIN items i ON i.id = inv.item_id
            WHERE inv.user_id = ?
              AND inv.quantity > 0
              AND i.key IN (
                'elmo_basalto',
                'lamina_juramento_quebrado',
                'insignia_setima_caravana',
                'selo_sal_nahr',
                'mascara_estrategista_cego'
              )
            """,
            (user_id,),
        ).fetchone()
        return int(row["c"] if row else 0)

    def _operation_gate(self, d: sqlite3.Row, opf: dict[str, object], conn: sqlite3.Connection) -> tuple[str | None, bool]:
        if d["barracks_level"] < opf["min_barracks_level"]:
            return f"Requisito ausente: Casernas T{opf['min_barracks_level']}+.", False
        if d["barn_level"] < opf["min_barn_level"]:
            return f"Requisito ausente: Celeiros T{opf['min_barn_level']}+.", False
        if d["forge_level"] < opf["min_forge_level"]:
            return f"Requisito ausente: Forja T{opf['min_forge_level']}+.", False

        feudo_tier = min(d["barn_level"], d["barracks_level"], d["forge_level"])
        if feudo_tier < opf["min_feudo_tier"]:
            return f"Requisito ausente: Feudo T{opf['min_feudo_tier']}+.", False
        if d["troops"] < opf["min_troops"]:
            return f"Requisito ausente: tropa mínima de {opf['min_troops']}.", False

        required_doctrine = opf["required_doctrine"]
        if required_doctrine and d["doctrine"] != required_doctrine:
            return f"Requisito ausente: Doutrina {required_doctrine}.", False

        if opf["requires_general"] and not d["general_id"]:
            return "Requisito ausente: General equipado para esta operação.", False
        if opf["requires_arcane_general"] and (not d["general_id"] or d["doctrine"] != "arcano"):
            return "Requisito ausente: General Arcano (general equipado + doutrina arcano).", False

        pieces_need = opf["required_legion_set_pieces"]
        if pieces_need > 0:
            pieces_have = self._count_legion_set_pieces(conn, d["user_id"])
            if pieces_have < pieces_need:
                return f"Requisito ausente: Set de Legião {pieces_need}/5 (atual {pieces_have}/5).", False

        if opf["requires_strategist"] and not d["strategist_id"]:
            if opf["partial_without_strategist"]:
                return None, True
            return "Requisito ausente: Estrategista equipado para esta operação.", False

        return None, False

    def get_operation_status(self, user_id: str, op_key: str) -> str:
        d = self.get_or_create_domain(user_id)
        with self.get_conn() as conn:
            op = conn.execute("SELECT * FROM operations WHERE key = ?", (op_key,)).fetchone()
            if not op:
                return "❌ indisponível"
            opf = self._operation_fields(op)
            blocker, partial = self._operation_gate(d, opf, conn)
        if blocker:
            return f"🔒 {blocker}"
        if partial:
            return "⚠️ sem estrategista: apenas rota parcial"
        return "✅ disponível"

    def do_operacao(self, user_id: str, key: str) -> str:
        who = self._who(user_id)
        d = self.get_or_create_domain(user_id)
        with self.get_conn() as conn:
            op_key = self._normalize_operation_key(key)
            op = conn.execute("SELECT * FROM operations WHERE key = ?", (op_key,)).fetchone()
            if not op:
                return f"{who} ❌ Operação inválida. Use: tumba_sultao, ruinas_muralha, poco_nomes, estrada_cinzas, fortim_sol_negro."

            opf = self._operation_fields(op)
            blocker, partial_route = self._operation_gate(d, opf, conn)
            if blocker:
                return f"{who} ❌ {blocker}"

            chance = simulate_operation_success_chance(d["power"], opf["difficulty_power"], d["doctrine"], opf["preferred_doctrine"])
            if partial_route:
                chance *= 0.55

            g_bonus, s_bonus = self.get_slot_bonuses(conn, d["general_id"], d["strategist_id"])

        outcome = "vitória tática" if random.random() <= chance else "falha tática"
        modifiers = self.get_global_modifiers()
        reward_mult_global = max(0.5, 1.0 + float(modifiers.get("operation_reward_pct", 0.0)))
        risk_mult_global = max(0.5, 1.0 + float(modifiers.get("operation_risk_pct", 0.0)))
        prestige_mult_global = max(0.5, 1.0 + float(modifiers.get("prestige_pct", 0.0)))

        risk_mult = 1.0
        reward_mult = 1.0
        prestige_mult = 1.0
        route_line = "Rota completa habilitada."
        if partial_route:
            risk_mult = 1.35
            reward_mult = 0.45
            prestige_mult = 0.35
            route_line = "Rota parcial: sem estrategista, retorno incompleto."

        troops_lost = int(max(1, d["troops"] * opf["base_risk_percent"] * (0.4 if outcome == "vitória tática" else 0.8) * risk_mult * risk_mult_global))
        troops_lost = min(int(d["troops"]), troops_lost)
        troops_after = max(0, int(d["troops"]) - troops_lost)

        base_gold_delta = int(opf["base_gold_reward"] * (1.0 if outcome == "vitória tática" else 0.2) * reward_mult * reward_mult_global)
        prestige_gain = int(opf["prestige_reward"] * (1.0 if outcome == "vitória tática" else 0.4) * prestige_mult * prestige_mult_global)
        forge_mult = 1.0 + (d["forge_level"] - 1) * 0.03
        gold_delta = int(base_gold_delta * forge_mult)
        gold_after = max(0, int(d["gold"]) + gold_delta)

        new_power = recalc_power(troops_after, d["barracks_level"], d["forge_level"], d["doctrine"], g_bonus, s_bonus)
        ts = self.now_ts()
        with self.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO season_scores (season_number, user_id, prestige, wealth_snapshot, power_snapshot, updated_at_ts)
                VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT(season_number, user_id) DO UPDATE SET
                    prestige = prestige + excluded.prestige,
                    wealth_snapshot = excluded.wealth_snapshot,
                    power_snapshot = excluded.power_snapshot,
                    updated_at_ts = excluded.updated_at_ts
                """,
                (user_id, prestige_gain, gold_after, new_power, ts),
            )
            conn.execute(
                """
                INSERT INTO operation_runs (
                    user_id, operation_id, outcome, route_mode, success_chance,
                    troops_lost, gold_delta, prestige_gain, power_before, power_after, created_at_ts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    op["id"],
                    outcome,
                    "partial" if partial_route else "full",
                    round(chance, 6),
                    troops_lost,
                    gold_delta,
                    prestige_gain,
                    int(d["power"]),
                    int(new_power),
                    ts,
                ),
            )
            conn.commit()

        self.update_player_state(user_id, troops=troops_after, gold=gold_after, power=new_power)
        relic_line = self.resolve_discovery(user_id, f"operacao:{op['key']}", d["forge_level"])

        decree_line = ""
        if reward_mult_global != 1.0 or risk_mult_global != 1.0 or prestige_mult_global != 1.0:
            decree_line = (
                f"\nDecreto ativo: recompensa x{reward_mult_global:.2f} | risco x{risk_mult_global:.2f} | prestígio x{prestige_mult_global:.2f}"
            )

        return (
            f"{who} ⚔️ Operação `{op['title']}`\n"
            f"{route_line}\n"
            f"Poder aplicado: {d['power']:,} → {new_power:,} | Dificuldade: {opf['difficulty_power']:,}\n"
            f"Resultado: **{outcome}**\n"
            f"Impacto real: -{troops_lost:,} tropas | +{gold_delta:,} ouro | prestígio +{prestige_gain:,}\n"
            f"Saldo pós-operação: tropas {troops_after:,} | ouro {gold_after:,}\n"
            f"{relic_line}\n"
            f"Próximo: reforce tropas/composição e execute nova operação{decree_line}"
        ).replace(",", ".")

    # Compatibilidade com aliases e integrações antigas.
    def do_simular_operacao(self, user_id: str, key: str) -> str:
        return self.do_operacao(user_id, key)
