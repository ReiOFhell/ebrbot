package com.skygroove.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.skygroove.domain.model.Track

@Composable
fun SplashScreen(onFinish: () -> Unit) {
    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.Center) {
        Text("SKYGROOVE")
        Button(onClick = onFinish) { Text("Invocar") }
    }
}

@Composable
fun TronoScreen(tracks: List<Track>) {
    LazyColumn(Modifier.fillMaxSize().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        item { Text("Trono — Domínio Sonoro") }
        item { Text("Mais Reproduzidas") }
        items(tracks.take(5)) { TrackCard(it) }
        item { Text("Últimos Ecos") }
        items(tracks.take(5)) { TrackCard(it) }
        item { Text("Favoritas") }
        items(tracks.filter { it.isFavorite }.take(5)) { TrackCard(it) }
    }
}

@Composable
fun BibliotecaScreen(query: String, tracks: List<Track>, onQuery: (String) -> Unit) {
    Column(Modifier.fillMaxSize().padding(12.dp)) {
        OutlinedTextField(value = query, onValueChange = onQuery, label = { Text("Buscar relíquias") }, modifier = Modifier.fillMaxWidth())
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(tracks.filter { query.isBlank() || it.title.contains(query, true) || it.artist.contains(query, true) || it.album.contains(query, true) }) {
                TrackCard(it)
            }
        }
    }
}

@Composable
fun PlayerSupremoScreen() { Text("Player Supremo — capa, controles, shuffle/repeat") }

@Composable
fun GrimoriosScreen() { Text("Grimórios — criar, renomear, excluir e gerenciar faixas") }

@Composable
fun PerfilScreen() { Text("Perfil — XP, nível, moedas, tempo total ouvido") }

@Composable
fun EstatisticasScreen() { Text("Estatísticas — ranking geral, mensal e ecos recentes") }

@Composable
private fun TrackCard(track: Track) {
    Card {
        Column(Modifier.fillMaxWidth().padding(12.dp)) {
            Text(track.title)
            Text("${track.artist} • ${track.album}")
        }
    }
}
