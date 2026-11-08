"""Tests du client Freebox OS et du mode cast, contre une fausse Freebox."""
import asyncio
import copy
import hashlib
import hmac
import shutil
import socket

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from freestream.cast import run_cast
from freestream.config import DEFAULT_CONFIG, DEFAULT_PROFILES
from freestream.freebox_api import FreeboxClient, FreeboxError
from freestream.inputs import InputMapper, LogBackend
from freestream.server import Agent

APP_TOKEN = "jeton-app-secret"
CHALLENGE = "defi123"


def fake_freebox(state):
    """Simule les routes Freebox OS utilisées par l'agent."""
    app = web.Application()
    ok = lambda result=None: web.json_response({"success": True, "result": result})
    err = lambda code: web.json_response({"success": False, "error_code": code, "msg": code}, status=403)

    async def api_version(r):
        return web.json_response({"api_version": "8.2", "api_base_url": "/api/", "device_name": "Freebox Server"})

    async def authorize(r):
        state["auth_body"] = await r.json()
        return ok({"app_token": APP_TOKEN, "track_id": 7})

    async def track(r):
        state["polls"] = state.get("polls", 0) + 1
        return ok({"status": "pending" if state["polls"] < 2 else "granted", "challenge": CHALLENGE})

    async def login(r):
        return ok({"logged_in": False, "challenge": CHALLENGE})

    async def session(r):
        body = await r.json()
        expected = hmac.new(APP_TOKEN.encode(), CHALLENGE.encode(), hashlib.sha1).hexdigest()
        if body.get("password") != expected:
            return err("invalid_token")
        return ok({"session_token": "sess", "permissions": {"player": True, "settings": False}})

    async def receivers(r):
        if r.headers.get("X-Fbx-App-Auth") != "sess":
            return err("auth_required")
        if state.get("no_rights"):
            return err("insufficient_rights")
        return ok([{"name": "Freebox Player", "capabilities": {"video": True}}])

    async def receiver_action(r):
        body = await r.json()
        state.setdefault("actions", []).append((r.match_info["name"], body))
        return ok()

    app.router.add_get("/api_version", api_version)
    app.router.add_post("/api/v8/login/authorize/", authorize)
    app.router.add_get("/api/v8/login/authorize/{track}", track)
    app.router.add_get("/api/v8/login/", login)
    app.router.add_post("/api/v8/login/session/", session)
    app.router.add_get("/api/v8/airmedia/receivers/", receivers)
    app.router.add_post("/api/v8/airmedia/receivers/{name}/", receiver_action)
    return app


async def start_fake(state):
    server = TestServer(fake_freebox(state))
    await server.start_server()
    return server, f"http://127.0.0.1:{server.port}"


def test_pair_session_cast(tmp_path):
    async def run():
        state = {}
        server, host = await start_fake(state)
        token_file = tmp_path / "tok.json"
        try:
            async with aiohttp.ClientSession() as http:
                c = FreeboxClient(http, host, token_file)
                assert await c.authorize(poll_interval=0.01) == APP_TOKEN
                assert state["auth_body"]["app_id"] == "fr.freestream.agent"
                # Nouveau client : relit le jeton sur disque
                c2 = FreeboxClient(http, host, token_file)
                perms = await c2.open_session()
                assert perms["player"] is True
                assert (await c2.receivers())[0]["name"] == "Freebox Player"
                await c2.cast("http://pc/stream.ts", "Freebox Player")
                await c2.stop("Freebox Player")
                name, body = state["actions"][0]
                assert name == "Freebox Player"   # le nom avec espace est bien encodé/décodé
                assert body == {"action": "start", "media_type": "video",
                                "media": "http://pc/stream.ts", "password": ""}
                assert state["actions"][1][1]["action"] == "stop"
        finally:
            await server.close()
    asyncio.run(run())


def test_errors_are_translated(tmp_path):
    async def run():
        state = {"no_rights": True}
        server, host = await start_fake(state)
        try:
            async with aiohttp.ClientSession() as http:
                c = FreeboxClient(http, host, tmp_path / "absent.json")
                with pytest.raises(FreeboxError, match="--freebox-pair"):
                    await c.open_session()          # pas de jeton enregistré
                c.app_token = APP_TOKEN
                await c.open_session()
                with pytest.raises(FreeboxError, match="Gestion des accès") as exc:
                    await c.receivers()
                assert exc.value.code == "insufficient_rights"
        finally:
            await server.close()
    asyncio.run(run())


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg absent")
def test_cast_http_end_to_end(tmp_path):
    """Le mode cast envoie au Player une URL qui délivre bien du MPEG-TS."""
    async def run():
        state = {}
        server, host = await start_fake(state)
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg.update(pin="1234", http_port=free_port(), freebox={"host": host})
        cfg["video"].update(source="testsrc", resolution="320x240", fps=30, bitrate_kbps=1000)
        token_file = tmp_path / "tok.json"
        token_file.write_text('{"app_token": "%s"}' % APP_TOKEN)
        agent = Agent(cfg, "x264", InputMapper(LogBackend(), DEFAULT_PROFILES, "manette"),
                      data_dir=tmp_path)
        stop = asyncio.Event()
        task = asyncio.create_task(run_cast(cfg, agent, transport="http", pc_ip="127.0.0.1",
                                            stop_event=stop, token_file=token_file))
        try:
            for _ in range(100):
                if state.get("actions"):
                    break
                await asyncio.sleep(0.05)
            name, body = state["actions"][0]
            assert body["action"] == "start" and body["media_type"] == "video"
            url = body["media"]
            assert url.startswith(f"http://127.0.0.1:{cfg['http_port']}/stream.ts?token=")
            # Le "Player" (ici nous) lit l'URL envoyée
            async with aiohttp.ClientSession() as http:
                async with http.get(url) as r:
                    assert r.status == 200
                    data = await asyncio.wait_for(r.content.readexactly(188 * 20), timeout=20)
            assert all(data[i] == 0x47 for i in range(0, len(data), 188))
        finally:
            stop.set()
            await asyncio.wait_for(task, timeout=10)
            await server.close()
        assert state["actions"][-1][1]["action"] == "stop"   # arrêt propre
    asyncio.run(run())


def test_cast_try_all_report(tmp_path):
    """--cast-try-all : questions à l'utilisateur et rapport JSON."""
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg absent")

    async def run():
        state = {}
        server, host = await start_fake(state)
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg.update(pin="1234", http_port=free_port(), freebox={"host": host})
        cfg["transport"]["port"] = free_port()
        token_file = tmp_path / "tok.json"
        token_file.write_text('{"app_token": "%s"}' % APP_TOKEN)
        agent = Agent(cfg, "x264", InputMapper(LogBackend(), DEFAULT_PROFILES, "manette"),
                      data_dir=tmp_path)

        async def ask(question):
            # Seul le flux HTTP "s'affiche" dans ce test
            last = state["actions"][-1][1]["media"]
            if "o/n" in question:
                return "o" if last.startswith("http") else "n"
            return "350"

        try:
            report = await run_cast(cfg, agent, transport="http", pc_ip="127.0.0.1",
                                    try_all=True, token_file=token_file, ask=ask)
        finally:
            await server.close()
        assert [r["transport"] for r in report["ok"]] == ["http"]
        assert report["ok"][0]["retard_ms"] == "350"
        # udp/rtp unicast ignorés sans --player-ip ; multicast essayés
        tried = {r["transport"] for r in report["results"]}
        assert tried == {"udp-multicast", "rtp-multicast", "http"}
        assert list((tmp_path / "probe-results").glob("airmedia-*.json"))
    asyncio.run(run())
