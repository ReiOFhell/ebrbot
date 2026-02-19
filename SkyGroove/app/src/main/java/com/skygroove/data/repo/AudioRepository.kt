package com.skygroove.data.repo

import android.content.Context
import com.skygroove.data.local.SkyGrooveDatabase
import com.skygroove.data.local.TrackEntity
import com.skygroove.domain.model.Track
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

class AudioRepository(
    private val context: Context,
    private val db: SkyGrooveDatabase,
) {
    fun observeLibrary(): Flow<List<Track>> = db.trackDao().observeTracks().map { list -> list.map { it.toDomain() } }

    fun search(query: String): Flow<List<Track>> = db.trackDao().search("%$query%").map { it.map(TrackEntity::toDomain) }

    suspend fun refreshFromDevice(scanner: LibraryScanner): Result<Int> = runCatching {
        val scanned = scanner.scan().map { it.toEntity() }
        db.trackDao().upsertAll(scanned)
        scanned.size
    }

    suspend fun setFavorite(trackId: Long, fav: Boolean) = db.trackDao().setFavorite(trackId, fav)

    private fun TrackEntity.toDomain() = Track(id, title, artist, album, durationMs, path, albumArtUri, isFavorite)
    private fun Track.toEntity() = TrackEntity(id, title, artist, album, durationMs, path, albumArtUri, isFavorite)
}
