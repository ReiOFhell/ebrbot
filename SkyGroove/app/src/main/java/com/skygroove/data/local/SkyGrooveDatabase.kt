package com.skygroove.data.local

import androidx.room.Database
import androidx.room.RoomDatabase

@Database(
    entities = [
        TrackEntity::class,
        PlaylistEntity::class,
        PlaylistTrackCrossRef::class,
        HistoryEntity::class,
        PlayCountEntity::class,
        ProfileStatsEntity::class,
    ],
    version = 1,
)
abstract class SkyGrooveDatabase : RoomDatabase() {
    abstract fun trackDao(): TrackDao
    abstract fun playlistDao(): PlaylistDao
    abstract fun statsDao(): StatsDao
}
