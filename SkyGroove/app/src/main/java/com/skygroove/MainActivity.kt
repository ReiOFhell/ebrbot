package com.skygroove

import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.skygroove.core.PermissionHelper
import com.skygroove.core.theme.SkyGrooveTheme
import com.skygroove.ui.MainViewModel
import com.skygroove.ui.components.ImperialScaffold
import com.skygroove.ui.navigation.Routes
import com.skygroove.ui.screens.BibliotecaScreen
import com.skygroove.ui.screens.EstatisticasScreen
import com.skygroove.ui.screens.GrimoriosScreen
import com.skygroove.ui.screens.PerfilScreen
import com.skygroove.ui.screens.PlayerSupremoScreen
import com.skygroove.ui.screens.SplashScreen
import com.skygroove.ui.screens.TronoScreen

class MainActivity : ComponentActivity() {
    private val vm by viewModels<MainViewModel> {
        val app = application as SkyGrooveApp
        object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = MainViewModel(app.container) as T
        }
    }

    private val permissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted -> vm.onPermissionResult(granted) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val granted = ContextCompat.checkSelfPermission(this, PermissionHelper.audioPermission()) == PackageManager.PERMISSION_GRANTED
        vm.onPermissionResult(granted)

        setContent { SkyGrooveTheme { SkyGrooveAppRoot(vm) { permissionLauncher.launch(PermissionHelper.audioPermission()) } } }
    }
}

@Composable
private fun SkyGrooveAppRoot(vm: MainViewModel, requestPermission: () -> Unit) {
    val nav = rememberNavController()
    val state by vm.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val _ = remember { context.packageName }

    NavHost(navController = nav, startDestination = Routes.Splash) {
        composable(Routes.Splash) {
            SplashScreen(onFinish = {
                if (!state.hasPermission) requestPermission()
                nav.navigate(Routes.Trono)
            })
        }
        composable(Routes.Trono) {
            ImperialScaffold(nav) { TronoScreen(tracks = state.tracks) }
        }
        composable(Routes.Biblioteca) {
            ImperialScaffold(nav) {
                BibliotecaScreen(query = state.query, tracks = state.tracks, onQuery = vm::onSearch)
            }
        }
        composable(Routes.PlayerSupremo) { ImperialScaffold(nav) { PlayerSupremoScreen() } }
        composable(Routes.Grimorios) { ImperialScaffold(nav) { GrimoriosScreen() } }
        composable(Routes.Perfil) { ImperialScaffold(nav) { PerfilScreen() } }
        composable(Routes.Estatisticas) { ImperialScaffold(nav) { EstatisticasScreen() } }
    }
}
