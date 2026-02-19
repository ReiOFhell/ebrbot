package com.skygroove.domain.usecase

import org.junit.Assert.assertEquals
import org.junit.Test

class ProgressionEngineTest {
    @Test
    fun `xp minimo e acumulativo`() {
        assertEquals(1, ProgressionEngine.xpForListen(2_000))
        assertEquals(12, ProgressionEngine.xpForListen(120_000))
    }

    @Test
    fun `moedas minimas`() {
        assertEquals(1, ProgressionEngine.coinsForListen(10_000))
        assertEquals(3, ProgressionEngine.coinsForListen(60_000))
    }

    @Test
    fun `nivel cresce com xp`() {
        assertEquals(1, ProgressionEngine.levelFromXp(0))
        assertEquals(2, ProgressionEngine.levelFromXp(100))
        assertEquals(4, ProgressionEngine.levelFromXp(500))
    }
}
