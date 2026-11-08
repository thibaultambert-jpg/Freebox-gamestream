"""Détection des encodeurs vidéo réellement utilisables sur ce PC.

`ffmpeg -encoders` liste les encodeurs compilés, pas ceux qui fonctionnent
(pilote absent, mauvaise carte...). On fait donc un vrai essai d'encodage
de quelques images noires avec chaque encodeur matériel.
"""
from __future__ import annotations

import subprocess

from .ffmpeg_cmd import ENCODER_NAMES

# Ordre de préférence : matériel d'abord (latence et charge CPU minimales)
PREFERENCE = ("nvenc", "amf", "qsv", "x264")


def test_encoder(ffmpeg: str, encoder: str, codec: str = "h264", timeout: float = 15) -> bool:
    """Encode 5 images de test ; True si FFmpeg réussit."""
    name = ENCODER_NAMES[(encoder, codec)]
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error",
           "-f", "lavfi", "-i", "color=black:s=320x240:r=30",
           "-frames:v", "5", "-pix_fmt", "nv12" if encoder != "x264" else "yuv420p",
           "-c:v", name, "-f", "null", "-"]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return res.returncode == 0


def detect_encoders(ffmpeg: str, codec: str = "h264") -> list[str]:
    """Liste des encodeurs fonctionnels, par ordre de préférence."""
    return [e for e in PREFERENCE if test_encoder(ffmpeg, e, codec)]


def choose_encoder(ffmpeg: str, wanted: str, codec: str = "h264") -> str:
    """Encodeur à utiliser : celui demandé, ou le meilleur disponible si 'auto'."""
    if wanted != "auto":
        return wanted
    found = detect_encoders(ffmpeg, codec)
    if not found:
        raise RuntimeError(
            "Aucun encodeur vidéo fonctionnel. Vérifiez que FFmpeg est installé "
            "et dans le PATH (ou renseignez \"ffmpeg\" dans la config)."
        )
    return found[0]
