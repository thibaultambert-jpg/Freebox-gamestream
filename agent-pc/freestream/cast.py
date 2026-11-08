"""Mode « cast » : vidéo seule vers le lecteur natif du Player, via AirMedia.

Aucune application à installer sur le Player : l'agent démarre le flux
(FFmpeg, comme d'habitude) puis demande à Freebox OS de le faire lire au
Player. La manette, elle, se branche directement sur le PC.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import secrets
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

from .ffmpeg_cmd import TRANSPORTS, make_target, player_urls
from .freebox_api import DEFAULT_HOST, FreeboxClient, FreeboxError
from .server import AGENT_DIR, Agent, create_app
from .stream import apply_overrides

log = logging.getLogger("freestream.cast")

TOKEN_FILE = AGENT_DIR / ".freebox_token.json"


def freebox_settings(cfg: dict[str, Any]) -> dict[str, Any]:
    fb = cfg.get("freebox", {})
    return {"host": fb.get("host", DEFAULT_HOST),
            "receiver": fb.get("receiver", "Freebox Player"),
            "password": fb.get("receiver_password", "")}


async def pair(cfg: dict[str, Any], token_file: Path = TOKEN_FILE) -> None:
    """Appairage unique avec Freebox OS."""
    fb = freebox_settings(cfg)
    async with aiohttp.ClientSession() as http:
        client = FreeboxClient(http, fb["host"], token_file)
        await client.authorize()
        perms = await client.open_session()
        rec = await client.receivers()
    print(f"Appairage réussi. Jeton enregistré dans {token_file}")
    print(f"Permissions accordées : {', '.join(k for k, v in perms.items() if v) or 'aucune'}")
    print("Récepteurs AirMedia : " + (", ".join(r.get("name", "?") for r in rec) or "aucun (Player éteint ?)"))


async def _prepare_stream(agent: Agent, cfg: dict[str, Any], transport: str, pc_ip: str,
                          player_ip: str, url_index: int, overrides: dict[str, Any]) -> str:
    """Démarre le flux et renvoie l'URL à envoyer au Player."""
    scfg = apply_overrides(cfg, overrides)
    target = make_target(scfg, transport, player_ip)
    await agent.stream.stop()
    if transport == "http":
        # Jeton dédié à cette session (non enregistré sur disque)
        token = secrets.token_urlsafe(16)
        agent.tokens.add(token)
        agent.http_cfg = {"cfg": scfg, "target": target}
    else:
        token = ""
        agent.http_cfg = None
        await agent.stream.start(scfg, target)
    urls = player_urls(target, pc_ip, cfg["http_port"], token)
    return urls[min(url_index, len(urls) - 1)]


async def run_cast(cfg: dict[str, Any], agent: Agent, *, transport: str, pc_ip: str,
                   player_ip: str = "", url_index: int = 0, try_all: bool = False,
                   stop_event: asyncio.Event | None = None,
                   token_file: Path = TOKEN_FILE, ask=None) -> dict[str, Any] | None:
    """Lance le serveur de l'agent, le flux, puis l'envoie au Player.

    stop_event : arrête proprement quand il est positionné (sinon Ctrl+C).
    ask        : fonction de question/réponse (tests) ; par défaut input().
    """
    fb = freebox_settings(cfg)
    if transport not in TRANSPORTS:
        raise ValueError(f"Transport inconnu : {transport}")
    if transport in ("udp", "rtp") and not player_ip and not try_all:
        raise ValueError("En unicast, indiquez l'IP du Player avec --player-ip "
                         "(ou utilisez http / udp-multicast / rtp-multicast).")

    runner = web.AppRunner(create_app(agent))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", cfg["http_port"]).start()
    stop_event = stop_event or asyncio.Event()
    loop = asyncio.get_running_loop()

    async def prompt(question: str) -> str:
        if ask:
            return await ask(question)
        return (await loop.run_in_executor(None, input, question)).strip().lower()

    report: dict[str, Any] | None = None
    async with aiohttp.ClientSession() as http:
        client = FreeboxClient(http, fb["host"], token_file)
        try:
            await client.open_session()
            receivers = await client.receivers()
            names = [r.get("name") for r in receivers]
            if fb["receiver"] not in names:
                print(f"⚠ Récepteur « {fb['receiver']} » absent. Récepteurs vus : {names or 'aucun'}")
                print("  Allumez le Player, activez AirMedia dans ses réglages, ou réglez "
                      "\"freebox\": {\"receiver\": \"...\"} dans config.json.")
            if try_all:
                report = await _try_all(agent, cfg, client, fb, pc_ip, player_ip, prompt)
            else:
                url = await _prepare_stream(agent, cfg, transport, pc_ip, player_ip, url_index, {})
                await asyncio.sleep(1.0)  # laisse FFmpeg démarrer avant que le Player se connecte
                await client.cast(url, fb["receiver"], fb["password"])
                print("=" * 60)
                print(f" Flux envoyé au Player : {url}")
                print(f" Mesure de latence : ouvrez http://{pc_ip}:{cfg['http_port']}/clock en plein écran")
                print(" Ctrl+C pour arrêter.")
                print("=" * 60)
                await stop_event.wait()
        finally:
            try:
                if client.session_token:
                    await client.stop(fb["receiver"], fb["password"])
            except (FreeboxError, aiohttp.ClientError) as exc:
                log.warning("Arrêt AirMedia impossible : %s", exc)
            await agent.stream.stop()
            await runner.cleanup()
    return report


async def _try_all(agent: Agent, cfg: dict[str, Any], client: FreeboxClient, fb: dict[str, Any],
                   pc_ip: str, player_ip: str, prompt) -> dict[str, Any]:
    """Essaie chaque transport et chaque variante d'URL avec la mire de test."""
    results = []
    for transport in TRANSPORTS:
        if transport in ("udp", "rtp") and not player_ip:
            print(f"— {transport} ignoré (indiquez --player-ip pour le tester)")
            continue
        target = make_target(cfg, transport, player_ip)
        n_urls = len(player_urls(target, pc_ip, cfg["http_port"], "x"))
        for idx in range(n_urls):
            url = await _prepare_stream(agent, cfg, transport, pc_ip, player_ip, idx,
                                        {"source": "testsrc", "resolution": "1280x720", "fps": 30,
                                         "bitrate_kbps": 6000})
            await asyncio.sleep(1.0)
            entry: dict[str, Any] = {"transport": transport, "url_index": idx, "url": url}
            print(f"\n— Essai {transport} n°{idx} : {url}")
            try:
                await client.cast(url, fb["receiver"], fb["password"])
            except FreeboxError as exc:
                entry.update(ok=False, error=str(exc))
                print(f"  ❌ Refusé par la Freebox : {exc}")
                results.append(entry)
                continue
            answer = await prompt("  La mire s'affiche-t-elle sur la TV ? [o/n] ")
            entry["ok"] = answer.startswith("o")
            if entry["ok"]:
                delay = await prompt("  Retard approximatif du compteur (ms, Entrée si inconnu) : ")
                entry["retard_ms"] = delay or None
            results.append(entry)
            try:
                await client.stop(fb["receiver"], fb["password"])
            except FreeboxError:
                pass
    await agent.stream.stop()
    report = {"mode": "airmedia", "date": dt.datetime.now().isoformat(), "results": results,
              "ok": [r for r in results if r.get("ok")]}
    out = agent.data_dir / "probe-results"
    out.mkdir(exist_ok=True)
    path = out / f"airmedia-{dt.datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport enregistré : {path}")
    ok = report["ok"]
    print("Transports acceptés : " + (", ".join(f"{r['transport']} n°{r['url_index']}" for r in ok)
                                     or "aucun → voir le plan B dans docs/ANALYSE.md"))
    return report
