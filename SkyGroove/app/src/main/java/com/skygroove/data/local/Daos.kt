package com.skygroove.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface TrackDao {
    @Query("SELECT * FROM tracks ORDER BY title")
    fun observeTracks(): Flow<List<TrackEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(items: List<TrackEntity>)

    @Query("UPDATE tracks SET isFavorite = :fav WHERE id = :trackId")
    suspend fun setFavorite(trackId: Long, fav: Boolean)

    @Query("SELECT * FROM tracks WHERE title LIKE :q OR artist LIKE :q OR album LIKE :q ORDER BY title")
    fun search(q: String): Flow<List<TrackEntity>>
}

@Dao
interface PlaylistDao {
    @Query("SELECT * FROM playlists ORDER BY name")
    fun observePlaylists(): Flow<List<PlaylistEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(item: PlaylistEntity): Long

    @Query("UPDATE playlists SET name = :name WHERE id = :id")
    suspend fun rename(id: Long, name: String)

    @Query("DELETE FROM playlists WHERE id = :id")
    suspend fun delete(id: Long)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun addTrack(ref: PlaylistTrackCrossRef)

    @Query("DELETE FROM playlist_tracks WHERE playlistId = :playlistId AND trackId = :trackId")
    suspend fun removeTrack(playlistId: Long, trackId: Long)
}

@Dao
interface StatsDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertHistory(item: HistoryEntity)

    @Query("SELECT * FROM history ORDER BY timestamp DESC LIMIT :limit")
    fun observeHistory(limit: Int = 20): Flow<List<HistoryEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertPlayCount(item: PlayCountEntity)

    @Query("SELECT * FROM play_count ORDER BY count DESC LIMIT :limit")
    fun observeTop(limit: Int = 20): Flow<List<PlayCountEntity>>

    @Query("SELECT * FROM play_count ORDER BY monthCount DESC LIMIT :limit")
    fun observeTopMonth(limit: Int = 20): Flow<List<PlayCountEntity>>

    @Query("SELECT * FROM profile_stats WHERE singletonId = 1")
    fun observeProfile(): Flow<ProfileStatsEntity?>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertProfile(item: ProfileStatsEntity)

    @Query("SELECT * FROM play_count WHERE trackId = :trackId")
    suspend fun findPlayCount(trackId: Long): PlayCountEntity?
}
