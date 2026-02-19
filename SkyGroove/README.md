# SkyGroove — Imperial High-Tech Dark Fantasy (Android/Kotlin)

## Arquitetura e estrutura
- **App único (`:app`) com Clean-ish layers**:
  - `ui/`: Compose, navegação, telas.
  - `domain/`: modelos e regras de progressão (XP/moedas/nível).
  - `data/`: Room + scanner de mídia + repositórios.
  - `player/`: serviço de reprodução em background (Media3 `MediaSessionService`).
- **Por quê**: baixo acoplamento, fácil testar regra de negócio, evoluir storage/player sem reescrever UI.

```
SkyGroove/
  app/src/main/java/com/skygroove/
    core/ (permissions)
    core/theme/ (design system)
    data/local/ (Room entities/dao/db)
    data/repo/ (scanner e repositórios)
    domain/model/
    domain/usecase/
    player/
    ui/components/
    ui/navigation/
    ui/screens/
    MainActivity.kt
    SkyGrooveApp.kt
```

## Decisões técnicas
- **UI**: Jetpack Compose + Material 3 (tema imperial customizado).
- **Player**: Media3 ExoPlayer + MediaSessionService (background/notificação/controles de mídia).
- **Persistência**: Room (playlists, favoritos, histórico, ranking, perfil XP/moedas).
- **Offline-first**: indexação via `MediaStore`, sem dependência de rede.
- **Permissões**: `READ_MEDIA_AUDIO` (Android 13+) / `READ_EXTERNAL_STORAGE` (legado).

## MVP implementado
- Splash + fluxo de primeira execução.
- Tabs: Trono, Biblioteca, Player Supremo, Grimórios, Perfil, Estatísticas.
- Scanner de músicas locais via MediaStore.
- Estrutura de reprodução em segundo plano com serviço Media3.
- Estrutura persistente para favoritos/playlists/histórico/play count/XP/moedas.

## Como rodar
1. Abra `SkyGroove/` no Android Studio Iguana+.
2. Sincronize Gradle.
3. Rode `app` em dispositivo Android 8.0+.
4. Conceda permissão de áudio para invocar biblioteca local.

## Como testar
- Unit tests: `./gradlew test`.
- Validar fluxo:
  - abrir app sem permissão (modo visual),
  - conceder permissão,
  - validar biblioteca e navegação,
  - reproduzir e sair do app para confirmar background.

## Roadmap em 4 fases (obrigatório)
1. **Fase 1 — MVP funcional**: reprodução + biblioteca + permissões (base pronta).
2. **Fase 2 — Organização robusta**: CRUD completo de grimórios, favoritar/desfavoritar e persistência refinada.
3. **Fase 3 — Império estatístico**: contagem por execução/tempo, ranking geral/mensal, XP/moedas calibráveis.
4. **Fase 4 — Polish imperial**: microanimações premium, evolução visual por nível, otimizações de scan/listas.

## Próximos passos
- Implementar tela “Agora Tocando” completa com seek/shuffle/repeat reais conectados ao player.
- Completar UX de estado vazio/erro com copy imperial.
- Adicionar testes de repositório com DB em memória e testes instrumentados de permissões.
