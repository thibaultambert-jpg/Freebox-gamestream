"""Gestion du processus FFmpeg (démarrage, arrêt, redémarrage automatique)."""
from __future__ import annotations

import asyncio
import collections
import copy
import logging
import time
from typing import Any

from .config import resolve_source
from .ffmpeg_cmd import StreamTarget, build_command

log = logging.getLogger("freestream.stream")


def apply_overrides(cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Copie de la config avec les réglages demandés par l'app (résolution, débit...)."""
    c = copy.deepcopy(cfg)
    v = c["video"]
    for key in ("resolution", "fps", "bitrate_kbps", "gop", "codec", "source", "encoder"):
        if params.get(key) not in (None, ""):
            v[key] = params[key]
    if params.get("audio") is not None:
        c["audio"]["enabled"] = bool(params["audio"])
    # Bornes de sécurité
    v["fps"] = max(10, min(120, int(v["fps"])))
    v["bitrate_kbps"] = max(1000, min(80000, int(v["bitrate_kbps"])))
    return c


class StreamManager:
    """Un seul flux à la fois (UDP/RTP). Le flux HTTP est géré par le serveur."""

    def __init__(self, cfg: dict[str, Any], encoder: str):
        self.cfg = cfg
        self.encoder = encoder
        self.proc: asyncio.subprocess.Process | None = None
        self.task: asyncio.Task | None = None
        self.cmd: list[str] = []
        self.target: StreamTarget | None = None
        self.started_at = 0.0
        self.restarts = 0
        self.stderr_tail: collections.deque[str] = collections.deque(maxlen=30)
        self._stop = asyncio.Event()

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "mode": self.target.mode if self.target else None,
            "player_ip": self.target.player_ip if self.target else None,
            "uptime_s": round(time.time() - self.started_at, 1) if self.running else 0,
            "restarts": self.restarts,
            "encoder": self.encoder,
            "cmd": self.cmd,
            "stderr": list(self.stderr_tail),
        }

    async def start(self, cfg: dict[str, Any], target: StreamTarget) -> list[str]:
        """(Re)démarre le flux vers la cible."""
        await self.stop()
        source = resolve_source(cfg)
        self.cmd = build_command(cfg, source, self.encoder, target)
        self.target = target
        self.restarts = 0
        self.stderr_tail.clear()
        self._stop = asyncio.Event()
        self.started_at = time.time()
        self.task = asyncio.create_task(self._run_loop())
        log.info("Flux %s -> %s", target.mode, " ".join(self.cmd))
        return self.cmd

    async def _run_loop(self) -> None:
        """Relance FFmpeg s'il s'arrête (reconnexion auto), avec temporisation croissante."""
        delay = 0.5
        while not self._stop.is_set():
            t0 = time.time()
            try:
                self.proc = await asyncio.create_subprocess_exec(
                    *self.cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
            except OSError as exc:
                self.stderr_tail.append(f"Impossible de lancer FFmpeg : {exc}")
                log.error("Impossible de lancer FFmpeg : %s", exc)
                return
            assert self.proc.stderr is not None
            async for raw in self.proc.stderr:
                line = raw.decode(errors="replace").rstrip()
                if line:
                    self.stderr_tail.append(line)
                    log.warning("ffmpeg: %s", line)
            code = await self.proc.wait()
            if self._stop.is_set():
                break
            # Si FFmpeg a tenu plus de 10 s, on repart avec un délai court
            delay = 0.5 if time.time() - t0 > 10 else min(delay * 2, 10)
            self.restarts += 1
            log.warning("FFmpeg s'est arrêté (code %s), relance dans %.1f s", code, delay)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

    async def stop(self) -> None:
        """Arrête proprement FFmpeg ('q' sur stdin, puis kill si besoin)."""
        self._stop.set()
        proc = self.proc
        if proc and proc.returncode is None:
            try:
                if proc.stdin:
                    proc.stdin.write(b"q")
                    await proc.stdin.drain()
                await asyncio.wait_for(proc.wait(), timeout=2)
            except (asyncio.TimeoutError, ConnectionError, OSError):
                proc.kill()
                await proc.wait()
        if self.task:
            try:
                await asyncio.wait_for(self.task, timeout=3)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self.task.cancel()
        self.task = None
        self.proc = None
