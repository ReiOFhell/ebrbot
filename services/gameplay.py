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

    def do_collect(self, user_id: str) -> str:
        d = self.get_or_create_domain(user_id)
        now = self.now_ts()
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

        new_gold = max(0, d["gold"] + net_gain)
        self.update_player_state(
            user_id,
            gold=new_gold,
            last_collect_ts=now,
            accumulated_maintenance=d["accumulated_maintenance"] + max(0, maintenance_cost),
        )

        return (
            "✅ Coleta concluída.\n"
            f"Δ Ouro bruto: +{gross_gain:,} | Manutenção: -{maintenance_cost:,} | Líquido: {net_gain:+,}\n"
            "Próximo: clique em **Treinar** ou abra **Construções**"
        ).replace(",", ".")

    def do_train(self, user_id: str) -> str:
        d = self.get_or_create_domain(user_id)
        now = self.now_ts()
        delta = now - d["last_train_ts"]
        if delta < TRAIN_COOLDOWN_SECONDS:
            rest = TRAIN_COOLDOWN_SECONDS - delta
            return f"❌ Treino indisponível\nΔ Cooldown restante: {max(1, rest // 60)} min\nPróximo: aguarde e clique novamente"

        troops_gain = barracks_train_amount(d["barracks_level"])
        new_troops = d["troops"] + troops_gain
        with self.get_conn() as conn:
            g_bonus, s_bonus = self.get_slot_bonuses(conn, d["general_id"], d["strategist_id"])
        new_power = recalc_power(new_troops, d["barracks_level"], d["forge_level"], d["doctrine"], g_bonus, s_bonus)
        self.update_player_state(user_id, troops=new_troops, power=new_power, last_train_ts=now)

        return (
            "✅ Treino concluído.\n"
            f"Δ Tropas: +{troops_gain:,} | Poder: {new_power:,}\n"
            "Próximo: clique em **Operações** ou **Rank**"
        ).replace(",", ".")

    def do_upgrade(self, user_id: str, estrutura: str) -> str:
        if estrutura not in {"celeiros", "casernas", "forja"}:
            return "❌ Upgrade indisponível\nΔ Estrutura inválida\nPróximo: escolha celeiros, casernas ou forja"

        d = self.get_or_create_domain(user_id)
        level_key = {"celeiros": "barn_level", "casernas": "barracks_level", "forja": "forge_level"}[estrutura]
        level = d[level_key]
        if level >= self.max_building_tier:
            return f"❌ Upgrade indisponível\nΔ {estrutura.title()} já está no T{self.max_building_tier}\nPróximo: melhore outra construção"

        cost = building_upgrade_cost(level, estrutura)
        if d["gold"] < cost:
            falta = cost - d["gold"]
            return f"❌ Upgrade indisponível\nΔ Ouro insuficiente (falta {falta:,})\nPróximo: clique em **Resgatar**".replace(",", ".")

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
            f"✅ Upgrade concluído ({estrutura.title()} T{new_level})\n"
            f"Δ Ouro: -{cost:,} | Tempo ref: {upgrade_secs // 60} min\n"
            "Próximo: continue em Construções ou volte ao Domínio"
        ).replace(",", ".")

    def do_set_doctrine(self, user_id: str, doctrine: str) -> str:
        doctrine = doctrine.strip().lower()
        if doctrine not in self.doctrines:
            return "❌ Doutrina inválida. Escolha: cerco, choque, furtivo ou arcano."

        d = self.get_or_create_domain(user_id)
        with self.get_conn() as conn:
            g_bonus, s_bonus = self.get_slot_bonuses(conn, d["general_id"], d["strategist_id"])
        new_power = recalc_power(d["troops"], d["barracks_level"], d["forge_level"], doctrine, g_bonus, s_bonus)
        self.update_player_state(user_id, doctrine=doctrine, power=new_power)
        return f"✅ Doutrina alterada para **{doctrine}**.\nΔ Poder: {new_power:,}\nPróximo: ajuste slots ou volte ao Domínio".replace(",", ".")

    def do_recruit_general_auto(self, user_id: str) -> str:
        with self.get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) c FROM generals WHERE user_id = ?", (user_id,)).fetchone()["c"]
            name = f"General #{count + 1}"
            conn.execute(
                "INSERT INTO generals (user_id, name, rank, equipped, created_at_ts) VALUES (?, ?, 'C', 0, ?)",
                (user_id, name, self.now_ts()),
            )
            gid = conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]
            conn.commit()
        return f"✅ General recrutado: **{name}** (id {gid}).\nΔ Slot disponível para equipar\nPróximo: selecione o general no painel".replace(",", ".")

    def do_equip_general(self, user_id: str, general_id: int) -> str:
        d = self.get_or_create_domain(user_id)
        with self.get_conn() as conn:
            g = conn.execute("SELECT id FROM generals WHERE id = ? AND user_id = ?", (general_id, user_id)).fetchone()
            if not g:
                return "❌ General não encontrado para este jogador."
            conn.execute("UPDATE generals SET equipped = 0 WHERE user_id = ?", (user_id,))
            conn.execute("UPDATE generals SET equipped = 1 WHERE id = ?", (general_id,))
            conn.commit()
            g_bonus, s_bonus = self.get_slot_bonuses(conn, general_id, d["strategist_id"])
        new_power = recalc_power(d["troops"], d["barracks_level"], d["forge_level"], d["doctrine"], g_bonus, s_bonus)
        self.update_player_state(user_id, general_id=general_id, power=new_power)
        return f"✅ General equipado (id {general_id}).\nΔ Poder: {new_power:,}\nPróximo: validar composição em Operações".replace(",", ".")

    def do_recruit_strategist_auto(self, user_id: str) -> str:
        d = self.get_or_create_domain(user_id)
        with self.get_conn() as conn:
            ok, msg = self.has_strategist_gate(d, conn)
            if not ok:
                return f"❌ {msg}"
            count = conn.execute("SELECT COUNT(*) c FROM strategists WHERE user_id = ?", (user_id,)).fetchone()["c"]
            name = f"Estrategista #{count + 1}"
            conn.execute(
                "INSERT INTO strategists (user_id, name, rank, equipped, created_at_ts) VALUES (?, ?, 'C', 0, ?)",
                (user_id, name, self.now_ts()),
            )
            sid = conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]
            conn.commit()
        return f"✅ Estrategista recrutado: **{name}** (id {sid}).\nΔ Slot de especialista disponível\nPróximo: selecione o estrategista no painel".replace(",", ".")

    def do_equip_strategist(self, user_id: str, strategist_id: int) -> str:
        d = self.get_or_create_domain(user_id)
        with self.get_conn() as conn:
            ok, msg = self.has_strategist_gate(d, conn)
            if not ok:
                return f"❌ {msg}"
            srow = conn.execute("SELECT id FROM strategists WHERE id = ? AND user_id = ?", (strategist_id, user_id)).fetchone()
            if not srow:
                return "❌ Estrategista não encontrado para este jogador."
            conn.execute("UPDATE strategists SET equipped = 0 WHERE user_id = ?", (user_id,))
            conn.execute("UPDATE strategists SET equipped = 1 WHERE id = ?", (strategist_id,))
            conn.commit()
            g_bonus, s_bonus = self.get_slot_bonuses(conn, d["general_id"], strategist_id)
        new_power = recalc_power(d["troops"], d["barracks_level"], d["forge_level"], d["doctrine"], g_bonus, s_bonus)
        self.update_player_state(user_id, strategist_id=strategist_id, power=new_power)
        return f"✅ Estrategista equipado (id {strategist_id}).\nΔ Poder: {new_power:,}\nPróximo: iniciar simulação de operação".replace(",", ".")

    def do_simular_operacao(self, user_id: str, key: str) -> str:
        d = self.get_or_create_domain(user_id)
        with self.get_conn() as conn:
            op = conn.execute("SELECT * FROM operations WHERE key = ?", (key.strip().lower(),)).fetchone()
            if not op:
                return "❌ Operação inválida."
            if d["barracks_level"] < op["min_barracks_level"]:
                return f"❌ Requisito ausente: Casernas T{op['min_barracks_level']}+."
            if op["requires_general"] and not d["general_id"]:
                return "❌ Requisito ausente: General equipado para esta operação."
            if d["troops"] <= 0:
                return "❌ Requisito ausente: sem tropas não há incursão."
            chance = simulate_operation_success_chance(d["power"], op["difficulty_power"], d["doctrine"], op["preferred_doctrine"])

            partial_route = False
            if op["requires_strategist"] and not d["strategist_id"]:
                if op["partial_without_strategist"]:
                    partial_route = True
                    chance *= 0.55
                else:
                    return "❌ Requisito ausente: Estrategista equipado para esta operação."

        outcome = "vitória tática" if random.random() <= chance else "falha tática"
        risk_mult = 1.0
        reward_mult = 1.0
        prestige_mult = 1.0
        route_line = "Rota completa habilitada."
        if partial_route:
            risk_mult = 1.35
            reward_mult = 0.45
            prestige_mult = 0.35
            route_line = "Rota parcial: sem estrategista, retorno incompleto."

        troops_lost = int(max(1, d["troops"] * op["base_risk_percent"] * (0.4 if outcome == "vitória tática" else 0.8) * risk_mult))
        base_gold_delta = int(op["base_gold_reward"] * (1.0 if outcome == "vitória tática" else 0.2) * reward_mult)
        prestige_gain = int(op["prestige_reward"] * (1.0 if outcome == "vitória tática" else 0.4) * prestige_mult)
        forge_mult = 1.0 + (d["forge_level"] - 1) * 0.03
        gold_delta = int(base_gold_delta * forge_mult)

        with self.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO season_scores (season_number, user_id, prestige, wealth_snapshot, power_snapshot, updated_at_ts)
                VALUES (1, ?, ?, 0, 0, ?)
                ON CONFLICT(season_number, user_id) DO UPDATE SET
                    prestige = prestige + excluded.prestige,
                    updated_at_ts = excluded.updated_at_ts
                """,
                (user_id, prestige_gain, self.now_ts()),
            )
            conn.execute(
                """
                INSERT INTO operation_runs (user_id, operation_id, outcome, troops_lost, gold_delta, created_at_ts)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, op["id"], outcome, troops_lost, gold_delta, self.now_ts()),
            )
            conn.commit()

        relic_line = self.resolve_discovery(user_id, f"operacao:{op['key']}", d["forge_level"])

        return (
            f"🧪 Simulação `{op['title']}`\n"
            f"{route_line}\n"
            f"Poder atual: {d['power']:,} | Dificuldade: {op['difficulty_power']:,}\n"
            f"Chance estimada: {chance*100:.1f}%\n"
            f"Resultado simulado: **{outcome}**\n"
            f"Registro: perdas estimadas {troops_lost:,} tropas | recompensa base {gold_delta:,} ouro | prestígio +{prestige_gain:,}\n"
            f"{relic_line}\n"
            "Próximo: tente outra operação ou ajuste composição militar"
        ).replace(",", ".")
