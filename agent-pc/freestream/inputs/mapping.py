"""Traduction des événements de touches reçus de la Freebox en actions PC.

Format d'un événement envoyé par l'app QML (JSON) :
    {"k": "Up", "c": 16777235, "d": 1, "r": 0}
      k : nom normalisé de la touche (voir app-player/js/keys.js)
      c : code Qt brut (sert pour les touches inconnues : action "code:<c>")
      d : 1 = appui, 0 = relâchement
      r : 1 = répétition automatique (touche maintenue)

L'app reste "bête" : tout le mapping se fait ici, modifiable sans redéployer l'app.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from .backends import Backend

log = logging.getLogger("freestream.input")


class InputMapper:
    def __init__(self, backend: Backend, profiles: dict[str, dict[str, str]],
                 profile: str, hold_timeout_ms: int = 600):
        self.backend = backend
        self.profiles = profiles
        self.profile = profile if profile in profiles else next(iter(profiles))
        self.hold_timeout = hold_timeout_ms / 1000.0
        # action -> instant du dernier appui/répétition
        self.held: dict[str, float] = {}
        self.listeners: list[Callable[[dict[str, Any]], None]] = []
        self.count = 0

    def resolve(self, event: dict[str, Any]) -> str | None:
        """Action associée à l'événement selon le profil actif."""
        table = self.profiles.get(self.profile, {})
        name = str(event.get("k", ""))
        if name in table:
            return table[name]
        code = event.get("c")
        if code is not None and f"code:{code}" in table:
            return table[f"code:{code}"]
        return None

    def handle(self, event: dict[str, Any], now: float | None = None) -> str | None:
        """Traite un événement ; retourne l'action déclenchée (ou None)."""
        now = time.monotonic() if now is None else now
        self.count += 1
        action = self.resolve(event)
        for cb in list(self.listeners):
            try:
                cb({**event, "action": action, "t": time.time()})
            except Exception:  # un auditeur défaillant ne doit pas bloquer les entrées
                log.exception("Auditeur d'entrées en erreur")
        if action is None:
            log.debug("Touche non mappée : %s", event)
            return None
        if int(event.get("d", 1)):
            if action not in self.held:
                self.backend.press(action)
            self.held[action] = now
        else:
            if action in self.held:
                del self.held[action]
                self.backend.release(action)
        return action

    def expire(self, now: float | None = None) -> list[str]:
        """Relâche les touches maintenues sans nouvelles depuis hold_timeout."""
        now = time.monotonic() if now is None else now
        expired = [a for a, t in self.held.items() if now - t > self.hold_timeout]
        for action in expired:
            del self.held[action]
            self.backend.release(action)
        return expired

    def release_all(self) -> None:
        """Relâche tout (déconnexion de l'app, arrêt du flux...)."""
        for action in list(self.held):
            self.backend.release(action)
        self.held.clear()

    async def watchdog(self) -> None:
        """Tâche de fond : vérifie les touches bloquées toutes les 50 ms."""
        while True:
            await asyncio.sleep(0.05)
            self.expire()
