package com.skygroove.domain.model

data class Track(
    val id: Long,
    val title: String,
    val artist: String,
    val album: String,
    val durationMs: Long,
    val path: String,
    val albumArtUri: String? = null,
    val isFavorite: Boolean = false,
)
