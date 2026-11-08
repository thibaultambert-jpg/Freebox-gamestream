# Analyse critique du plan FreeStream

Ce document passe en revue le plan initial. Pour chaque point, il dit ce qui tient, ce qui coince et ce qui a été changé dans le code livré.

> **Ce que je n'ai pas pu vérifier.** Le site `dev.freebox.fr` n'était pas joignable depuis mon environnement, et je n'ai pas de Player sous la main. Tout ce qui touche au SDK (modules présents, format exact du `manifest.json`, intitulés des menus du Player) est donc **à confirmer sur votre boîtier**. C'est justement le rôle de la sonde automatique (`ProbeScreen.qml`), qui répond à ces questions en 5 minutes au lieu de les supposer.

---

## 1. Verdict rapide

| Point du plan | Avis | Changement apporté |
|---|---|---|
| Architecture passerelle PC ↔ app QML | ✅ Seule voie possible sans code natif | Conservée |
| Phase 0 bloquante | ✅ Excellente idée | **Automatisée** : une sonde teste modules, transports, URL et touches, puis envoie un rapport JSON au PC |
| Objectif < 150 ms | ⚠️ Ambitieux avec un lecteur multimédia de box TV | Seuils de décision par type de jeu (§3) |
| Agent en Python **ou** Rust | ⚠️ Rust n'apporte rien ici : c'est FFmpeg qui fait le travail lourd | Python (aiohttp), testé |
| UDP en priorité, HTTP en repli | ✅ Bonne intuition | On teste aussi **RTP et le multicast**, le format natif de l'IPTV Free (§4) |
| WebSocket pour les entrées | ⚠️ Le module `QtWebSockets` n'est peut-être pas sur le Player | WebSocket s'il existe, sinon HTTP (XMLHttpRequest, toujours présent en QML), avec bascule automatique |
| Découverte mDNS | ❌ Impossible côté QML pur (pas de socket UDP) | Scan HTTP du sous-réseau + saisie de l'IP à la télécommande |
| Manette via `fbx` | ⚠️ Incertain : au mieux des touches, sans sticks analogiques | **Manette branchée directement au PC** recommandée (§5) |
| Audio AAC dans le TS | ⚠️ Peut **ajouter** de la latence (le lecteur se cale sur l'horloge audio) | Audio désactivé par défaut, à tester en option |
| Liste des jeux Steam | ⚠️ Beaucoup de travail pour peu de gain | Utiliser **Steam Big Picture**, déjà jouable à la télécommande |
| Paquet FreeStore | ⚠️ Publication soumise à la validation de Free | Pour un usage perso, le mode développeur suffit (à vérifier : l'app reste-t-elle installée après un redémarrage ?) |
| Sécurité | ❌ Absente du plan : n'importe qui sur le réseau pourrait taper au clavier sur votre PC | Appairage par PIN, jeton, anti-force brute |

---

## 2. Le vrai risque : la latence du lecteur du Player

Le plan le dit bien : tout dépend de la Phase 0. Le maillon faible n'est **ni le PC ni le réseau**. C'est le `MediaPlayer` QtMultimedia du Player :

* il est conçu pour la TV et la VOD, donc il **met en tampon** (souvent 0,5 à 2 s sur les box TV) ;
* le SDK QML ne permet probablement pas de régler ce tampon (pas de propriété standard en Qt 5) ;
* sa latence peut **augmenter avec le temps** (dérive d'horloge entre le PC et le Player).

Ce que fait le code livré pour limiter ce risque :

1. **Encodage sans tampon côté PC.** Pas d'images B, CBR avec un tampon VBV de 3 images, préréglages *ultra low latency* de NVENC/AMF/QSV, multiplexeur TS sans délai, PAT/PMT répétées toutes les 200 ms pour accrocher vite.
2. **Mesure automatique du temps jusqu'à la 1re image** pour chaque transport et chaque syntaxe d'URL (sonde).
3. **Resynchronisation.** Un bouton du menu pause, plus une option périodique, rechargent le flux pour vider les tampons du lecteur.
4. **Chien de garde.** Si la lecture se fige plus de 4 s, l'app relance le flux toute seule.

**Ce que je recommande :** ne codez rien d'autre avant d'avoir le chiffre glass-to-glass (cf. tutoriel, §7). Si le lecteur met 800 ms en tampon, aucun réglage FFmpeg ne vous sauvera.

---

## 3. Des seuils de décision plus réalistes

« < 150 ms sinon plan B » est trop binaire. À titre de repère, Moonlight/Sunshine sur un bon réseau filaire fait typiquement 20 à 60 ms.

| Latence glass-to-glass mesurée | Jouable pour… | Décision |
|---|---|---|
| < 100 ms | Presque tout, sauf FPS compétitif et jeux de rythme | GO |
| 100–150 ms | Aventure, plateforme tranquille, course arcade | GO |
| 150–250 ms | RPG, stratégie, point & click, jeux au tour par tour | GO limité, avec plan B en parallèle |
| > 250 ms | Tour par tour seulement | NO-GO, passez au plan B |

---

## 4. Transports vidéo : élargir les essais

Le Player est d'abord un **décodeur IPTV** : la TV de Free arrive en **MPEG-TS sur RTP multicast**. C'est donc probablement le chemin le plus optimisé de son lecteur (hypothèse à vérifier). La sonde teste ces 5 transports, chacun avec plusieurs syntaxes d'URL :

| Transport | Envoi par le PC | URL essayées sur le Player |
|---|---|---|
| `udp` | `udp://IP_PLAYER:1234` | `udp://@:1234`, `udp://0.0.0.0:1234`, `udp://@IP:1234` |
| `rtp` | `rtp://IP_PLAYER:1234` (rtp_mpegts) | `rtp://@:1234`, … |
| `udp-multicast` | `udp://239.255.42.42:1234?ttl=1` | `udp://@239.255.42.42:1234`, … |
| `rtp-multicast` | `rtp://239.255.42.42:1234?ttl=1` | `rtp://@239.255.42.42:1234`, … |
| `http` | l'agent sert `/stream.ts` | `http://IP_PC:8765/stream.ts?token=…` |

**RTSP n'est pas testé** : un rapport de bug sur le tracker Freebox indique que le Player demande un transport `FBXRTP/AVP` non standard dans la requête RTSP SETUP, ce qui casse la plupart des serveurs (MediaMTX compris). Ce n'est à tenter que si tout le reste échoue.

**Réseau :** le Player et le PC doivent être **en Ethernet** (ou CPL de bonne qualité). En UDP, un paquet perdu ne revient jamais : en Wi-Fi, vous aurez des artefacts. Le multicast en Wi-Fi est à proscrire, car il passe au débit le plus bas.

---

## 5. Entrées : sortir la manette du circuit Freebox

C'est **l'amélioration la plus rentable**. Le plan fait passer la manette par le Player, puis le réseau, puis l'agent, puis ViGEm. Problèmes :

* QML ne voit que des **événements de touches** : pas de sticks analogiques, pas de gâchettes progressives, pas de vibrations ;
* certaines touches sont **interceptées par le système** (Free, Home, volume) ;
* certaines télécommandes n'envoient **pas l'événement de relâchement**. L'agent compense avec un relâchement automatique après 600 ms d'inactivité.

**Alternative (zéro développement, latence minimale) :** connectez la manette **directement au PC**.

* PC dans la même pièce : Bluetooth natif (manette Xbox/PS5/8BitDo).
* PC plus loin : dongle Bluetooth ou adaptateur sans fil Xbox au bout d'une **rallonge USB active** posée près de la TV.
* Toutes les fonctions sont disponibles (analogique, vibrations, gyroscope selon le jeu).

L'app garde la télécommande pour naviguer et pour les jeux simples (profil `manette` qui simule une manette Xbox avec le pavé directionnel, ou profil `clavier`).

Note sur **ViGEmBus** : son auteur a arrêté la maintenance du projet, mais le pilote fonctionne toujours sous Windows 10/11 et reste utilisé par de nombreux outils. Le paquet Python `vgamepad` l'embarque.

---

## 6. Ce qui change dans les phases

| Phase | Plan initial | Plan révisé |
|---|---|---|
| 0 | Hello world, inventaire manuel de l'API, tests FFmpeg à la main | **1 soirée** : déployer l'app, lancer la sonde, lire le rapport JSON, mesurer avec la page `/clock` |
| 1 | Réglages FFmpeg, reconnexion, résolutions | Déjà dans le code. Reste à comparer les mesures (720p/1080p, 30/60 i/s, débit, NVENC intra-refresh) |
| 2 | Mapping, ViGEm | Déjà dans le code. Reste à **mapper les codes réels** relevés par la sonde, dans `config.json`, sans redéployer l'app |
| 3 | mDNS, PIN, audio, liste Steam | PIN fait, scan réseau fait. Audio : à tester **avec et sans** (impact sur la latence). Steam : Big Picture |
| 4 | Exécutable + FreeStore | Démarrage auto via le Planificateur de tâches (tutoriel). PyInstaller en option. FreeStore seulement si publication publique |

---

## 7. Plan B : si la latence n'est pas au rendez-vous

Soyons honnêtes : **si le but est de jouer**, et pas de construire l'outil, le plan B est meilleur que le plan A, pour environ 40 €.

1. **Moonlight sur un petit boîtier branché à la TV** (clé Google TV / Fire TV, Apple TV, Raspberry Pi 4/5 avec `moonlight-qt`) et **Sunshine** sur le PC. Latence de 10 à 40 ms, manettes, HDR, 4K. Le Player Devialet peut rester la barre de son si votre TV lui renvoie le son (HDMI ARC/eARC ou optique : à vérifier selon votre installation).
2. **Câble HDMI direct** PC → TV (câble HDMI optique de 10 à 15 m) + Steam Big Picture : latence nulle.
3. Pour info : le Player de la **Freebox Pop** est sous Android TV et accepte Moonlight nativement.

FreeStream reste pertinent si vous ne voulez **aucun matériel en plus**, pour des jeux peu sensibles à la latence, ou pour le plaisir du projet.

---

## 8. Dépôts existants : réutiliser plutôt que réinventer

| Projet | Utilité ici |
|---|---|
| [FFmpeg](https://ffmpeg.org/) (≥ 6.0) | Capture `ddagrab` (Desktop Duplication, zéro copie vers NVENC/AMF), encodage, MPEG-TS. C'est le cœur de l'agent |
| [vgamepad](https://github.com/yannbouteiller/vgamepad) + [ViGEmBus](https://github.com/nefarius/ViGEmBus) | Manette Xbox 360 virtuelle depuis Python |
| [ReDeFin](https://github.com/laborantine/ReDeFin) (client Jellyfin en QML pour Freebox, GPL-3.0) | **Meilleure référence** pour une app QML qui tourne vraiment sur le Player : structure du projet, manifest, gestion des touches, lecture vidéo. À lire avant la Phase 0 (lien trouvé via un fil du forum Freebox, non vérifié) |
| [Sunshine](https://github.com/LizardByte/Sunshine) / [Moonlight](https://github.com/moonlight-stream) | Plan B. Le protocole Moonlight (RTP chiffré, contrôle propriétaire) n'est **pas** lisible par le MediaPlayer QML, donc pas réutilisable pour le plan A |
| [MediaMTX](https://github.com/bluenviron/mediamtx) | Serveur RTSP/RTP/HLS, utile seulement si vous voulez tester RTSP malgré le problème `FBXRTP` |

---

## 9. Risques restants à lever sur le Player

1. **Version de Qt.** Le code vise Qt 5 (`QtMultimedia 5.0`, `MediaPlayer` + `VideoOutput.source`). Si le Player est en Qt 6, seuls `PlayerScreen.qml` et `ProbeScreen.qml` sont à adapter (API `MediaPlayer` différente).
2. **Moteur JavaScript.** Le code est écrit en ES5 strict (`var`, pas de fonctions fléchées) pour fonctionner avec un moteur ancien.
3. **Lecteur vidéo.** Il est possible que `fbx` fournisse son propre lecteur, mieux intégré au décodeur matériel. Si la sonde montre que `MediaPlayer` ne lit aucun flux, cherchez dans la doc du SDK un composant vidéo `fbx.*`, ajoutez son module dans `probe.modules` de la config de l'agent, et adaptez `PlayerScreen.qml`.
4. **Touches interceptées.** Notez lesquelles n'apparaissent jamais dans le journal de la sonde.
