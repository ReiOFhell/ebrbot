package com.skygroove.core.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val ImperialScheme = darkColorScheme(
    primary = Color(0xFFB11226),
    onPrimary = Color(0xFFF5E9D0),
    background = Color(0xFF0B0B0F),
    surface = Color(0xFF15151C),
    secondary = Color(0xFFC6A75E),
    tertiary = Color(0xFF6A0D0D),
)

@Composable
fun SkyGrooveTheme(content: @Composable () -> Unit) {
    val _ = isSystemInDarkTheme()
    MaterialTheme(colorScheme = ImperialScheme, content = content)
}
