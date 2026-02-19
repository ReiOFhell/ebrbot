package com.skygroove.data.repo

import com.skygroove.data.local.HistoryEntity
import com.skygroove.data.local.PlayCountEntity
import com.skygroove.data.local.ProfileStatsEntity
import com.skygroove.data.local.SkyGrooveDatabase
import com.skygroove.domain.model.ProfileStats
import com.skygroove.domain.usecase.ProgressionEngine
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import java.time.LocalDate
import java.time.format.DateTimeFormatter

class StatsRepository(private val db: SkyGrooveDatabase) {
    fun observeProfile(): Flow<ProfileStats> = db.statsDao().observeProfile().map {
        val profile = it ?: ProfileStatsEntity(xp = 0, imperialCoins = 0, totalListenMs = 0)
        ProfileStats(
            xp = profile.xp,
            level = ProgressionEngine.levelFromXp(profile.xp),
            imperialCoins = profile.imperialCoins,
            totalListenMs = profile.totalListenMs,
        )
    }

    fun observeTop() = db.statsDao().observeTop()
    fun observeTopMonth() = db.statsDao().observeTopMonth()
    fun observeHistory() = db.statsDao().observeHistory()

    suspend fun registerListen(trackId: Long, listenedMs: Long) {
        val monthKey = LocalDate.now().format(DateTimeFormatter.ofPattern("yyyy-MM"))
        val current = db.statsDao().findPlayCount(trackId)
        val next = if (current == null) {
            PlayCountEntity(trackId = trackId, count = 1, monthKey = monthKey, monthCount = 1)
        } else {
            val monthCount = if (current.monthKey == monthKey) current.monthCount + 1 else 1
            current.copy(count = current.count + 1, monthKey = monthKey, monthCount = monthCount)
        }
        db.statsDao().upsertPlayCount(next)
        db.statsDao().upsertHistory(HistoryEntity(trackId = trackId, timestamp = System.currentTimeMillis()))

        val snapshot = db.statsDao().observeProfile().map {
            it ?: ProfileStatsEntity(xp = 0, imperialCoins = 0, totalListenMs = 0)
        }.first()

        db.statsDao().upsertProfile(
            snapshot.copy(
                xp = snapshot.xp + ProgressionEngine.xpForListen(listenedMs),
                imperialCoins = snapshot.imperialCoins + ProgressionEngine.coinsForListen(listenedMs),
                totalListenMs = snapshot.totalListenMs + listenedMs,
            )
        )
    }
}
