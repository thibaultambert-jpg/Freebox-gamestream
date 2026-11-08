"""Tests du mapping des touches et du relâchement automatique."""
from freestream.config import DEFAULT_PROFILES
from freestream.inputs import InputMapper, LogBackend


def mapper(timeout=600):
    b = LogBackend()
    return InputMapper(b, DEFAULT_PROFILES, "manette", timeout), b


def test_press_release():
    m, b = mapper()
    assert m.handle({"k": "Select", "d": 1}, now=0) == "pad:A"
    m.handle({"k": "Select", "d": 1, "r": 1}, now=0.05)  # répétition : pas de double appui
    m.handle({"k": "Select", "d": 0}, now=0.1)
    assert b.history == [("press", "pad:A"), ("release", "pad:A")]


def test_auto_release_when_remote_sends_no_keyup():
    m, b = mapper(timeout=600)
    m.handle({"k": "Up", "d": 1}, now=0)
    assert m.expire(now=0.5) == []
    m.handle({"k": "Up", "d": 1, "r": 1}, now=0.5)   # maintien : rafraîchit le délai
    assert m.expire(now=1.0) == []
    assert m.expire(now=1.2) == ["pad:DPAD_UP"]
    assert b.history[-1] == ("release", "pad:DPAD_UP")


def test_unknown_key_by_code():
    b = LogBackend()
    m = InputMapper(b, {"p": {"code:42": "key:SPACE"}}, "p")
    assert m.handle({"k": "code:42", "c": 42, "d": 1}) == "key:SPACE"
    assert m.handle({"k": "Nope", "c": 7, "d": 1}) is None


def test_listeners_and_release_all():
    m, b = mapper()
    seen = []
    m.listeners.append(seen.append)
    m.handle({"k": "Red", "d": 1})
    m.release_all()
    assert seen[0]["action"] == "pad:X"
    assert b.history == [("press", "pad:X"), ("release", "pad:X")]
