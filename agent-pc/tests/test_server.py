"""Tests d'intégration du serveur (aiohttp), avec une vraie commande FFmpeg (mire)."""
import asyncio
import copy
import shutil

import pytest
from aiohttp.test_utils import TestClient, TestServer

from freestream.config import DEFAULT_CONFIG, DEFAULT_PROFILES
from freestream.inputs import InputMapper, LogBackend
from freestream.server import Agent, create_app


def make_agent(tmp_path):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["pin"] = "1234"
    cfg["video"].update(source="testsrc", resolution="320x240", fps=30, bitrate_kbps=1000)
    backend = LogBackend()
    mapper = InputMapper(backend, DEFAULT_PROFILES, "manette")
    return Agent(cfg, "x264", mapper, data_dir=tmp_path), backend


async def _client(agent):
    client = TestClient(TestServer(create_app(agent)))
    await client.start_server()
    return client


def test_pairing_and_input(tmp_path):
    async def run():
        agent, backend = make_agent(tmp_path)
        c = await _client(agent)
        try:
            r = await c.get("/api/info")
            assert (await r.json())["require_pin"] is True
            r = await c.post("/api/input", data='{"k":"Select","d":1}')
            assert r.status == 401
            r = await c.post("/api/pair", data='{"pin":"0000"}')
            assert r.status == 403
            r = await c.post("/api/pair", data='{"pin":"1234"}')
            token = (await r.json())["token"]
            h = {"X-FreeStream-Token": token}
            r = await c.post("/api/input", data='{"events":[{"k":"Select","d":1},{"k":"Select","d":0}]}', headers=h)
            assert (await r.json())["actions"] == ["pad:A", "pad:A"]
            assert backend.history == [("press", "pad:A"), ("release", "pad:A")]
            # WebSocket : ping/pong + événement
            ws = await c.ws_connect("/ws?token=" + token)
            await ws.send_str('{"ping": 5}')
            assert (await ws.receive_json())["pong"] == 5
            await ws.send_str('{"k":"Back","d":1}')
            await ws.close()
            await asyncio.sleep(0.1)
            assert ("press", "pad:B") in backend.history
            assert ("release", "pad:B") in backend.history  # relâché à la déconnexion
        finally:
            await c.close()
    asyncio.run(run())


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg absent")
def test_http_stream_produces_mpegts(tmp_path):
    async def run():
        agent, _ = make_agent(tmp_path)
        agent.cfg["require_pin"] = False
        c = await _client(agent)
        try:
            r = await c.post("/api/stream/start", data='{"transport":"http"}')
            body = await r.json()
            assert body["urls"][0].startswith("http://")
            r = await c.get("/stream.ts")
            data = await asyncio.wait_for(r.content.readexactly(188 * 20), timeout=20)
            # Octet de synchronisation MPEG-TS tous les 188 octets
            assert all(data[i] == 0x47 for i in range(0, len(data), 188))
            r.close()
        finally:
            await c.close()
    asyncio.run(run())


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg absent")
def test_udp_stream_reaches_listener(tmp_path):
    async def run():
        agent, _ = make_agent(tmp_path)
        agent.cfg["require_pin"] = False
        agent.cfg["transport"]["port"] = 41234
        loop = asyncio.get_running_loop()
        got = loop.create_future()

        class Proto(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):
                if not got.done():
                    got.set_result(data)

        transport, _ = await loop.create_datagram_endpoint(Proto, local_addr=("127.0.0.1", 41234))
        c = await _client(agent)
        try:
            r = await c.post("/api/stream/start", data='{"transport":"udp","player_ip":"127.0.0.1"}')
            assert r.status == 200
            data = await asyncio.wait_for(got, timeout=20)
            assert len(data) == 1316 and data[0] == 0x47
            r = await c.get("/api/stream/status")
            assert (await r.json())["running"] is True
            await c.post("/api/stream/stop")
        finally:
            transport.close()
            await c.close()
    asyncio.run(run())
