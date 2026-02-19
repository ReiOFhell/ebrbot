package com.skygroove.ui.components

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.compose.currentBackStackEntryAsState
import com.skygroove.ui.navigation.Routes

@Composable
fun ImperialScaffold(nav: NavHostController, content: @Composable (Modifier) -> Unit) {
    val current = nav.currentBackStackEntryAsState().value?.destination?.route
    val items = listOf(
        Routes.Trono to "Trono",
        Routes.Biblioteca to "Biblioteca",
        Routes.PlayerSupremo to "Supremo",
        Routes.Grimorios to "Grimórios",
        Routes.Perfil to "Perfil",
        Routes.Estatisticas to "Estatísticas",
    )
    Scaffold(
        bottomBar = {
            NavigationBar {
                items.forEach { (route, label) ->
                    NavigationBarItem(
                        selected = current == route,
                        onClick = { nav.navigate(route) },
                        label = { Text(label) },
                        icon = { Text("✦") },
                    )
                }
            }
        }
    ) { pad -> content(Modifier.padding(pad)) }
}
