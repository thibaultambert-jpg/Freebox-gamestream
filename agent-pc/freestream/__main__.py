"""Point d'entrée : `python -m freestream [options]`.

Exemples :
  python -m freestream                         # lance l'agent
  python -m freestream --config ma-config.json
  python -m freestream --list-encoders         # teste NVENC/AMF/QSV/x264
  python -m freestream --print-cmd udp 192.168.1.20   # affiche la commande FFmpeg
"""
from __future__ import annotations

import argparse
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


if __name__ == "__main__":
    sys.exit(main())
