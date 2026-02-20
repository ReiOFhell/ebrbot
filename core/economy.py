from dataclasses import dataclass

COLLECT_CAP_SECONDS = 24 * 60 * 60
TRAIN_COOLDOWN_SECONDS = 30 * 60

BARN_BASE_PROD = 12_000
BARRACKS_BASE_TRAIN = 10

BUILDING_BASE_COST = {
    "celeiros": 100_000,
    "casernas": 120_000,
    "forja": 90_000,
}

BUILDING_BASE_MAINTENANCE_H = {
    "celeiros": 300,
    "casernas": 500,
    "forja": 250,
}

UPGRADE_TIME_BY_TARGET_TIER = {
    2: 15 * 60,
    3: 35 * 60,
    4: 80 * 60,
    5: 150 * 60,
    6: 270 * 60,
    7: 420 * 60,
    8: 600 * 60,
    9: 840 * 60,
    10: 1200 * 60,
}


@dataclass(frozen=True)
class EconomySnapshot:
    production_per_hour: int
    building_maintenance_per_hour: int
    military_maintenance_per_hour: int
    total_maintenance_per_hour: int
    net_per_hour: int


def building_upgrade_cost(level: int, estrutura: str) -> int:
    base = BUILDING_BASE_COST[estrutura]
    return int(base * (2.55 ** (level - 1)))


def building_upgrade_time_seconds(target_tier: int) -> int:
    return UPGRADE_TIME_BY_TARGET_TIER.get(target_tier, UPGRADE_TIME_BY_TARGET_TIER[10])


def barn_production_per_hour(level: int) -> int:
    return int(BARN_BASE_PROD * (2.2 ** (level - 1)))


def barracks_train_amount(level: int) -> int:
    return int(BARRACKS_BASE_TRAIN * (2.2 ** (level - 1)))


def building_maintenance_per_hour(level: int, estrutura: str) -> int:
    base = BUILDING_BASE_MAINTENANCE_H[estrutura]
    return int(base * (2.3 ** (level - 1)))


def military_maintenance_per_hour(tropas: int) -> int:
    if tropas <= 1_000:
        return int(tropas * 0.05)
    if tropas <= 10_000:
        return int(1_000 * 0.05 + (tropas - 1_000) * 0.08)
    return int(1_000 * 0.05 + 9_000 * 0.08 + (tropas - 10_000) * 0.12)


def effective_collect_seconds(elapsed_seconds: int) -> int:
    return max(0, min(elapsed_seconds, COLLECT_CAP_SECONDS))


def recalc_power(troops: int, barracks_level: int, forge_level: int) -> int:
    return int(troops + (barracks_level * 50) + (forge_level * 30))


def economy_snapshot(*, barn_level: int, barracks_level: int, forge_level: int, troops: int) -> EconomySnapshot:
    production = barn_production_per_hour(barn_level)
    building_maint = (
        building_maintenance_per_hour(barn_level, "celeiros")
        + building_maintenance_per_hour(barracks_level, "casernas")
        + building_maintenance_per_hour(forge_level, "forja")
    )
    military_maint = military_maintenance_per_hour(troops)
    total = building_maint + military_maint
    return EconomySnapshot(
        production_per_hour=production,
        building_maintenance_per_hour=building_maint,
        military_maintenance_per_hour=military_maint,
        total_maintenance_per_hour=total,
        net_per_hour=production - total,
    )


def net_balance_for_window_seconds(snapshot: EconomySnapshot, seconds: int) -> int:
    return int(snapshot.net_per_hour * (seconds / 3600))
