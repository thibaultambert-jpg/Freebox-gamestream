"""Tests de la construction des commandes FFmpeg."""
import copy

import pytest

from freestream.config import DEFAULT_CONFIG
from freestream.ffmpeg_cmd import build_command, make_target, player_urls, TRANSPORTS


def cfg(**video):
    c = copy.deepcopy(DEFAULT_CONFIG)
    c["video"].update(video)
    return c


def test_nvenc_ddagrab_native_zero_copy():
    c = cfg(resolution="native")
    cmd = build_command(c, "ddagrab", "nvenc", make_target(c, "udp", "192.168.1.20"))
    chain = cmd[cmd.index("-filter_complex") + 1]
    assert chain.startswith("ddagrab=") and "hwdownload" not in chain
    assert "h264_nvenc" in cmd and "-bf" in cmd and cmd[cmd.index("-bf") + 1] == "0"
    assert cmd[-1] == "udp://192.168.1.20:1234?pkt_size=1316"
    assert cmd[-2] == "mpegts"


def test_ddagrab_scaling_downloads_frames():
    c = cfg(resolution="1280x720")
    cmd = build_command(c, "ddagrab", "nvenc", make_target(c, "udp", "1.2.3.4"))
    chain = cmd[cmd.index("-filter_complex") + 1]
    assert "hwdownload" in chain and "scale=1280:720" in chain and chain.endswith("[v]")


def test_qsv_uses_scale_qsv():
    c = cfg(resolution="1920x1080")
    cmd = build_command(c, "ddagrab", "qsv", make_target(c, "rtp", "1.2.3.4"))
    chain = cmd[cmd.index("-filter_complex") + 1]
    assert "scale_qsv=w=1920:h=1080" in chain
    assert cmd[-2] == "rtp_mpegts"


@pytest.mark.parametrize("mode", TRANSPORTS)
def test_all_transports(mode):
    c = cfg()
    t = make_target(c, mode, "192.168.1.20")
    cmd = build_command(c, "testsrc", "x264", t)
    assert "libx264" in cmd
    urls = player_urls(t, "192.168.1.10", 8765, "tok")
    assert urls
    if mode == "http":
        assert cmd[-1] == "pipe:1" and urls[0].endswith("token=tok")
    if "multicast" in mode:
        assert "239.255.42.42" in cmd[-1] and "ttl=1" in cmd[-1]


def test_bufsize_is_few_frames():
    c = cfg(bitrate_kbps=12000, fps=60, vbv_frames=3)
    cmd = build_command(c, "testsrc", "nvenc", make_target(c, "udp", "1.2.3.4"))
    assert cmd[cmd.index("-bufsize") + 1] == "600k"


def test_audio_mapping():
    c = cfg()
    c["audio"].update(enabled=True, device="CABLE Output")
    cmd = build_command(c, "ddagrab", "nvenc", make_target(c, "udp", "1.2.3.4"))
    assert "audio=CABLE Output" in cmd
    # ddagrab n'a pas d'entrée -i : l'audio est l'entrée 0
    assert cmd[cmd.index("-map", cmd.index("-map") + 1) + 1] == "0:a"
    cmd = build_command(c, "gdigrab", "nvenc", make_target(c, "udp", "1.2.3.4"))
    assert "1:a" in cmd


def test_unknown_transport():
    with pytest.raises(ValueError):
        make_target(cfg(), "carrier-pigeon", "1.2.3.4")
