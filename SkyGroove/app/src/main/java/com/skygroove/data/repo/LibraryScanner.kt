package com.skygroove.data.repo

import android.content.ContentUris
import android.content.Context
import android.provider.MediaStore
import com.skygroove.domain.model.Track

class LibraryScanner(private val context: Context) {
    fun scan(): List<Track> {
        val result = mutableListOf<Track>()
        val projection = arrayOf(
            MediaStore.Audio.Media._ID,
            MediaStore.Audio.Media.TITLE,
            MediaStore.Audio.Media.ARTIST,
            MediaStore.Audio.Media.ALBUM,
            MediaStore.Audio.Media.DURATION,
            MediaStore.Audio.Media.DATA,
        )
        val selection = "${MediaStore.Audio.Media.IS_MUSIC} != 0"

        context.contentResolver.query(
            MediaStore.Audio.Media.EXTERNAL_CONTENT_URI,
            projection,
            selection,
            null,
            "${MediaStore.Audio.Media.TITLE} ASC"
        )?.use { cursor ->
            val idCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media._ID)
            val titleCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.TITLE)
            val artistCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.ARTIST)
            val albumCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.ALBUM)
            val durationCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DURATION)
            val dataCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DATA)

            while (cursor.moveToNext()) {
                val id = cursor.getLong(idCol)
                val artUri = ContentUris.withAppendedId(UriTable.albumArtBase, id).toString()
                result += Track(
                    id = id,
                    title = cursor.getString(titleCol) ?: "Relíquia sem nome",
                    artist = cursor.getString(artistCol) ?: "Artista Incógnito",
                    album = cursor.getString(albumCol) ?: "Álbum Incógnito",
                    durationMs = cursor.getLong(durationCol),
                    path = cursor.getString(dataCol) ?: "",
                    albumArtUri = artUri,
                )
            }
        }
        return result
    }
}

private object UriTable {
    val albumArtBase = android.net.Uri.parse("content://media/external/audio/albumart")
}
