"""Serveur HTTP + WebSocket de l'agent (aiohttp).

Routes principales (toutes en JSON sauf mention) :
  GET  /api/info             infos publiques (nom, version, PIN requis ?)      [libre]
  POST /api/pair             {"pin": "1234"} -> {"token": "..."}               [libre]
  GET  /api/ping             horloge serveur, pour mesurer l'aller-retour      [libre]
  GET  /api/probe/config     liste des modules/transports à sonder (Phase 0)   [libre]
  POST /api/probe/report     rapport de la sonde -> fichier probe-results/     [libre]
  POST /api/probe/key        touche vue par la sonde (journal)                 [libre]
  GET  /api/app/config       réglages de l'app (touches pause, profils)        [jeton]
  POST /api/stream/start     démarre le flux, renvoie les URLs à lire          [jeton]
  POST /api/stream/stop      arrête le flux                                    [jeton]
  GET  /api/stream/status    état du flux et dernières lignes FFmpeg           [jeton]
  GET  /stream.ts            flux MPEG-TS en HTTP (transport de repli)         [jeton]
  POST /api/input            {"events": [...]} entrées clavier/manette         [jeton]
  GET  /ws                   WebSocket d'entrées (mêmes messages)              [jeton]
  POST /api/profile          {"profile": "clavier"} change le profil de mapping [jeton]
  GET  /clock                page de mesure de latence (à ouvrir sur le PC)    [libre]
  GET  /api/events           flux SSE des entrées reçues (pour /clock)         [libre]
  GET  /                     page d'état                                       [libre]

Le jeton s'envoie dans l'en-tête "X-FreeStream-Token" ou le paramètre "?token=".
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import secrets
import time
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web

from . import __version__
from .config import resolve_source
from .ffmpeg_cmd import TRANSPORTS, build_command, make_target, player_urls
from .inputs import InputMapper
from .stream import StreamManager, apply_overrides

log = logging.getLogger("freestream.server")

AGENT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"
WATCHDOG_KEY: web.AppKey[asyncio.Task] = web.AppKey("watchdog", asyncio.Task)


class Agent:
    """État global de l'agent, partagé par les routes."""

    def __init__(self, cfg: dict[str, Any], encoder: str, mapper: InputMapper,
                 data_dir: Path | None = None):
        self.cfg = cfg
        self.encoder = encoder
        self.mapper = mapper
        self.stream = StreamManager(cfg, encoder)
        self.data_dir = data_dir or AGENT_DIR
        self.tokens_file = self.data_dir / ".freestream_tokens.json"
        self.tokens: set[str] = self._load_tokens()
        self.http_cfg: dict[str, Any] | None = None   # réglages du flux HTTP en attente
        self.http_proc: asyncio.subprocess.Process | None = None
        self.sse_queues: list[asyncio.Queue] = []
        self.failed_pins: dict[str, list[float]] = {}
        mapper.listeners.append(self._broadcast)

    # ---------- jetons d'appairage ----------
    def _load_tokens(self) -> set[str]:
        try:
            return set(json.loads(self.tokens_file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return set()

    def _save_tokens(self) -> None:
        try:
            self.tokens_file.write_text(json.dumps(sorted(self.tokens)), encoding="utf-8")
        except OSError as exc:
            log.warning("Impossible d'enregistrer les jetons : %s", exc)

    def check_token(self, request: web.Request) -> None:
        if not self.cfg.get("require_pin", True):
            return
        token = request.headers.get("X-FreeStream-Token") or request.query.get("token", "")
        if token not in self.tokens:
            raise web.HTTPUnauthorized(text=json.dumps({"error": "appairage requis"}),
                                       content_type="application/json")

    # ---------- diffusion vers la page /clock ----------
    def _broadcast(self, event: dict[str, Any]) -> None:
        for q in list(self.sse_queues):
            if q.qsize() < 100:
                q.put_nowait(event)


def _json(data: Any, status: int = 200) -> web.Response:
    return web.json_response(data, status=status,
                             dumps=lambda d: json.dumps(d, ensure_ascii=False))


async def _body(request: web.Request) -> dict[str, Any]:
    """Corps JSON tolérant (le XMLHttpRequest QML envoie parfois text/plain)."""
    try:
        text = await request.text()
        return json.loads(text) if text.strip() else {}
    except ValueError:
        raise web.HTTPBadRequest(text="JSON invalide")


def create_app(agent: Agent) -> web.Application:
    app = web.Application()
    routes = web.RouteTableDef()
    cfg = agent.cfg

    @routes.get("/api/info")
    async def info(request: web.Request) -> web.Response:
        return _json({
            "app": "freestream", "name": cfg["name"], "version": __version__,
            "require_pin": cfg.get("require_pin", True), "encoder": agent.encoder,
            "source": resolve_source(cfg), "transports": list(TRANSPORTS),
            "defaults": {
                "transport": cfg["transport"]["mode"],
                "resolution": cfg["video"]["resolution"],
                "fps": cfg["video"]["fps"], "bitrate_kbps": cfg["video"]["bitrate_kbps"],
            },
            "your_ip": request.remote,
        })

    @routes.post("/api/pair")
    async def pair(request: web.Request) -> web.Response:
        ip = request.remote or "?"
        now = time.time()
        # Anti force brute : 5 essais ratés par minute et par IP
        recent = [t for t in agent.failed_pins.get(ip, []) if now - t < 60]
        if len(recent) >= 5:
            return _json({"error": "trop d'essais, patientez une minute"}, 429)
        body = await _body(request)
        if str(body.get("pin", "")) != cfg["pin"]:
            agent.failed_pins[ip] = recent + [now]
            return _json({"error": "PIN incorrect"}, 403)
        token = secrets.token_urlsafe(24)
        agent.tokens.add(token)
        agent._save_tokens()
        log.info("Appairage réussi avec %s", ip)
        return _json({"token": token, "name": cfg["name"]})

    @routes.get("/api/ping")
    async def ping(request: web.Request) -> web.Response:
        return _json({"t": time.time() * 1000})

    # ---------- Phase 0 : sonde ----------
    @routes.get("/api/probe/config")
    async def probe_config(request: web.Request) -> web.Response:
        return _json(cfg["probe"])

    @routes.post("/api/probe/report")
    async def probe_report(request: web.Request) -> web.Response:
        body = await _body(request)
        out_dir = agent.data_dir / "probe-results"
        out_dir.mkdir(exist_ok=True)
        name = f"probe-{dt.datetime.now():%Y%m%d-%H%M%S}.json"
        body["_received_from"] = request.remote
        (out_dir / name).write_text(json.dumps(body, indent=2, ensure_ascii=False),
                                    encoding="utf-8")
        log.info("Rapport de sonde enregistré : %s", out_dir / name)
        return _json({"saved": name})

    @routes.post("/api/probe/key")
    async def probe_key(request: web.Request) -> web.Response:
        body = await _body(request)
        log.info("Sonde touche : %s", body)
        agent._broadcast({**body, "probe": True, "t": time.time()})
        return _json({"ok": True})

    # ---------- configuration de l'app ----------
    @routes.get("/api/app/config")
    async def app_config(request: web.Request) -> web.Response:
        agent.check_token(request)
        return _json({**cfg["app"], "profile": agent.mapper.profile,
                      "profiles": sorted(agent.mapper.profiles)})

    @routes.post("/api/profile")
    async def set_profile(request: web.Request) -> web.Response:
        agent.check_token(request)
        body = await _body(request)
        prof = body.get("profile")
        if prof not in agent.mapper.profiles:
            return _json({"error": f"profil inconnu : {prof}"}, 400)
        agent.mapper.release_all()
        agent.mapper.profile = prof
        return _json({"profile": prof})

    # ---------- flux vidéo ----------
    @routes.post("/api/stream/start")
    async def stream_start(request: web.Request) -> web.Response:
        agent.check_token(request)
        body = await _body(request)
        player_ip = body.get("player_ip") or request.remote or ""
        try:
            scfg = apply_overrides(cfg, body)
            target = make_target(scfg, body.get("transport"), player_ip)
        except (ValueError, KeyError) as exc:
            return _json({"error": str(exc)}, 400)
        await agent.stream.stop()
        await _stop_http(agent)
        token = request.headers.get("X-FreeStream-Token") or request.query.get("token", "")
        host = request.url.host or request.host.split(":")[0]
        urls = player_urls(target, host, cfg["http_port"], token)
        if target.mode == "http":
            # FFmpeg sera lancé quand le Player ouvrira /stream.ts
            agent.http_cfg = {"cfg": scfg, "target": target}
            cmd = build_command(scfg, resolve_source(scfg), agent.encoder, target)
        else:
            agent.http_cfg = None
            cmd = await agent.stream.start(scfg, target)
        return _json({"urls": urls, "mode": target.mode, "cmd": cmd})

    @routes.post("/api/stream/stop")
    async def stream_stop(request: web.Request) -> web.Response:
        agent.check_token(request)
        await agent.stream.stop()
        await _stop_http(agent)
        agent.http_cfg = None
        agent.mapper.release_all()
        return _json({"stopped": True})

    @routes.get("/api/stream/status")
    async def stream_status(request: web.Request) -> web.Response:
        agent.check_token(request)
        st = agent.stream.status()
        st["http_client"] = agent.http_proc is not None
        return _json(st)

    @routes.get("/stream.ts")
    async def stream_http(request: web.Request) -> web.StreamResponse:
        agent.check_token(request)
        if not agent.http_cfg:
            # Pas de /api/stream/start préalable : on prend la config par défaut
            agent.http_cfg = {"cfg": cfg, "target": make_target(cfg, "http", request.remote or "")}
        await _stop_http(agent)  # un seul client HTTP à la fois
        scfg, target = agent.http_cfg["cfg"], agent.http_cfg["target"]
        cmd = build_command(scfg, resolve_source(scfg), agent.encoder, target)
        log.info("Flux HTTP vers %s : %s", request.remote, " ".join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        agent.http_proc = proc
        resp = web.StreamResponse(headers={"Content-Type": "video/mp2t",
                                           "Cache-Control": "no-cache"})
        await resp.prepare(request)

        async def pump_stderr() -> None:
            assert proc.stderr is not None
            async for line in proc.stderr:
                log.warning("ffmpeg(http): %s", line.decode(errors="replace").rstrip())

        err_task = asyncio.create_task(pump_stderr())
        try:
            assert proc.stdout is not None
            while True:
                chunk = await proc.stdout.read(188 * 64)  # renvoie dès que des données arrivent
                if not chunk:
                    break
                await resp.write(chunk)
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            err_task.cancel()
            if agent.http_proc is proc:
                await _stop_http(agent)
        return resp

    # ---------- entrées ----------
    @routes.post("/api/input")
    async def input_http(request: web.Request) -> web.Response:
        agent.check_token(request)
        body = await _body(request)
        events = body.get("events") or [body]
        actions = [agent.mapper.handle(e) for e in events if isinstance(e, dict)]
        return _json({"ok": True, "actions": actions})

    @routes.get("/ws")
    async def input_ws(request: web.Request) -> web.WebSocketResponse:
        agent.check_token(request)
        ws = web.WebSocketResponse(heartbeat=5)
        await ws.prepare(request)
        log.info("WebSocket d'entrées connecté : %s", request.remote)
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                except ValueError:
                    continue
                if data.get("ping"):
                    # Écho immédiat : permet à l'app de mesurer l'aller-retour
                    await ws.send_str(json.dumps({"pong": data["ping"]}))
                    continue
                for e in data.get("events") or [data]:
                    if isinstance(e, dict):
                        agent.mapper.handle(e)
        finally:
            agent.mapper.release_all()
            log.info("WebSocket d'entrées déconnecté : %s", request.remote)
        return ws

    # ---------- mesure de latence ----------
    @routes.get("/api/events")
    async def events(request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream",
                                           "Cache-Control": "no-cache"})
        await resp.prepare(request)
        q: asyncio.Queue = asyncio.Queue()
        agent.sse_queues.append(q)
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    await resp.write(f"data: {json.dumps(ev)}\n\n".encode())
                except asyncio.TimeoutError:
                    await resp.write(b": keepalive\n\n")
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            agent.sse_queues.remove(q)
        return resp

    @routes.get("/clock")
    async def clock(request: web.Request) -> web.FileResponse:
        return web.FileResponse(WEB_DIR / "clock.html")

    @routes.get("/")
    async def index(request: web.Request) -> web.FileResponse:
        return web.FileResponse(WEB_DIR / "index.html")

    app.add_routes(routes)

    async def on_startup(app: web.Application) -> None:
        app[WATCHDOG_KEY] = asyncio.create_task(agent.mapper.watchdog())

    async def on_cleanup(app: web.Application) -> None:
        app[WATCHDOG_KEY].cancel()
        await agent.stream.stop()
        await _stop_http(agent)
        agent.mapper.release_all()
        agent.mapper.backend.close()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


async def _stop_http(agent: Agent) -> None:
    proc, agent.http_proc = agent.http_proc, None
    if proc and proc.returncode is None:
        proc.kill()
        await proc.wait()
