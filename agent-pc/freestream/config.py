"""Configuration de l'agent FreeStream.

La configuration par défaut est définie ici ; l'utilisateur peut la surcharger
avec un fichier JSON (voir config.example.json). Seules les clés présentes dans
le fichier remplacent les valeurs par défaut (fusion récursive).
"""
from __future__ import annotations

import copy
import json
import platform
import secrets
import socket
from pathlib import Path
from typing import Any

IS_WINDOWS = platform.system() == "Windows"

# Profils de mapping : nom de touche envoyé par l'app QML -> action sur le PC.
#   "pad:<BOUTON>"  -> manette Xbox virtuelle (ViGEmBus)
#   "key:<TOUCHE>"  -> clavier (SendInput, scancodes)
# Les noms de touches ("Up", "Select", ...) sont produits par app-player/js/keys.js.
# Une touche inconnue arrive sous la forme "code:<entier Qt>" : on peut aussi la mapper.
DEFAULT_PROFILES: dict[str, dict[str, str]] = {
    "manette": {
        "Up": "pad:DPAD_UP",
        "Down": "pad:DPAD_DOWN",
        "Left": "pad:DPAD_LEFT",
        "Right": "pad:DPAD_RIGHT",
        "Select": "pad:A",
        "Back": "pad:B",
        "Red": "pad:X",
        "Green": "pad:Y",
        "Yellow": "pad:LB",
        "Blue": "pad:RB",
        "ChannelUp": "pad:RT",
        "ChannelDown": "pad:LT",
        "Play": "pad:START",
        "Info": "pad:BACK",
        "1": "pad:LSTICK_UPLEFT",
        "2": "pad:LSTICK_UP",
        "3": "pad:LSTICK_UPRIGHT",
        "4": "pad:LSTICK_LEFT",
        "6": "pad:LSTICK_RIGHT",
        "7": "pad:LSTICK_DOWNLEFT",
        "8": "pad:LSTICK_DOWN",
        "9": "pad:LSTICK_DOWNRIGHT",
        "5": "pad:LS",
        "0": "pad:RS",
    },
    "clavier": {
        "Up": "key:UP",
        "Down": "key:DOWN",
        "Left": "key:LEFT",
        "Right": "key:RIGHT",
        "Select": "key:ENTER",
        "Space": "key:SPACE",
        "Back": "key:ESC",
        "Red": "key:SPACE",
        "Green": "key:E",
        "Yellow": "key:Q",
        "Blue": "key:R",
        "ChannelUp": "key:PAGEUP",
        "ChannelDown": "key:PAGEDOWN",
        "Play": "key:P",
        "Info": "key:TAB",
        "1": "key:1", "2": "key:2", "3": "key:3", "4": "key:4", "5": "key:5",
        "6": "key:6", "7": "key:7", "8": "key:8", "9": "key:9", "0": "key:0",
    },
}

DEFAULT_CONFIG: dict[str, Any] = {
    # Nom affiché sur la Freebox
    "name": socket.gethostname(),
    # Port HTTP/WebSocket de l'agent (API + flux HTTP de repli)
    "http_port": 8765,
    # Code PIN d'appairage : null = tiré au hasard à chaque démarrage
    "pin": None,
    "require_pin": True,
    # Chemin de l'exécutable FFmpeg (>= 6.0 conseillé pour ddagrab)
    "ffmpeg": "ffmpeg",
    "video": {
        # auto = ddagrab sous Windows, mire de test (testsrc) ailleurs
        "source": "auto",          # auto | ddagrab | gdigrab | testsrc
        "output_idx": 0,           # numéro d'écran pour ddagrab
        "encoder": "auto",         # auto | nvenc | amf | qsv | x264
        "codec": "h264",           # h264 | hevc
        "resolution": "1280x720",  # "native" ou "LARGEURxHAUTEUR"
        "fps": 60,
        "bitrate_kbps": 12000,
        "gop": 60,                 # distance entre images clés (en images)
        "vbv_frames": 3,           # taille du tampon débit en nombre d'images (petit = faible latence)
        "intra_refresh": False,    # NVENC : rafraîchissement intra progressif (expérimental)
        "draw_mouse": True,
    },
    "audio": {
        "enabled": False,
        # Nom du périphérique DirectShow (ex : "CABLE Output (VB-Audio Virtual Cable)")
        "device": "",
        "codec": "aac",            # aac | mp2 | ac3
        "bitrate_kbps": 160,
    },
    "transport": {
        "mode": "udp",             # udp | rtp | udp-multicast | rtp-multicast | http
        "port": 1234,
        "multicast_group": "239.255.42.42",
        "pkt_size": 1316,          # 7 paquets TS de 188 octets
    },
    "input": {
        "backend": "auto",         # auto | vigem | sendinput | log
        # Une touche "enfoncée" sans nouvel événement pendant ce délai est relâchée
        # automatiquement (certaines télécommandes n'envoient pas le relâchement).
        "hold_timeout_ms": 600,
        "profile": "manette",
        "profiles": DEFAULT_PROFILES,
    },
    "freebox": {
        # Mode vidéo seule (AirMedia) : adresse de Freebox OS et nom du récepteur
        "host": "http://mafreebox.freebox.fr",
        "receiver": "Freebox Player",
        "receiver_password": "",   # si un mot de passe AirMedia est défini sur le Player
    },
    "app": {
        # Touches qui ouvrent le menu pause dans l'app (non transmises au PC)
        "pause_keys": ["Menu"],
        # Appui long sur Retour (ms) pour ouvrir le menu pause, 0 = désactivé
        "back_long_press_ms": 1500,
    },
    "probe": {
        # Modules QML dont l'app sonde la présence (Phase 0). Ajoutez les modules
        # fbx.* trouvés dans la doc du SDK.
        "modules": [
            "QtQuick 2.0",
            "QtQuick 2.7",
            "QtQuick 2.12",
            "QtQuick.Window 2.2",
            "QtQuick.Controls 2.0",
            "QtQuick.LocalStorage 2.0",
            "QtMultimedia 5.0",
            "QtMultimedia 5.12",
            "QtWebSockets 1.0",
            "QtGamepad 1.0",
            "Qt.labs.settings 1.0",
            "QtQml 2.0",
        ],
        "transports": ["udp", "rtp", "udp-multicast", "rtp-multicast", "http"],
        "timeout_s": 12,
    },
}


def deep_merge(base: dict, override: dict) -> dict:
    """Fusionne récursivement `override` dans une copie de `base`."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict) and key != "profiles":
            result[key] = deep_merge(result[key], value)
        elif key == "profiles" and isinstance(value, dict):
            # Les profils fournis remplacent ou complètent les profils par défaut
            merged = copy.deepcopy(result.get(key, {}))
            for name, prof in value.items():
                merged[name] = prof
            result[key] = merged
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config(path: str | Path | None) -> dict[str, Any]:
    """Charge la configuration (défauts + fichier JSON éventuel)."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if path:
        p = Path(path)
        if p.exists():
            with p.open(encoding="utf-8") as fh:
                cfg = deep_merge(cfg, json.load(fh))
        else:
            raise FileNotFoundError(f"Fichier de configuration introuvable : {p}")
    if not cfg.get("pin"):
        # PIN à 4 chiffres, régénéré à chaque démarrage
        cfg["pin"] = f"{secrets.randbelow(10000):04d}"
    cfg["pin"] = str(cfg["pin"])
    return cfg


def resolve_source(cfg: dict[str, Any]) -> str:
    """Retourne la source de capture effective."""
    src = cfg["video"]["source"]
    if src == "auto":
        return "ddagrab" if IS_WINDOWS else "testsrc"
    return src
