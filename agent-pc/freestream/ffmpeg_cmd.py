"""Construction des lignes de commande FFmpeg (fonctions pures, testables).

Chaîne : capture (ddagrab/gdigrab/testsrc) -> encodeur matériel basse latence
-> multiplexage MPEG-TS -> transport (UDP/RTP unicast ou multicast, ou HTTP).

Toutes les options visent la latence minimale :
  * pas d'images B (bf=0), débit constant (CBR) avec un tampon VBV de quelques images ;
  * préréglages "ultra low latency" des encodeurs matériels ;
  * multiplexeur TS sans délai (muxdelay/muxpreload=0) et vidage immédiat des paquets ;
  * PAT/PMT et en-têtes répétés souvent pour que le Player puisse "accrocher" à tout moment.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Nom FFmpeg de chaque encodeur selon le codec
ENCODER_NAMES = {
    ("nvenc", "h264"): "h264_nvenc",
    ("nvenc", "hevc"): "hevc_nvenc",
    ("amf", "h264"): "h264_amf",
    ("amf", "hevc"): "hevc_amf",
    ("qsv", "h264"): "h264_qsv",
    ("qsv", "hevc"): "hevc_qsv",
    ("x264", "h264"): "libx264",
    ("x264", "hevc"): "libx265",
}

TRANSPORTS = ("udp", "rtp", "udp-multicast", "rtp-multicast", "http")


@dataclass
class StreamTarget:
    """Destination du flux."""
    mode: str            # un des TRANSPORTS
    player_ip: str = ""  # IP du Player (unicast)
    port: int = 1234
    multicast_group: str = "239.255.42.42"
    pkt_size: int = 1316


def parse_resolution(res: str) -> tuple[int, int] | None:
    """'1280x720' -> (1280, 720) ; 'native' -> None."""
    if not res or res == "native":
        return None
    w, h = res.lower().split("x")
    return int(w), int(h)


def _video_input(source: str, encoder: str, v: dict[str, Any]) -> tuple[list[str], str]:
    """Retourne (arguments d'entrée, chaîne de filtres) pour la capture vidéo.

    La chaîne de filtres se termine par le label [v] qui est mappé en sortie.
    """
    fps = int(v["fps"])
    size = parse_resolution(v.get("resolution", "native"))
    hw_frames_ok = encoder in ("nvenc", "amf")  # acceptent directement les textures D3D11

    if source == "ddagrab":
        # Desktop Duplication API : capture GPU, la plus rapide sous Windows 10/11.
        mouse = 1 if v.get("draw_mouse", True) else 0
        chain = f"ddagrab=output_idx={int(v.get('output_idx', 0))}:framerate={fps}:draw_mouse={mouse}"
        if encoder == "qsv":
            chain += ",hwmap=derive_device=qsv,format=qsv"
            if size:
                chain += f",scale_qsv=w={size[0]}:h={size[1]}"
        elif hw_frames_ok and size is None:
            pass  # zéro copie : la texture va directement à l'encodeur
        else:
            # Redescente en mémoire système pour mise à l'échelle / encodage logiciel.
            chain += ",hwdownload,format=bgra"
            if size:
                chain += f",scale={size[0]}:{size[1]}:flags=fast_bilinear"
            chain += ",format=nv12" if encoder != "x264" else ",format=yuv420p"
        return [], chain + "[v]"

    if source == "gdigrab":
        # GDI : plus lent, mais fonctionne partout (repli).
        args = ["-f", "gdigrab", "-framerate", str(fps), "-draw_mouse",
                "1" if v.get("draw_mouse", True) else "0", "-i", "desktop"]
    elif source == "testsrc":
        # Mire de test animée avec horodatage : pratique pour la Phase 0 sans jeu.
        w, h = size or (1280, 720)
        args = ["-re", "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate={fps}"]
        size = None  # déjà à la bonne taille
    else:
        raise ValueError(f"Source vidéo inconnue : {source}")

    chain = "[0:v]"
    filters = []
    if size:
        filters.append(f"scale={size[0]}:{size[1]}:flags=fast_bilinear")
    if source == "testsrc" and v.get("test_overlay", True):
        # Compteur en millisecondes incrusté (temps du flux)
        filters.append(
            "drawtext=text='%{eif\\:t*1000\\:d} ms':x=40:y=40:fontsize=64:"
            "fontcolor=white:box=1:boxcolor=black@0.6"
        )
    filters.append("format=yuv420p" if encoder == "x264" else "format=nv12")
    if encoder == "qsv":
        filters.append("hwupload=extra_hw_frames=16")
    return args, chain + ",".join(filters) + "[v]"


def _video_encoder(encoder: str, v: dict[str, Any]) -> list[str]:
    """Options d'encodage basse latence propres à chaque encodeur."""
    codec = v.get("codec", "h264")
    name = ENCODER_NAMES[(encoder, codec)]
    kbps = int(v["bitrate_kbps"])
    fps = int(v["fps"])
    gop = int(v.get("gop", fps))
    # Tampon VBV : quelques images seulement -> débit très régulier, latence faible
    bufsize = max(1, int(kbps * int(v.get("vbv_frames", 3)) / fps))
    rate = ["-b:v", f"{kbps}k", "-maxrate", f"{kbps}k", "-bufsize", f"{bufsize}k"]

    if encoder == "nvenc":
        args = ["-c:v", name, "-preset", "p1", "-tune", "ull", "-rc", "cbr",
                *rate, "-g", str(gop), "-bf", "0", "-zerolatency", "1",
                "-delay", "0", "-forced-idr", "1"]
        if v.get("intra_refresh"):
            args += ["-intra-refresh", "1"]
        return args
    if encoder == "amf":
        return ["-c:v", name, "-usage", "ultralowlatency", "-quality", "speed",
                "-rc", "cbr", *rate, "-g", str(gop), "-bf", "0",
                "-header_insertion_mode", "gop"]
    if encoder == "qsv":
        return ["-c:v", name, "-preset", "veryfast", "-look_ahead", "0",
                "-async_depth", "1", *rate, "-g", str(gop), "-bf", "0"]
    if encoder == "x264":
        tune = ["-tune", "zerolatency"]
        extra = ["-x264-params", "repeat-headers=1"] if codec == "h264" else []
        return ["-c:v", name, "-preset", "ultrafast", *tune, *rate,
                "-g", str(gop), "-bf", "0", *extra]
    raise ValueError(f"Encodeur inconnu : {encoder}")


def _audio(a: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(arguments d'entrée, arguments d'encodage) pour l'audio."""
    if not a.get("enabled") or not a.get("device"):
        return [], []
    inp = ["-f", "dshow", "-audio_buffer_size", "20", "-i", f"audio={a['device']}"]
    codec = {"aac": "aac", "mp2": "mp2", "ac3": "ac3"}[a.get("codec", "aac")]
    enc = ["-c:a", codec, "-b:a", f"{int(a.get('bitrate_kbps', 160))}k", "-ar", "48000",
           "-ac", "2", "-af", "aresample=async=1"]
    return inp, enc


def output_url(target: StreamTarget) -> tuple[str, str]:
    """(format FFmpeg, URL de sortie) pour un transport donné."""
    pkt = f"pkt_size={target.pkt_size}"
    if target.mode == "udp":
        return "mpegts", f"udp://{target.player_ip}:{target.port}?{pkt}"
    if target.mode == "rtp":
        return "rtp_mpegts", f"rtp://{target.player_ip}:{target.port}?{pkt}"
    if target.mode == "udp-multicast":
        return "mpegts", f"udp://{target.multicast_group}:{target.port}?{pkt}&ttl=1"
    if target.mode == "rtp-multicast":
        return "rtp_mpegts", f"rtp://{target.multicast_group}:{target.port}?{pkt}&ttl=1"
    if target.mode == "http":
        return "mpegts", "pipe:1"
    raise ValueError(f"Transport inconnu : {target.mode}")


def player_urls(target: StreamTarget, agent_host: str, http_port: int, token: str) -> list[str]:
    """URLs candidates que l'app QML peut passer à MediaPlayer.

    On ne sait pas a priori quelle syntaxe le lecteur du Player accepte :
    la sonde (Phase 0) les essaie toutes et retient celle qui fonctionne.
    """
    p, g = target.port, target.multicast_group
    if target.mode == "udp":
        return [f"udp://@:{p}", f"udp://0.0.0.0:{p}", f"udp://@{target.player_ip}:{p}"]
    if target.mode == "rtp":
        return [f"rtp://@:{p}", f"rtp://0.0.0.0:{p}", f"rtp://@{target.player_ip}:{p}"]
    if target.mode == "udp-multicast":
        return [f"udp://@{g}:{p}", f"udp://{g}:{p}"]
    if target.mode == "rtp-multicast":
        return [f"rtp://@{g}:{p}", f"rtp://{g}:{p}"]
    if target.mode == "http":
        return [f"http://{agent_host}:{http_port}/stream.ts?token={token}"]
    raise ValueError(f"Transport inconnu : {target.mode}")


def build_command(cfg: dict[str, Any], source: str, encoder: str,
                  target: StreamTarget) -> list[str]:
    """Commande FFmpeg complète."""
    v, a = cfg["video"], cfg["audio"]
    vin, vchain = _video_input(source, encoder, v)
    ain, aenc = _audio(a)
    fmt, url = output_url(target)

    cmd = [cfg.get("ffmpeg", "ffmpeg"), "-hide_banner", "-loglevel", "warning"]
    if encoder == "qsv" and source != "ddagrab":
        cmd += ["-init_hw_device", "qsv=hw", "-filter_hw_device", "hw"]
    if vin:
        # Options d'entrée basse latence (ddagrab, lui, n'a pas d'entrée -i)
        cmd += ["-fflags", "nobuffer", "-flags", "low_delay"]
    cmd += vin

    # Index de l'entrée audio : après l'entrée vidéo éventuelle
    audio_index = 1 if vin else 0
    cmd += ain
    cmd += ["-filter_complex", vchain, "-map", "[v]"]
    if ain:
        cmd += ["-map", f"{audio_index}:a"]
    cmd += _video_encoder(encoder, v)
    cmd += aenc
    # Multiplexage MPEG-TS sans délai
    cmd += ["-flush_packets", "1", "-max_delay", "0", "-muxdelay", "0",
            "-muxpreload", "0", "-pat_period", "0.2", "-pcr_period", "20",
            "-f", fmt, url]
    return cmd


def make_target(cfg: dict[str, Any], mode: str | None, player_ip: str) -> StreamTarget:
    """Construit la cible à partir de la config (mode éventuellement forcé)."""
    t = cfg["transport"]
    mode = mode or t["mode"]
    if mode not in TRANSPORTS:
        raise ValueError(f"Transport inconnu : {mode}")
    return StreamTarget(mode=mode, player_ip=player_ip, port=int(t["port"]),
                        multicast_group=t["multicast_group"],
                        pkt_size=int(t["pkt_size"]))
