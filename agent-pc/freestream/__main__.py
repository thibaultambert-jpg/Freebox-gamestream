"""Point d'entrée : `python -m freestream [options]`.

Exemples :
  python -m freestream                         # lance l'agent
  python -m freestream --config ma-config.json
  python -m freestream --list-encoders         # teste NVENC/AMF/QSV/x264
  python -m freestream --print-cmd udp 192.168.1.20   # affiche la commande FFmpeg

Mode vidéo seule, sans app sur le Player (AirMedia) :
  python -m freestream --freebox-pair          # une seule fois
  python -m freestream --cast                  # flux HTTP envoyé au lecteur natif
  python -m freestream --cast-try-all          # teste tous les transports
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import socket
import subprocess
import sys

from aiohttp import web

from . import __version__
from .config import load_config, resolve_source
from .encoders import choose_encoder, detect_encoders
from .ffmpeg_cmd import TRANSPORTS, build_command, make_target
from .inputs import InputMapper, create_backend
from .server import Agent, create_app


def local_ips() -> list[str]:
    """Adresses IPv4 locales probables (pour l'affichage)."""
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.1.254", 9))  # aucune donnée envoyée : sert à choisir l'interface
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="freestream", description="Agent PC FreeStream")
    ap.add_argument("--config", help="fichier JSON de configuration")
    ap.add_argument("--port", type=int, help="port HTTP (défaut 8765)")
    ap.add_argument("--input-backend", choices=["auto", "vigem", "sendinput", "log"])
    ap.add_argument("--encoder", choices=["auto", "nvenc", "amf", "qsv", "x264"])
    ap.add_argument("--source", choices=["auto", "ddagrab", "gdigrab", "testsrc"])
    ap.add_argument("--list-encoders", action="store_true", help="teste les encodeurs et quitte")
    ap.add_argument("--print-cmd", nargs=2, metavar=("TRANSPORT", "IP_PLAYER"),
                    help="affiche la commande FFmpeg et quitte")
    ap.add_argument("--freebox-pair", action="store_true",
                    help="appaire l'agent avec Freebox OS (mode AirMedia) et quitte")
    ap.add_argument("--cast", nargs="?", const="http", metavar="TRANSPORT",
                    help="vidéo seule via AirMedia (http par défaut, ou udp/rtp/udp-multicast/rtp-multicast)")
    ap.add_argument("--cast-try-all", action="store_true",
                    help="AirMedia : essaie tous les transports avec une mire et enregistre un rapport")
    ap.add_argument("--receiver", help="nom du récepteur AirMedia (défaut « Freebox Player »)")
    ap.add_argument("--player-ip", default="", help="IP du Player (transports udp/rtp unicast)")
    ap.add_argument("--pc-ip", help="IP du PC à annoncer au Player (détectée sinon)")
    ap.add_argument("--url-index", type=int, default=0, help="variante d'URL à envoyer (0, 1, 2)")
    ap.add_argument("--no-pin", action="store_true", help="désactive l'appairage (déconseillé)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    cfg = load_config(args.config)
    if args.port:
        cfg["http_port"] = args.port
    if args.input_backend:
        cfg["input"]["backend"] = args.input_backend
    if args.encoder:
        cfg["video"]["encoder"] = args.encoder
    if args.source:
        cfg["video"]["source"] = args.source
    if args.no_pin:
        cfg["require_pin"] = False

    if args.receiver:
        cfg.setdefault("freebox", {})["receiver"] = args.receiver

    if args.freebox_pair:
        from .cast import pair
        from .freebox_api import FreeboxError
        try:
            asyncio.run(pair(cfg))
        except (FreeboxError, OSError) as exc:
            print(f"ERREUR : {exc}")
            return 1
        return 0

    ffmpeg = cfg["ffmpeg"]
    try:
        subprocess.run([ffmpeg, "-version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        print(f"ERREUR : FFmpeg introuvable ('{ffmpeg}'). Installez-le (voir docs/TUTO.md).")
        return 2

    if args.list_encoders:
        codec = cfg["video"]["codec"]
        found = detect_encoders(ffmpeg, codec)
        print(f"Encodeurs {codec} fonctionnels : {', '.join(found) or 'aucun'}")
        return 0 if found else 1

    encoder = choose_encoder(ffmpeg, cfg["video"]["encoder"], cfg["video"]["codec"])

    if args.print_cmd:
        mode, ip = args.print_cmd
        if mode not in TRANSPORTS:
            print(f"Transport inconnu. Choix : {', '.join(TRANSPORTS)}")
            return 2
        cmd = build_command(cfg, resolve_source(cfg), encoder, make_target(cfg, mode, ip))
        print(subprocess.list2cmdline(cmd))
        return 0

    backend = create_backend(cfg["input"]["backend"])
    mapper = InputMapper(backend, cfg["input"]["profiles"], cfg["input"]["profile"],
                         cfg["input"]["hold_timeout_ms"])
    agent = Agent(cfg, encoder, mapper)

    if args.cast or args.cast_try_all:
        return _cast(cfg, agent, args)

    app = create_app(agent)

    port = cfg["http_port"]
    print("=" * 60)
    print(f" FreeStream agent v{__version__} — {cfg['name']}")
    print(f" Encodeur : {encoder} | Source : {resolve_source(cfg)} | Entrées : {backend.name}")
    for ip in local_ips() or ["<IP du PC>"]:
        print(f" Adresse à saisir sur la Freebox : {ip}  (port {port})")
        print(f" Page de mesure de latence     : http://{ip}:{port}/clock")
    if cfg.get("require_pin", True):
        print(f" CODE PIN D'APPAIRAGE : {cfg['pin']}")
    print("=" * 60)
    web.run_app(app, host="0.0.0.0", port=port, print=None)
    return 0


def _cast(cfg: dict, agent: Agent, args: argparse.Namespace) -> int:
    """Mode AirMedia : vidéo seule vers le lecteur natif du Player."""
    from .cast import run_cast
    from .freebox_api import FreeboxError

    ips = local_ips()
    pc_ip = args.pc_ip or (ips[0] if ips else "")
    if not pc_ip:
        print("ERREUR : IP du PC introuvable, indiquez-la avec --pc-ip")
        return 2
    print(f" FreeStream — mode vidéo seule (AirMedia) | Encodeur : {agent.encoder} | "
          f"Source : {resolve_source(cfg)} | IP du PC : {pc_ip}")
    try:
        asyncio.run(run_cast(cfg, agent, transport=args.cast or "http", pc_ip=pc_ip,
                             player_ip=args.player_ip, url_index=args.url_index,
                             try_all=args.cast_try_all))
    except KeyboardInterrupt:
        print("Arrêt.")
    except (FreeboxError, ValueError, OSError) as exc:
        print(f"ERREUR : {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
