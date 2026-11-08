"""Client minimal de l'API Freebox OS : appairage, session, AirMedia.

AirMedia permet d'envoyer une URL vidéo au lecteur natif du Freebox Player,
sans aucune application installée sur le Player :
    POST /api/vX/airmedia/receivers/Freebox Player/
    {"action": "start", "media_type": "video", "media": "<url>"}

Authentification Freebox OS (une seule fois) :
  1. POST login/authorize/  -> app_token + track_id
  2. l'utilisateur valide sur l'écran de la Freebox Server
  3. GET login/authorize/<track_id> jusqu'à "granted"
Puis à chaque lancement :
  4. GET login/ -> challenge
  5. POST login/session/ avec password = HMAC-SHA1(app_token, challenge)
  6. en-tête X-Fbx-App-Auth: <session_token> sur toutes les requêtes
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import socket
from pathlib import Path
from typing import Any
from urllib.parse import quote

import aiohttp

from . import __version__

log = logging.getLogger("freestream.freebox")

APP_ID = "fr.freestream.agent"
APP_NAME = "FreeStream"
DEFAULT_HOST = "http://mafreebox.freebox.fr"

# Messages en français pour les erreurs courantes de l'API
ERRORS = {
    "insufficient_rights": "droits insuffisants : dans Freebox OS, ouvrez Paramètres de la Freebox → "
                           "Gestion des accès → Applications, et cochez les permissions de « FreeStream »",
    "auth_required": "session expirée ou absente",
    "invalid_token": "jeton d'application invalide : relancez l'appairage (--freebox-pair)",
    "pending_token": "l'appairage n'a pas encore été validé sur l'écran de la Freebox Server",
    "denied_from_external_ip": "accès refusé depuis l'extérieur : le PC doit être sur le réseau de la Freebox",
    "invalid_request": "requête invalide",
    "ratelimited": "trop de tentatives, patientez quelques minutes",
    "unknown_receiver": "récepteur AirMedia introuvable : vérifiez que le Player est allumé et qu'AirMedia est activé",
    "invalid_action": "action AirMedia refusée par le Player",
    "not_implemented": "fonction non disponible sur ce modèle",
}


class FreeboxError(Exception):
    """Erreur renvoyée par Freebox OS (message traduit en français)."""

    def __init__(self, code: str, msg: str = ""):
        self.code = code
        text = ERRORS.get(code, msg or code)
        super().__init__(f"{text} [{code}]")


class FreeboxClient:
    def __init__(self, session: aiohttp.ClientSession, host: str = DEFAULT_HOST,
                 token_file: Path | None = None):
        self.http = session
        self.host = host.rstrip("/")
        self.token_file = token_file
        self.base = ""            # ex : http://mafreebox.freebox.fr/api/v8/
        self.app_token = ""
        self.session_token = ""
        self.device_name = ""

    # ---------- bas niveau ----------
    async def discover(self) -> str:
        """Lit /api_version et construit l'URL de base de l'API."""
        async with self.http.get(f"{self.host}/api_version") as r:
            info = await r.json(content_type=None)
        major = str(info.get("api_version", "4.0")).split(".")[0]
        self.base = f"{self.host}{info.get('api_base_url', '/api/')}v{major}/"
        self.device_name = info.get("device_name", "Freebox")
        log.info("Freebox détectée : %s (API v%s)", self.device_name, major)
        return self.base

    async def _call(self, method: str, path: str, body: dict | None = None,
                    auth: bool = True) -> Any:
        if not self.base:
            await self.discover()
        headers = {"X-Fbx-App-Auth": self.session_token} if auth and self.session_token else {}
        async with self.http.request(method, self.base + path, json=body, headers=headers) as r:
            try:
                data = await r.json(content_type=None)
            except (ValueError, aiohttp.ContentTypeError):
                raise FreeboxError("invalid_request", f"réponse non JSON (HTTP {r.status})")
        if not data.get("success"):
            raise FreeboxError(data.get("error_code", "unknown"), data.get("msg", ""))
        return data.get("result")

    # ---------- jeton d'application ----------
    def load_token(self) -> bool:
        if not self.token_file or not self.token_file.exists():
            return False
        try:
            self.app_token = json.loads(self.token_file.read_text(encoding="utf-8"))["app_token"]
            return bool(self.app_token)
        except (OSError, ValueError, KeyError):
            return False

    def save_token(self) -> None:
        if self.token_file:
            self.token_file.write_text(json.dumps({"app_id": APP_ID, "app_token": self.app_token}),
                                       encoding="utf-8")

    async def authorize(self, poll_interval: float = 1.0, timeout: float = 120) -> str:
        """Demande l'autorisation ; l'utilisateur valide sur la Freebox Server."""
        res = await self._call("POST", "login/authorize/", {
            "app_id": APP_ID, "app_name": APP_NAME, "app_version": __version__,
            "device_name": socket.gethostname(),
        }, auth=False)
        token, track = res["app_token"], res["track_id"]
        print(">>> Validez la demande « FreeStream » sur l'écran de la Freebox Server "
              "(avec les boutons ou l'écran tactile de la façade)…")
        waited = 0.0
        while waited < timeout:
            st = await self._call("GET", f"login/authorize/{track}", auth=False)
            status = st.get("status")
            if status == "granted":
                self.app_token = token
                self.save_token()
                return token
            if status in ("denied", "timeout"):
                raise FreeboxError(status, "appairage refusé" if status == "denied"
                                   else "délai de validation dépassé")
            await asyncio.sleep(poll_interval)
            waited += poll_interval
        raise FreeboxError("timeout", "délai de validation dépassé")

    async def open_session(self) -> dict:
        """Ouvre une session avec le jeton enregistré."""
        if not self.app_token and not self.load_token():
            raise FreeboxError("no_token", "pas encore appairé : lancez d'abord --freebox-pair")
        login = await self._call("GET", "login/", auth=False)
        password = hmac.new(self.app_token.encode(), login["challenge"].encode(),
                            hashlib.sha1).hexdigest()
        res = await self._call("POST", "login/session/",
                               {"app_id": APP_ID, "password": password}, auth=False)
        self.session_token = res["session_token"]
        return res.get("permissions", {})

    # ---------- AirMedia ----------
    async def receivers(self) -> list[dict]:
        return await self._call("GET", "airmedia/receivers/") or []

    async def cast(self, url: str, receiver: str = "Freebox Player", password: str = "") -> None:
        """Demande au Player de lire l'URL vidéo."""
        await self._call("POST", f"airmedia/receivers/{quote(receiver)}/", {
            "action": "start", "media_type": "video", "media": url, "password": password})

    async def stop(self, receiver: str = "Freebox Player", password: str = "") -> None:
        await self._call("POST", f"airmedia/receivers/{quote(receiver)}/", {
            "action": "stop", "media_type": "video", "password": password})
