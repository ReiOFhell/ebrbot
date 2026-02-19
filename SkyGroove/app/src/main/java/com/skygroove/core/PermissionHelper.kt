package com.skygroove.core

import android.Manifest
import android.os.Build

object PermissionHelper {
    fun audioPermission(): String = if (Build.VERSION.SDK_INT >= 33) {
        Manifest.permission.READ_MEDIA_AUDIO
    } else {
        Manifest.permission.READ_EXTERNAL_STORAGE
    }
}
