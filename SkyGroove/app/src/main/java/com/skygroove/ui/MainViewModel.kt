package com.skygroove.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.skygroove.AppContainer
import com.skygroove.domain.model.Track
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.launch

data class MainUiState(
    val tracks: List<Track> = emptyList(),
    val query: String = "",
    val hasPermission: Boolean = false,
)

class MainViewModel(private val container: AppContainer) : ViewModel() {
    private val _state = MutableStateFlow(MainUiState())
    val state: StateFlow<MainUiState> = _state.asStateFlow()

    init {
        container.audioRepository.observeLibrary().onEach { list ->
            _state.value = _state.value.copy(tracks = list)
        }.launchIn(viewModelScope)
    }

    fun onPermissionResult(granted: Boolean) {
        _state.value = _state.value.copy(hasPermission = granted)
        if (granted) refreshLibrary()
    }

    fun refreshLibrary() {
        viewModelScope.launch {
            container.audioRepository.refreshFromDevice(container.scanner)
        }
    }

    fun onSearch(query: String) {
        _state.value = _state.value.copy(query = query)
    }
}
