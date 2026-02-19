package com.skygroove.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "tracks")
data class TrackEntity(
    @PrimaryKey val id: Long,
    val title: String,
    val artist: String,
    val album: String,
    val durationMs: Long,
    val path: String,
    val albumArtUri: String?,
    val isFavorite: Boolean = false,
)

@Entity(tableName = "playlists")
data class PlaylistEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val name: String,
)

@Entity(primaryKeys = ["playlistId", "trackId"], tableName = "playlist_tracks")
data class PlaylistTrackCrossRef(
    val playlistId: Long,
    val trackId: Long,
)

@Entity(tableName = "history")
data class HistoryEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val trackId: Long,
    val timestamp: Long,
)

@Entity(tableName = "play_count")
data class PlayCountEntity(
    @PrimaryKey val trackId: Long,
    val count: Int,
    val monthKey: String,
    val monthCount: Int,
)

@Entity(tableName = "profile_stats")
data class ProfileStatsEntity(
    @PrimaryKey val singletonId: Int = 1,
    val xp: Long,
    val imperialCoins: Long,
    val totalListenMs: Long,
)
