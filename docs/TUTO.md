# Tutoriel FreeStream : jouer aux jeux de son PC sur le Freebox Player Devialet

Ce tutoriel vous guide pas à pas, de l'installation jusqu'à la première partie. Il couvre aussi la mesure de latence (Phase 0), qui décide si le projet vaut la peine d'être poursuivi.

**Durée estimée :** 1 h 30 pour la première installation, puis 1 minute pour lancer une partie.

> **Intitulés à vérifier.** Les noms exacts des menus du Player et de Qt Creator peuvent varier selon les versions. En cas de doute, la référence est la doc officielle du SDK : <https://dev.freebox.fr/sdk/player.html>.

---

## Sommaire

0. [Ce qu'il vous faut](#0-ce-quil-vous-faut)
1. [Préparer le réseau](#1-préparer-le-réseau)
2. [Installer l'agent sur le PC](#2-installer-lagent-sur-le-pc)
3. [Activer le mode développeur sur le Player](#3-activer-le-mode-développeur-sur-le-player)
4. [Installer l'app sur le Player avec Qt Creator](#4-installer-lapp-sur-le-player-avec-qt-creator)
5. [Premier lancement et appairage](#5-premier-lancement-et-appairage)
6. [Phase 0 : la sonde de compatibilité](#6-phase-0--la-sonde-de-compatibilité)
7. [Mesurer la latence](#7-mesurer-la-latence)
8. [Jouer](#8-jouer)
9. [Personnaliser les touches](#9-personnaliser-les-touches)
10. [Recommandé : la manette branchée au PC](#10-recommandé--la-manette-branchée-au-pc)
11. [Activer le son](#11-activer-le-son)
12. [Démarrage automatique de l'agent](#12-démarrage-automatique-de-lagent)
13. [Référence des réglages](#13-référence-des-réglages)
14. [Dépannage](#14-dépannage)
15. [Pour les développeurs](#15-pour-les-développeurs)

---

## 0. Ce qu'il vous faut

**Matériel**

* Un Freebox Player Devialet (Delta).
* Un PC sous Windows 10 ou 11 avec une carte graphique récente. Encodeur matériel conseillé : NVIDIA (NVENC), AMD (AMF) ou Intel (Quick Sync).
* **Un câble Ethernet** pour le Player et pour le PC (ou des adaptateurs CPL de qualité). Le Wi-Fi est déconseillé.
* Une manette Bluetooth ou USB, optionnelle mais recommandée (§10).

**Logiciels (gratuits)**

| Logiciel | Où l'installer | Rôle |
|---|---|---|
| Python 3.11 ou plus | PC | Fait tourner l'agent |
| FFmpeg 6.0 ou plus | PC | Capture et encodage de l'écran |
| Pilote ViGEmBus | PC | Manette Xbox virtuelle |
| Qt Creator + plugin Freebox | PC de développement (le même PC convient) | Installe l'app sur le Player |
| Ce dépôt git | PC | Code de l'agent et de l'app |

---

## 1. Préparer le réseau

1. Branchez le **Player** et le **PC** en Ethernet, sur la Freebox Server ou sur un switch relié à elle.
2. Donnez une **IP fixe au PC**, pour ne pas avoir à la ressaisir sur le Player :
   * ouvrez Freebox OS (<http://mafreebox.freebox.fr>) ;
   * allez dans *Paramètres de la Freebox → DHCP → Baux statiques* ;
   * ajoutez un bail pour l'adresse MAC du PC, par exemple `192.168.1.10`.
3. Notez aussi l'IP du Player : elle apparaît dans la liste des appareils de Freebox OS.

---

## 2. Installer l'agent sur le PC

### 2.1 Récupérer le code

```powershell
git clone https://github.com/thibaultambert-jpg/Freebox-gamestream.git
cd Freebox-gamestream\agent-pc
```

Sans git : téléchargez le ZIP depuis GitHub (*Code → Download ZIP*) et décompressez-le.

### 2.2 Installation automatique

1. Installez Python depuis <https://www.python.org/downloads/>. **Cochez « Add python.exe to PATH »**.
2. Ouvrez PowerShell dans `agent-pc` et lancez :

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\install.ps1
   ```

   Ce script :
   * crée un environnement Python isolé (`.venv`) et installe `aiohttp` et `vgamepad` ;
   * installe FFmpeg via `winget` s'il est absent (**fermez et rouvrez PowerShell ensuite**) ;
   * copie `config.example.json` vers `config.json`.

3. Installez le pilote **ViGEmBus** (`ViGEmBus_x.y.z_x64_x86_arm64.exe`) depuis <https://github.com/nefarius/ViGEmBus/releases>, puis redémarrez le PC.

### 2.3 Adapter `config.json`

Ouvrez `agent-pc\config.json` dans un éditeur de texte. Le minimum à vérifier :

```json
{
  "name": "PC-Salon",
  "ffmpeg": "ffmpeg",
  "video": { "source": "ddagrab", "encoder": "auto", "resolution": "1280x720", "fps": 60, "bitrate_kbps": 12000 }
}
```

* `ffmpeg` : laissez `"ffmpeg"` s'il est dans le PATH ; sinon mettez le chemin complet, par exemple `"C:/ffmpeg/bin/ffmpeg.exe"` (avec des `/`).
* La référence complète des réglages est au §13.

### 2.4 Vérifier l'installation

```powershell
# Quels encodeurs matériels fonctionnent ?
.venv\Scripts\python.exe -m freestream --list-encoders
#  -> Encodeurs h264 fonctionnels : nvenc, x264

# Voir la commande FFmpeg qui sera utilisée (sans rien lancer)
.venv\Scripts\python.exe -m freestream --config config.json --print-cmd udp 192.168.1.20
```

### 2.5 Lancer l'agent

Double-cliquez sur `scripts\start-agent.bat`. La console affiche :

```
============================================================
 FreeStream agent v0.1.0 — PC-Salon
 Encodeur : nvenc | Source : ddagrab | Entrées : vigem+sendinput
 Adresse à saisir sur la Freebox : 192.168.1.10  (port 8765)
 Page de mesure de latence     : http://192.168.1.10:8765/clock
 CODE PIN D'APPAIRAGE : 4821
============================================================
```

* **Pare-feu Windows** : au premier lancement, Windows demande s'il faut autoriser Python. Cochez **Réseaux privés**. Votre réseau domestique doit être déclaré comme *Privé* dans les paramètres réseau de Windows. Pour créer la règle à la main (PowerShell administrateur) :

  ```powershell
  New-NetFirewallRule -DisplayName "FreeStream" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private
  ```

* Vérifiez que la page <http://localhost:8765/> s'ouvre dans votre navigateur.
* Si la ligne `Entrées :` affiche `log`, ViGEmBus ou `vgamepad` n'est pas installé : les touches seront seulement affichées, pas injectées.

### 2.6 Valider le flux sans le Player (conseillé)

Pour mettre hors de cause le PC et le réseau avant d'accuser le Player, utilisez **VLC** sur un autre ordinateur (ou le même) :

1. Dans VLC : *Média → Ouvrir un flux réseau* → `udp://@:1234`.
2. Sur le PC, lancez la mire de test vers cet ordinateur :

   ```bat
   scripts\phase0-mire.bat 192.168.1.30
   ```

   Pour tester la vraie capture d'écran : `scripts\phase0-udp.bat 192.168.1.30 h264_nvenc`.
3. L'image doit apparaître dans VLC en 1 à 2 s (VLC met lui-même ~1 s en tampon : c'est normal ici).

---

## 3. Activer le mode développeur sur le Player

1. Sur le Player, ouvrez les **Réglages**.
2. Cherchez l'option **« Mode développeur »**. Elle se trouve généralement dans la partie *Système* ou *Informations*, selon la version du firmware ; la doc du SDK donne le chemin exact.
3. Activez-la. Le Player devient visible sur le réseau pour Qt Creator.

---

## 4. Installer l'app sur le Player avec Qt Creator

### 4.1 Installer Qt Creator et le plugin Freebox

Suivez la section d'installation de <https://dev.freebox.fr/sdk/player.html> : installation de Qt / Qt Creator, puis du **plugin Freebox** dans la version indiquée par la doc.

### 4.2 Créer le projet

1. Dans Qt Creator : *Fichier → Nouveau projet* → modèle **Freebox** (application QML pour le Player).
2. Nommez-le `FreeStream`. L'assistant génère un **`manifest.json`** (identité de l'app) et un `main.qml`.
   * **Gardez le `manifest.json` généré.** Son format est propre au SDK ; le dépôt n'en fournit pas pour ne pas vous induire en erreur.
3. Copiez dans le dossier du projet **tout le contenu de `app-player/`** du dépôt, en remplaçant le `main.qml` généré :

   ```
   FreeStream/
   ├── manifest.json        ← généré par l'assistant (à garder)
   ├── main.qml             ← celui du dépôt
   ├── HomeScreen.qml
   ├── MainMenu.qml
   ├── SettingsScreen.qml
   ├── PlayerScreen.qml
   ├── ProbeScreen.qml
   ├── InputSender.qml
   ├── MenuList.qml
   ├── Store.qml
   └── js/
       ├── api.js
       └── keys.js
   ```

4. Si le projet liste ses fichiers (fichier `.qmlproject` ou équivalent), ajoutez-y les nouveaux fichiers et le dossier `js/`.
5. Vérifiez que le point d'entrée déclaré dans le manifest est bien `main.qml`.

### 4.3 Déployer et lancer

1. Sélectionnez votre Player comme cible (kit/appareil Freebox détecté sur le réseau).
2. Cliquez sur ▶ **Exécuter**. L'app s'installe et démarre sur la TV.
3. La sortie de l'application dans Qt Creator affiche les `console.log` de l'app, utiles en cas de souci.

> L'app démarre même s'il manque des modules optionnels sur le Player (WebSocket, LocalStorage) : elle les charge dynamiquement et se débrouille sans.

---

## 5. Premier lancement et appairage

1. Sur l'écran d'accueil, choisissez **« ＋ Ajouter un PC par son adresse IP »**.
2. Saisissez l'IP du PC (§2.5) :
   * **chiffres** de la télécommande : tapent le nombre (avec 3 chiffres, on passe au suivant) ;
   * **◀ ▶** : nombre précédent ou suivant ;
   * **▲ ▼** : +1 / −1 ;
   * **OK** : valider.

   Autre option : « 🔍 Rechercher les PC sur le réseau » scanne les 254 adresses du sous-réseau (environ 15 s).
3. Tapez le **code PIN** affiché dans la console de l'agent.
4. Vous arrivez au menu principal. Le PC est mémorisé, avec son jeton : plus besoin de PIN la prochaine fois, même après un redémarrage de l'agent.

Pour oublier un PC : sélectionnez-le à l'accueil et appuyez sur la **touche rouge**.

---

## 6. Phase 0 : la sonde de compatibilité

C'est **l'étape décisive**. Dans le menu principal, choisissez **« 🧪 Sonde de compatibilité »** et laissez-la tourner, environ 3 à 5 minutes.

### 6.1 Ce que fait la sonde

| Étape | Ce qui est testé | Pourquoi |
|---|---|---|
| Environnement | OS, résolution de l'écran | Savoir pour quoi on développe |
| Modules QML | `QtWebSockets`, `QtQuick.LocalStorage`, `QtGamepad`, `QtMultimedia`, versions de `QtQuick`… | Règle « ne jamais supposer qu'une API existe » |
| Aller-retour HTTP | 10 pings vers l'agent | Latence réseau de base |
| Transports vidéo | udp, rtp, udp-multicast, rtp-multicast, http, chacun avec 1 à 3 syntaxes d'URL | Trouver ce que le lecteur accepte, et mesurer le temps jusqu'à la 1re image |
| Variantes | 1080p60, puis HEVC, sur le meilleur transport | Capacités du décodeur |
| Touches | Vous appuyez sur **toutes** les touches | Codes réels de la télécommande et de la manette |

Pendant les tests vidéo, une mire avec un compteur de millisecondes s'affiche dans l'aperçu.

### 6.2 Journal des touches

Quand la sonde le demande, appuyez sur chaque touche de la télécommande, puis de la manette si elle est appairée au Player. Pour chaque touche s'affiche son nom normalisé (`Up`, `Select`, `Red`…) ou `code:NNN` si elle est inconnue. **Maintenez RETOUR 3 secondes** pour terminer.

### 6.3 Lire le rapport

À la fin, le rapport est enregistré sur le PC dans `agent-pc\probe-results\probe-AAAAMMJJ-HHMMSS.json`, et **le meilleur transport est automatiquement retenu** dans les réglages de l'app.

Extrait commenté :

```jsonc
{
  "modules": [
    { "module": "QtWebSockets 1.0", "ok": false, "error": "module \"QtWebSockets\" is not installed" }
    // -> les entrées passeront en HTTP (automatique)
  ],
  "rtt": { "median_ms": 3 },              // réseau local sain si < 10 ms
  "video": [
    { "transport": "udp", "url": "udp://@:1234", "ok": true, "first_video_ms": 640,
      "statuses": [ { "t": 12, "what": "status=2" }, { "t": 640, "what": "hasVideo=true" } ] },
    { "transport": "http", "url": "http://…/stream.ts?token=…", "ok": true, "first_video_ms": 1900 }
  ],
  "best": { "transport": "udp", "url_index": 0, "first_video_ms": 640 },
  "keys": [
    { "k": "Up", "c": 16777235, "hex": "0x1000013", "repeats": true, "release_seen": true },
    { "k": "code:16777399", "c": 16777399, "release_seen": false }
    // -> touche inconnue, et sans relâchement : l'agent la relâchera au bout de 600 ms
  ]
}
```

**Attention :** `first_video_ms` est le temps de *démarrage* du flux, **pas** la latence de jeu. Celle-ci se mesure au §7.

### 6.4 Décider (go / no-go)

* **Aucun transport `ok`** : le `MediaPlayer` QML ne lit pas ces flux. Cherchez dans la doc du SDK un lecteur vidéo propre au module `fbx` (voir `docs/ANALYSE.md` §9), sinon passez au plan B.
* **Au moins un transport `ok`** : passez à la mesure de latence (§7).

---

## 7. Mesurer la latence

### 7.1 Latence vidéo (glass-to-glass)

1. Sur le PC, ouvrez **`http://IP_DU_PC:8765/clock`** dans un navigateur, en plein écran (**F11**), sur l'écran capturé.
2. Sur le Player, lancez **Jouer**. La TV affiche le chronomètre du PC.
3. Placez-vous pour voir **l'écran du PC et la TV dans le même cadre**, et prenez **une dizaine de photos** avec votre téléphone (de préférence en rafale).
4. Sur chaque photo : **latence = chrono du PC − chrono de la TV**.
5. Gardez la **médiane**, pas la meilleure valeur.

Modèle de tableau à remplir après chaque changement de réglage (règle du projet : une mesure par changement vidéo) :

| Date | Transport | Résolution | i/s | Débit | Encodeur | Audio | Médiane (ms) | Min–max (ms) | Remarques |
|---|---|---|---|---|---|---|---|---|---|
| | udp | 1280x720 | 60 | 12 | nvenc | non | | | |

> **La photo mesure un peu plus que la réalité.** L'écran du PC a lui-même un délai d'affichage, et la TV aussi (activez le **mode Jeu** de la TV). Pour comparer des réglages entre eux, c'est très bien ; pour un chiffre absolu, c'est légèrement pessimiste.

### 7.2 Latence entrée → image (la plus parlante)

1. La page `/clock` contient un **carré qui s'allume en blanc** dès qu'une touche arrive sur le PC.
2. Filmez **au ralenti** (120 ou 240 i/s) votre doigt sur la télécommande **et** la TV.
3. Sur la vidéo, comptez les images entre l'appui sur la touche et le flash sur la TV. Par exemple, à 240 i/s : 1 image = 4,2 ms.

Cette mesure inclut tout : télécommande, Player, réseau, agent, capture, encodage, décodage, TV.

### 7.3 Pistes pour réduire la latence

À tester une par une, avec une mesure après chaque essai :

1. **Mode Jeu** de la TV. Gain souvent énorme, jusqu'à 50–100 ms.
2. Transport `udp`, puis `rtp`, puis `rtp-multicast`.
3. Laisser l'**audio désactivé**.
4. 60 i/s plutôt que 30 (le délai par image est divisé par deux).
5. `"resolution": "native"` avec le bureau Windows réglé en 1920x1080 : capture sans copie vers l'encodeur (NVENC/AMF), donc moins de charge et moins de délai.
6. `"vbv_frames": 1` ou `2` : débit plus régulier, au prix de la qualité dans les scènes chargées.
7. NVENC uniquement : `"intra_refresh": true` avec `"gop": 600` (supprime les grosses images clés périodiques).
8. Si la latence **augmente pendant la partie** : menu pause → *Resynchroniser*, ou réglage *Resynchronisation auto*.

---

## 8. Jouer

1. Sur le PC, lancez le jeu, de préférence en mode **fenêtré sans bordure** (*borderless*), plus fiable pour la capture que le plein écran exclusif.
   * Astuce : lancez **Steam Big Picture**. Toute l'interface se pilote avec le pavé directionnel et OK de la télécommande (profil `manette`).
2. Sur le Player : menu principal → **▶ Jouer**.
3. Toutes les touches partent vers le PC, **sauf** :
   * la touche **Menu**, qui ouvre le menu pause (configurable) ;
   * un **appui long (1,5 s) sur Retour**, qui ouvre aussi le menu pause.
4. **Menu pause :**
   * *Reprendre* ;
   * *Resynchroniser le flux* : vide les tampons du lecteur, à faire si l'image prend du retard ;
   * *Afficher / masquer les statistiques* : RTT réseau, mode des entrées (WebSocket ou HTTP), temps de 1re image, relances ;
   * *Quitter* : arrête le flux sur le PC et relâche toutes les touches.

Correspondance par défaut, **profil `manette`** (Xbox 360 virtuelle) :

| Télécommande | Manette Xbox |
|---|---|
| ▲ ▼ ◀ ▶ | Croix directionnelle |
| OK | A |
| Retour | B |
| Rouge / Vert | X / Y |
| Jaune / Bleu | LB / RB |
| Chaîne + / − | RT / LT |
| Lecture | START |
| Info | BACK |
| 2 4 6 8 (et 1 3 7 9) | Stick gauche (8 directions) |
| 5 / 0 | Clic stick gauche / droit |

Le **profil `clavier`** envoie des touches clavier (flèches, Entrée, Échap, Espace…). On change de profil dans *Réglages → Profil de touches*.

---

## 9. Personnaliser les touches

Le mapping se fait **uniquement sur le PC**, dans `config.json`. Pas besoin de redéployer l'app.

1. Récupérez les noms et codes des touches dans le rapport de la sonde (§6.3).
2. Ajoutez un profil dans `config.json` :

   ```json
   "input": {
     "profile": "mon-jeu",
     "profiles": {
       "mon-jeu": {
         "Up": "key:W", "Down": "key:S", "Left": "key:A", "Right": "key:D",
         "Select": "key:SPACE", "Back": "key:ESC",
         "Red": "pad:X",
         "code:16777399": "key:F5"
       }
     }
   }
   ```

   * **Clé** : le nom normalisé (`Up`, `Select`, `Red`, `ChannelUp`, `1`…) ou `code:<code Qt>` pour une touche inconnue.
   * **Valeur `key:…`** : touche clavier parmi `A`–`Z`, `0`–`9`, `F1`–`F12`, `UP`, `DOWN`, `LEFT`, `RIGHT`, `ENTER`, `ESC`, `SPACE`, `TAB`, `BACKSPACE`, `LSHIFT`, `LCTRL`, `LALT`, `PAGEUP`, `PAGEDOWN`, `HOME`, `END`, `INSERT`, `DELETE`.
   * **Valeur `pad:…`** : bouton de la manette virtuelle parmi `A`, `B`, `X`, `Y`, `LB`, `RB`, `LT`, `RT`, `START`, `BACK`, `GUIDE`, `LS`, `RS`, `DPAD_UP`, `DPAD_DOWN`, `DPAD_LEFT`, `DPAD_RIGHT`, `LSTICK_UP`, `LSTICK_DOWN`, `LSTICK_LEFT`, `LSTICK_RIGHT`, `LSTICK_UPLEFT`, `LSTICK_UPRIGHT`, `LSTICK_DOWNLEFT`, `LSTICK_DOWNRIGHT`.
3. Les profils par défaut (`manette`, `clavier`) restent disponibles. Ceux que vous définissez s'ajoutent ou les remplacent s'ils portent le même nom.
4. Redémarrez l'agent.
5. Vérifiez avec la page `/clock` : la ligne « Dernière touche » affiche `Up → key:W`.

**Touches qui restent « collées » ?** Certaines télécommandes n'envoient pas de relâchement. L'agent relâche toute touche sans nouvel événement depuis `hold_timeout_ms` (600 ms par défaut). Augmentez cette valeur si une touche maintenue « lâche » toute seule ; baissez-la si les touches traînent.

---

## 10. Recommandé : la manette branchée au PC

C'est l'amélioration la plus simple et la plus efficace (voir `docs/ANALYSE.md` §5) :

* **PC dans la même pièce :** appairez la manette en Bluetooth directement sur Windows (*Paramètres → Bluetooth et appareils*).
* **PC dans une autre pièce :** prenez une **rallonge USB active** (5–10 m) avec, au bout, près de la TV, un dongle Bluetooth ou l'adaptateur sans fil Xbox.

Le jeu voit une vraie manette : sticks analogiques, gâchettes progressives, vibrations, et aucune latence ajoutée par le Player. L'app FreeStream ne sert alors qu'à **afficher l'image** ; gardez la télécommande pour le menu pause.

---

## 11. Activer le son

Le son voyage dans le flux MPEG-TS et sort par le Devialet. **À tester avec une mesure** (§7) : sur certains lecteurs, l'audio augmente la latence.

1. Installez **VB-Audio Virtual Cable** (<https://vb-audio.com/Cable/>) et choisissez **« CABLE Input »** comme sortie audio de Windows.
   * Alternative : activez « Mixage stéréo » dans les périphériques d'enregistrement, si votre carte son le propose.
2. Listez les périphériques de capture :

   ```powershell
   ffmpeg -hide_banner -list_devices true -f dshow -i dummy
   ```

3. Dans `config.json`, recopiez **exactement** le nom du périphérique :

   ```json
   "audio": { "enabled": true, "device": "CABLE Output (VB-Audio Virtual Cable)", "codec": "aac", "bitrate_kbps": 160 }
   ```

4. Redémarrez l'agent, puis activez *Réglages → Audio* dans l'app.
5. Si le son est absent ou la latence explose, essayez `"codec": "mp2"` (codec historique de la TNT, très bien supporté par les décodeurs TV) ou `"ac3"`.

---

## 12. Démarrage automatique de l'agent

La capture d'écran (`ddagrab`) a besoin de la **session utilisateur ouverte** : lancez donc l'agent **à l'ouverture de session**, pas comme service Windows.

**Méthode simple :** touche *Windows + R* → `shell:startup` → créez dans ce dossier un raccourci vers `agent-pc\scripts\start-agent.bat`.

**Méthode avec droits élevés** (nécessaire pour injecter des touches dans un jeu lancé en administrateur). Dans PowerShell administrateur :

```powershell
schtasks /create /tn "FreeStream" /sc onlogon /rl highest /tr "\"C:\chemin\vers\Freebox-gamestream\agent-pc\scripts\start-agent.bat\""
```

**Exécutable autonome (optionnel) :**

```powershell
.venv\Scripts\pip install pyinstaller
.venv\Scripts\pyinstaller --name FreeStream --add-data "freestream\web;freestream\web" run_agent.py
# -> dist\FreeStream\FreeStream.exe (copiez config.json à côté et lancez-le avec --config config.json)
```

---

## 13. Référence des réglages

### 13.1 Agent (`agent-pc\config.json`)

| Clé | Défaut | Description |
|---|---|---|
| `name` | nom du PC | Nom affiché sur la TV |
| `http_port` | `8765` | Port de l'API, du WebSocket et du flux HTTP. L'app suppose 8765 |
| `pin` | aléatoire | PIN fixe si vous préférez (ex. `"1234"`) |
| `require_pin` | `true` | `false` désactive l'appairage. **Déconseillé** : n'importe qui sur le réseau pourrait taper sur votre PC |
| `ffmpeg` | `"ffmpeg"` | Chemin de FFmpeg |
| `video.source` | `auto` | `ddagrab` (Windows 10/11, rapide), `gdigrab` (repli), `testsrc` (mire de test) |
| `video.output_idx` | `0` | Écran capturé (0 = principal) |
| `video.encoder` | `auto` | `nvenc`, `amf`, `qsv`, `x264` (logiciel) |
| `video.codec` | `h264` | `hevc` possible si la sonde montre que le Player le décode |
| `video.resolution` | `1280x720` | `native` = sans mise à l'échelle (le plus rapide avec NVENC/AMF) |
| `video.fps` | `60` | Images par seconde |
| `video.bitrate_kbps` | `12000` | Débit constant |
| `video.gop` | `60` | Distance entre images clés (1 s à 60 i/s : récupération rapide après une perte UDP) |
| `video.vbv_frames` | `3` | Taille du tampon de débit, en images |
| `video.intra_refresh` | `false` | NVENC : rafraîchissement progressif au lieu des images clés |
| `audio.*` | désactivé | Voir §11 |
| `transport.mode` | `udp` | Transport par défaut (l'app envoie le sien) |
| `transport.port` | `1234` | Port UDP/RTP |
| `transport.multicast_group` | `239.255.42.42` | Groupe multicast |
| `input.backend` | `auto` | `vigem`, `sendinput`, `log` (simulation) |
| `input.hold_timeout_ms` | `600` | Relâchement automatique |
| `input.profile` | `manette` | Profil actif au démarrage |
| `app.pause_keys` | `["Menu"]` | Touches qui ouvrent le menu pause |
| `app.back_long_press_ms` | `1500` | Appui long sur Retour pour le menu pause (`0` = désactivé) |
| `probe.modules` | liste | Modules testés par la sonde. **Ajoutez-y les modules `fbx.*`** trouvés dans la doc du SDK |

### 13.2 App (*Réglages* sur le Player)

Transport, variante d'URL, résolution, i/s, débit, audio, statistiques, resynchronisation auto, profil de touches. Ces réglages sont mémorisés sur le Player si `QtQuick.LocalStorage` existe (la sonde vous le dira), sinon jusqu'à la fermeture de l'app.

### 13.3 Options en ligne de commande de l'agent

```
python -m freestream [--config FICHIER] [--port N] [--encoder auto|nvenc|amf|qsv|x264]
                     [--source auto|ddagrab|gdigrab|testsrc] [--input-backend auto|vigem|sendinput|log]
                     [--list-encoders] [--print-cmd TRANSPORT IP_PLAYER] [--no-pin] [-v]
```

---

## 14. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| « Aucun agent FreeStream sur … » | Pare-feu, mauvaise IP, agent arrêté | §2.5 : règle de pare-feu, réseau *Privé*. Test depuis un autre appareil : `http://IP_PC:8765/api/info` |
| Le scan ne trouve rien | Sous-réseau différent de 192.168.1.x, ou pare-feu | Saisissez l'IP à la main ; le scan utilise les 3 premiers nombres de la dernière IP saisie |
| « PIN incorrect » / « trop d'essais » | Le PIN change à chaque démarrage | Relisez la console ; après 5 échecs, attendez 1 minute. Ou fixez `"pin"` dans la config |
| Écran noir, « délai dépassé » | Transport non supporté, ou FFmpeg en erreur | Regardez la console de l'agent (lignes `ffmpeg:`). Testez avec VLC (§2.6). Refaites la sonde |
| `ddagrab` : erreur au démarrage | FFmpeg < 6.0, ou session verrouillée / Bureau à distance | Mettez FFmpeg à jour ; ouvrez la session sur l'écran physique ; sinon `"source": "gdigrab"` |
| Image figée sur un écran UAC | Le bureau sécurisé de Windows n'est pas capturable | Validez l'invite UAC sur le PC, ou lancez le jeu sans élévation |
| Artefacts, blocs gris | Pertes UDP (Wi-Fi, CPL faible, débit trop haut) | Ethernet, débit plus bas, `gop` 30 |
| La latence augmente pendant la partie | Dérive des tampons du lecteur | Menu pause → *Resynchroniser* ; activez la resynchronisation auto |
| Touches sans effet dans le jeu | Back-end `log`, jeu lancé en admin, mauvais profil | Vérifiez la ligne `Entrées :` au démarrage ; agent en admin (§12) ; regardez `/clock` |
| Touche qui reste enfoncée | La télécommande n'envoie pas de relâchement | Baissez `hold_timeout_ms` |
| Manette virtuelle non vue par le jeu | ViGEmBus absent | Installez ViGEmBus, redémarrez ; testez avec `joy.cpl` (Win+R) |
| Encodeur `x264` choisi alors que j'ai une carte NVIDIA | Pilote trop ancien | Mettez à jour le pilote graphique ; `--list-encoders` |
| L'app ne démarre pas sur le Player | Module manquant ou version de Qt | Sortie de l'application dans Qt Creator ; `docs/ANALYSE.md` §9 |

---

## 15. Pour les développeurs

### 15.1 Organisation du dépôt

```
agent-pc/                 Agent PC (Python 3.11+, aiohttp)
  freestream/
    __main__.py           Ligne de commande
    config.py             Réglages par défaut + profils de touches
    ffmpeg_cmd.py         Construction des commandes FFmpeg (fonctions pures)
    encoders.py           Détection des encodeurs matériels
    stream.py             Processus FFmpeg avec relance automatique
    server.py             API HTTP, WebSocket, flux HTTP, SSE
    inputs/               Mapping des touches + ViGEm / SendInput / simulation
    web/clock.html        Chronomètre de mesure de latence
  scripts/                Installation, lancement, tests FFmpeg bruts (Phase 0)
  tests/                  Tests pytest (avec un vrai FFmpeg pour HTTP et UDP)
app-player/               App QML du Player (Qt 5, ES5)
docs/                     Analyse critique et ce tutoriel
```

### 15.2 Lancer les tests (Windows, Linux ou macOS)

```bash
cd agent-pc
pip install -r requirements-dev.txt
python -m pytest -q
```

Sous Linux et macOS, l'agent tourne en mode simulation (mire `testsrc`, entrées journalisées). C'est pratique pour développer l'app sans PC de jeu :

```bash
python -m freestream --source testsrc --encoder x264 --input-backend log
```

### 15.3 Protocole app ↔ agent

* **Événement de touche** (WebSocket `/ws` ou `POST /api/input`) :
  `{"k": "Up", "c": 16777235, "d": 1, "r": 0}`. `d` vaut 1 pour l'appui et 0 pour le relâchement ; `r` vaut 1 pour une répétition automatique.
* **Démarrer le flux :** `POST /api/stream/start {"transport": "udp", "resolution": "1280x720", "fps": 60, "bitrate_kbps": 12000}`. La réponse contient `{"urls": [...], "cmd": [...]}`.
* **Authentification :** en-tête `X-FreeStream-Token` ou paramètre `?token=`.
* La liste complète des routes est en tête de `agent-pc/freestream/server.py`.
