# FreeStream

Jouez aux jeux de votre PC Windows sur la TV, via le **Freebox Player Devialet**, sans matériel supplémentaire.

```
 PC Windows                                         Freebox Player Devialet (app QML)
 ┌──────────────────────────────┐   MPEG-TS (UDP/RTP/HTTP)   ┌──────────────────────────┐
 │ agent-pc (Python)            │ ─────────────────────────▶ │ MediaPlayer + VideoOutput │
 │  FFmpeg : ddagrab → NVENC/   │                            │                          │
 │  AMF/QSV, basse latence      │ ◀───────────────────────── │ touches télécommande /    │
 │  ViGEm (manette) + SendInput │   WebSocket ou HTTP (JSON) │ manette → JSON            │
 └──────────────────────────────┘                            └──────────────────────────┘
```

## Documentation

* **[Tutoriel détaillé](docs/TUTO.md)** : installation, Phase 0, mesure de latence, jeu, dépannage.
* **[Analyse critique du plan](docs/ANALYSE.md)** : risques, améliorations, plan B, dépôts réutilisables.

## Deux modes

| Mode | Pour qui | Installation sur le Player |
|---|---|---|
| **Express (AirMedia)** : `scripts\cast.bat` | Vidéo seule, manette branchée au PC | Aucune : le lecteur natif lit le flux via l'API AirMedia de Freebox OS |
| **App QML** | Piloter le PC à la télécommande, ou si le lecteur natif est trop lent | App déployée en mode développeur |

## Démarrage express (AirMedia)

1. **PC :** `agent-pc\scripts\install.ps1`.
2. `agent-pc\scripts\cast.bat pair`, puis acceptez sur l'écran de la Freebox Server (une seule fois).
3. `agent-pc\scripts\cast.bat test` pour voir les formats acceptés, puis `cast.bat` pour diffuser.

## Démarrage avec l'app QML

1. **PC :** `agent-pc\scripts\install.ps1`, puis `agent-pc\scripts\start-agent.bat`. Notez l'IP et le PIN affichés.
2. **Player :** activez le mode développeur, puis déployez `app-player/` avec Qt Creator et le plugin Freebox.
3. **App :** saisissez l'IP du PC, puis le PIN, puis lancez la **Sonde de compatibilité (Phase 0)**.
4. **Mesure :** ouvrez `http://IP_DU_PC:8765/clock` sur le PC, lancez **Jouer** et photographiez les deux écrans.

## État

| Composant | État |
|---|---|
| Agent PC : capture, encodage, transports, entrées, PIN, page de mesure | ✅ Fonctionnel, testé (pytest, flux HTTP et UDP réels) |
| App QML : accueil, appairage, réglages, envoi des touches | ✅ Testé hors écran (Qt 6) contre l'agent |
| Mode express AirMedia : client Freebox OS, cast, essais des transports | ✅ Testé contre une Freebox OS simulée ; acceptation des formats et latence à vérifier sur le Player |
| App QML : lecture vidéo et sonde | ⚠️ À valider sur le Player (QtMultimedia du SDK) |
| Latence glass-to-glass | ❓ À mesurer : c'est l'objet de la Phase 0 |
