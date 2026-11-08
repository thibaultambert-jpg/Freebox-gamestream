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

## Démarrage express

1. **PC :** `agent-pc\scripts\install.ps1`, puis `agent-pc\scripts\start-agent.bat`. Notez l'IP et le PIN affichés.
2. **Player :** activez le mode développeur, puis déployez `app-player/` avec Qt Creator et le plugin Freebox.
3. **App :** saisissez l'IP du PC, puis le PIN, puis lancez la **Sonde de compatibilité (Phase 0)**.
4. **Mesure :** ouvrez `http://IP_DU_PC:8765/clock` sur le PC, lancez **Jouer** et photographiez les deux écrans.

## État

| Composant | État |
|---|---|
| Agent PC : capture, encodage, transports, entrées, PIN, page de mesure | ✅ Fonctionnel, testé (pytest, flux HTTP et UDP réels) |
| App QML : accueil, appairage, réglages, envoi des touches | ✅ Testé hors écran (Qt 6) contre l'agent |
| App QML : lecture vidéo et sonde | ⚠️ À valider sur le Player (QtMultimedia du SDK) |
| Latence glass-to-glass | ❓ À mesurer : c'est l'objet de la Phase 0 |
