"""Is a key still held down? For shortcuts that act while held.

A registered shortcut reports the press and nothing more — neither
Windows' RegisterHotKey nor macOS' Carbon hotkeys say when the key comes
back up. Hold-to-see needs exactly that, so after the press this is asked,
a few dozen times a second, whether the shortcut's letter is still down.

Windows answers from GetAsyncKeyState. macOS answers from the window
server's own key table (CGEventSourceKeyState), which is read, not
listened to, and needs no permission of its own. Anywhere else, or if the
question cannot be asked, the answer is None and the caller treats the
press as a toggle instead.
"""
import sys

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

_mac = {"fn": None, "flags": None, "tried": False}

# Which state macOS is asked for: 1, the keyboard itself. It was 0, the
# session's view of the keys, which is built from the key events delivered
# to apps - and a key press taken as a registered shortcut is not delivered
# to anyone. So while another app was in front, the letter of the shortcut
# read as up from the moment it was pressed, and holding it snipped; once
# Squint was in front (after that snip) the same hold worked.
HID_STATE = 1

# Windows virtual keys, and macOS modifier flags, for each modifier name.
_WIN_MODS = {"ctrl": 0x11, "control": 0x11, "alt": 0x12, "option": 0x12,
             "shift": 0x10, "cmd": 0x5B, "win": 0x5B, "super": 0x5B}
_MAC_FLAGS = {"shift": 0x20000, "ctrl": 0x40000, "control": 0x40000,
              "alt": 0x80000, "option": 0x80000, "cmd": 0x100000,
              "win": 0x100000, "super": 0x100000}


def _key_of(spec):
    parts = [p.strip().lower() for p in str(spec or "").split("+")
             if p.strip()]
    mods = {"ctrl", "control", "alt", "option", "shift", "cmd", "win",
            "super"}
    keys = [p for p in parts if p not in mods]
    return keys[0] if keys else None


def _mac_reader():
    if _mac["tried"]:
        return _mac["fn"]
    _mac["tried"] = True
    try:
        import ctypes
        import ctypes.util
        path = ctypes.util.find_library("ApplicationServices") or \
            ctypes.util.find_library("CoreGraphics")
        lib = ctypes.cdll.LoadLibrary(path)
        fn = lib.CGEventSourceKeyState
        fn.argtypes = [ctypes.c_int32, ctypes.c_uint16]
        fn.restype = ctypes.c_bool
        _mac["fn"] = fn
        flags = lib.CGEventSourceFlagsState
        flags.argtypes = [ctypes.c_int32]
        flags.restype = ctypes.c_uint64
        _mac["flags"] = flags
    except Exception:
        _mac["fn"] = None
    return _mac["fn"]


def is_down(spec):
    """True/False for the shortcut's main key, or None if unknown."""
    key = _key_of(spec)
    if not key:
        return None
    try:
        if IS_WINDOWS:
            import ctypes
            from . import hotkey
            _mods, vk = hotkey.parse(spec)
            return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
        if IS_MAC:
            from .hotkey_carbon import KEY_CODES
            code = KEY_CODES.get(key)
            fn = _mac_reader()
            if code is None or fn is None:
                return None
            return bool(fn(HID_STATE, code))
    except Exception:
        return None
    return None


def _modifiers_of(spec):
    return [p.strip().lower() for p in str(spec or "").split("+")
            if p.strip().lower() in _WIN_MODS]


def modifiers_down(spec):
    """True if any of the shortcut's modifiers is still held, False if none
    is, None if it cannot be told."""
    mods = _modifiers_of(spec)
    if not mods:
        return None
    try:
        if IS_WINDOWS:
            import ctypes
            state = ctypes.windll.user32.GetAsyncKeyState
            return any(state(_WIN_MODS[m]) & 0x8000 for m in mods)
        if IS_MAC:
            _mac_reader()
            flags = _mac["flags"]
            if flags is None:
                return None
            current = int(flags(HID_STATE))
            return any(current & _MAC_FLAGS[m] for m in mods)
    except Exception:
        return None
    return None
