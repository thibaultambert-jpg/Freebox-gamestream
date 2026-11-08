"""Back-ends d'injection d'entrées sur le PC.

* VigemBackend     : manette Xbox 360 virtuelle via ViGEmBus (paquet Python `vgamepad`).
* SendInputBackend : clavier Windows via l'API SendInput (scancodes, compatible DirectInput).
* LogBackend       : n'injecte rien, affiche les actions (tests, Linux, débogage).
"""
from __future__ import annotations

import ctypes
import logging
import platform

log = logging.getLogger("freestream.input")

# Directions du stick gauche pour les actions pad:LSTICK_*
STICK_DIRS = {
    "LSTICK_UP": (0.0, 1.0), "LSTICK_DOWN": (0.0, -1.0),
    "LSTICK_LEFT": (-1.0, 0.0), "LSTICK_RIGHT": (1.0, 0.0),
    "LSTICK_UPLEFT": (-0.7, 0.7), "LSTICK_UPRIGHT": (0.7, 0.7),
    "LSTICK_DOWNLEFT": (-0.7, -0.7), "LSTICK_DOWNRIGHT": (0.7, -0.7),
}
TRIGGERS = ("LT", "RT")
PAD_BUTTONS = ("A", "B", "X", "Y", "LB", "RB", "START", "BACK", "GUIDE", "LS", "RS",
               "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT")

# Scancodes (jeu 1) des touches usuelles ; le bit 0xE000 signale une touche étendue.
SCANCODES = {
    "ESC": 0x01, "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06, "6": 0x07,
    "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B, "BACKSPACE": 0x0E, "TAB": 0x0F,
    "Q": 0x10, "W": 0x11, "E": 0x12, "R": 0x13, "T": 0x14, "Y": 0x15, "U": 0x16,
    "I": 0x17, "O": 0x18, "P": 0x19, "ENTER": 0x1C, "LCTRL": 0x1D, "A": 0x1E,
    "S": 0x1F, "D": 0x20, "F": 0x21, "G": 0x22, "H": 0x23, "J": 0x24, "K": 0x25,
    "L": 0x26, "LSHIFT": 0x2A, "Z": 0x2C, "X": 0x2D, "C": 0x2E, "V": 0x2F,
    "B": 0x30, "N": 0x31, "M": 0x32, "SPACE": 0x39, "LALT": 0x38,
    "F1": 0x3B, "F2": 0x3C, "F3": 0x3D, "F4": 0x3E, "F5": 0x3F, "F6": 0x40,
    "F7": 0x41, "F8": 0x42, "F9": 0x43, "F10": 0x44, "F11": 0x57, "F12": 0x58,
    "UP": 0xE048, "DOWN": 0xE050, "LEFT": 0xE04B, "RIGHT": 0xE04D,
    "PAGEUP": 0xE049, "PAGEDOWN": 0xE051, "HOME": 0xE047, "END": 0xE04F,
    "INSERT": 0xE052, "DELETE": 0xE053, "LWIN": 0xE05B,
}


class Backend:
    """Interface commune : press/release d'une action ('pad:A', 'key:SPACE'...)."""
    name = "base"

    def press(self, action: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def release(self, action: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def close(self) -> None:
        pass


class LogBackend(Backend):
    name = "log"

    def __init__(self) -> None:
        self.history: list[tuple[str, str]] = []

    def press(self, action: str) -> None:
        self.history.append(("press", action))
        log.info("[simulé] appui   %s", action)

    def release(self, action: str) -> None:
        self.history.append(("release", action))
        log.info("[simulé] relâche %s", action)


class VigemBackend(Backend):
    """Manette Xbox 360 virtuelle (nécessite le pilote ViGEmBus + `pip install vgamepad`)."""
    name = "vigem"

    def __init__(self) -> None:
        import vgamepad as vg  # import tardif : module Windows uniquement
        self.vg = vg
        self.pad = vg.VX360Gamepad()
        self.held_dirs: list[str] = []
        B = vg.XUSB_BUTTON
        self.buttons = {
            "A": B.XUSB_GAMEPAD_A, "B": B.XUSB_GAMEPAD_B, "X": B.XUSB_GAMEPAD_X,
            "Y": B.XUSB_GAMEPAD_Y, "LB": B.XUSB_GAMEPAD_LEFT_SHOULDER,
            "RB": B.XUSB_GAMEPAD_RIGHT_SHOULDER, "START": B.XUSB_GAMEPAD_START,
            "BACK": B.XUSB_GAMEPAD_BACK, "GUIDE": B.XUSB_GAMEPAD_GUIDE,
            "LS": B.XUSB_GAMEPAD_LEFT_THUMB, "RS": B.XUSB_GAMEPAD_RIGHT_THUMB,
            "DPAD_UP": B.XUSB_GAMEPAD_DPAD_UP, "DPAD_DOWN": B.XUSB_GAMEPAD_DPAD_DOWN,
            "DPAD_LEFT": B.XUSB_GAMEPAD_DPAD_LEFT, "DPAD_RIGHT": B.XUSB_GAMEPAD_DPAD_RIGHT,
        }

    def _apply_stick(self) -> None:
        # Le dernier sens enfoncé l'emporte ; aucun sens -> stick au centre
        x, y = STICK_DIRS[self.held_dirs[-1]] if self.held_dirs else (0.0, 0.0)
        self.pad.left_joystick_float(x_value_float=x, y_value_float=y)

    def _set(self, btn: str, down: bool) -> None:
        if btn in self.buttons:
            (self.pad.press_button if down else self.pad.release_button)(button=self.buttons[btn])
        elif btn in TRIGGERS:
            fn = self.pad.left_trigger_float if btn == "LT" else self.pad.right_trigger_float
            fn(value_float=1.0 if down else 0.0)
        elif btn in STICK_DIRS:
            if btn in self.held_dirs:
                self.held_dirs.remove(btn)
            if down:
                self.held_dirs.append(btn)
            self._apply_stick()
        else:
            log.warning("Bouton de manette inconnu : %s", btn)
            return
        self.pad.update()

    def press(self, action: str) -> None:
        self._set(action.split(":", 1)[1], True)

    def release(self, action: str) -> None:
        self._set(action.split(":", 1)[1], False)

    def close(self) -> None:
        self.pad.reset()
        self.pad.update()


class SendInputBackend(Backend):
    """Clavier Windows par scancodes (fonctionne aussi dans la plupart des jeux)."""
    name = "sendinput"

    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008

    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("SendInput n'existe que sous Windows")
        from ctypes import wintypes

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_size_t)]

        class MOUSEINPUT(ctypes.Structure):  # nécessaire pour la taille de l'union
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class _U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        self.KEYBDINPUT, self.INPUT, self._U = KEYBDINPUT, INPUT, _U
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)

    def _send(self, key: str, up: bool) -> None:
        code = SCANCODES.get(key.upper())
        if code is None:
            log.warning("Touche clavier inconnue : %s", key)
            return
        flags = self.KEYEVENTF_SCANCODE
        if code & 0xE000:
            flags |= self.KEYEVENTF_EXTENDEDKEY
        if up:
            flags |= self.KEYEVENTF_KEYUP
        ki = self.KEYBDINPUT(0, code & 0xFF, flags, 0, 0)
        inp = self.INPUT(1, self._U(ki=ki))  # 1 = INPUT_KEYBOARD
        self.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    def press(self, action: str) -> None:
        self._send(action.split(":", 1)[1], False)

    def release(self, action: str) -> None:
        self._send(action.split(":", 1)[1], True)


class RouterBackend(Backend):
    """Aiguille 'pad:*' vers la manette et 'key:*' vers le clavier."""

    def __init__(self, pad: Backend | None, keyboard: Backend | None, fallback: Backend):
        self.pad, self.keyboard, self.fallback = pad, keyboard, fallback
        self.name = "+".join(b.name for b in (pad, keyboard) if b) or fallback.name

    def _pick(self, action: str) -> Backend:
        if action.startswith("pad:") and self.pad:
            return self.pad
        if action.startswith("key:") and self.keyboard:
            return self.keyboard
        return self.fallback

    def press(self, action: str) -> None:
        self._pick(action).press(action)

    def release(self, action: str) -> None:
        self._pick(action).release(action)

    def close(self) -> None:
        for b in (self.pad, self.keyboard):
            if b:
                b.close()


def create_backend(kind: str) -> Backend:
    """Instancie le back-end demandé ('auto' = tout ce qui est disponible)."""
    if kind == "log":
        return LogBackend()
    pad = kb = None
    if kind in ("auto", "vigem"):
        try:
            pad = VigemBackend()
        except Exception as exc:  # pilote absent, module absent, non-Windows...
            log.warning("Manette virtuelle indisponible (%s). Installez ViGEmBus + vgamepad.", exc)
    if kind in ("auto", "sendinput"):
        try:
            kb = SendInputBackend()
        except Exception as exc:
            log.warning("Clavier SendInput indisponible (%s).", exc)
    if not pad and not kb:
        log.warning("Aucun back-end réel : les entrées seront seulement journalisées.")
    return RouterBackend(pad, kb, LogBackend())
