package com.skygroove.domain.usecase

import kotlin.math.sqrt

object ProgressionEngine {
    fun xpForListen(durationMs: Long): Long = (durationMs / 10_000L).coerceAtLeast(1)

    fun coinsForListen(durationMs: Long): Long = (durationMs / 20_000L).coerceAtLeast(1)

    fun levelFromXp(xp: Long): Int = (sqrt((xp / 25.0).coerceAtLeast(1.0)).toInt()).coerceAtLeast(1)
}
