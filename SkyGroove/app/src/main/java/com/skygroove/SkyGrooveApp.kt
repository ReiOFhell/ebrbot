package com.skygroove

import android.app.Application
import androidx.room.Room
import com.skygroove.data.local.SkyGrooveDatabase
import com.skygroove.data.repo.AudioRepository
import com.skygroove.data.repo.LibraryScanner
import com.skygroove.data.repo.StatsRepository

class SkyGrooveApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        val db = Room.databaseBuilder(this, SkyGrooveDatabase::class.java, "skygroove.db").build()
        container = AppContainer(
            audioRepository = AudioRepository(this, db),
            statsRepository = StatsRepository(db),
            scanner = LibraryScanner(this),
        )
    }
}

data class AppContainer(
    val audioRepository: AudioRepository,
    val statsRepository: StatsRepository,
    val scanner: LibraryScanner,
)
