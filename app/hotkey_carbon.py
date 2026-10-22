"""Real global hotkeys on macOS, via Carbon's RegisterEventHotKey.

This is the API macOS actually provides for system-wide shortcuts, and it is
better than watching the keyboard in two important ways:

* It **consumes** the keystroke. A watcher like pynput only observes, so the
  foreground app still receives the key — press a shortcut over a browser and
  the browser acts on it too.
* It needs **no Accessibility permission**. Key watchers do, because they can
  see everything you type; a registered hotkey only ever reports itself.

Reached through ctypes rather than pyobjc, so there is no extra dependency.
Import never raises: on failure the caller falls back to the watcher.
"""
import ctypes
import ctypes.util
import sys

AVAILABLE = False
_error = None

# Every Carbon function this module calls. Checked at import, because
# "the library loaded" is not the same as "the library can do this".
#
# Carbon is old and Apple has been hollowing it out for years. A symbol
# that goes missing does not announce itself: ctypes raises AttributeError
# at the moment of use, deep inside a watcher process whose stderr nobody
# reads, and what the person sees is a shortcut that registers perfectly
# and never fires. Finding out up front turns that into one line in the
# log and a fall back to the other backend.
NEEDED = ("RegisterEventHotKey", "InstallEventHandler",
          "GetApplicationEventTarget", "GetEventParameter",
          "RunApplicationEventLoop", "TransformProcessType")

missing = ()

if sys.platform == "darwin":
    try:
        _carbon_path = ctypes.util.find_library("Carbon")
        carbon = ctypes.CDLL(_carbon_path) if _carbon_path else None
        core = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
        if carbon is not None:
            missing = tuple(name for name in NEEDED
                            if not hasattr(carbon, name))
            AVAILABLE = not missing
            if missing:
                _error = "Carbon is missing %s" % ", ".join(missing)
    except Exception as exc:      # pragma: no cover - macOS only
        _error = exc
        carbon = core = None
else:
    carbon = core = None
    _error = "not macOS"


# Carbon modifier masks (Events.h)
CMD_KEY = 0x0100
SHIFT_KEY = 0x0200
OPTION_KEY = 0x0800
CONTROL_KEY = 0x1000

MODIFIER_MASKS = {
    "cmd": CMD_KEY, "win": CMD_KEY, "super": CMD_KEY,
    "shift": SHIFT_KEY,
    "alt": OPTION_KEY, "option": OPTION_KEY,
    "ctrl": CONTROL_KEY, "control": CONTROL_KEY,
}

# Virtual key codes (kVK_ANSI_*, Events.h). These are positional codes, not
# characters — they do not change with the keyboard layout.
KEY_CODES = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05,
    "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C,
    "w": 0x0D, "e": 0x0E, "r": 0x0F, "y": 0x10, "t": 0x11, "1": 0x12,
    "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "=": 0x18,
    "9": 0x19, "7": 0x1A, "-": 0x1B, "8": 0x1C, "0": 0x1D, "]": 0x1E,
    "o": 0x1F, "u": 0x20, "[": 0x21, "i": 0x22, "p": 0x23, "l": 0x25,
    "j": 0x26, "'": 0x27, "k": 0x28, ";": 0x29, "\\": 0x2A, ",": 0x2B,
    "/": 0x2C, "n": 0x2D, "m": 0x2E, ".": 0x2F, "`": 0x32,
    "space": 0x31, "return": 0x24, "enter": 0x24, "tab": 0x30,
    "delete": 0x33, "backspace": 0x33, "escape": 0x35, "esc": 0x35,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60,
    "f6": 0x61, "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D,
    "f11": 0x67, "f12": 0x6F, "f13": 0x69, "f14": 0x6B, "f15": 0x71,
    "f16": 0x6A, "f17": 0x40, "f18": 0x4F, "f19": 0x50, "f20": 0x5A,
    "home": 0x73, "end": 0x77, "pageup": 0x74, "pagedown": 0x79,
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
}


def translate_spec(spec):
    """'ctrl+cmd+t' -> (modifier_mask, key_code). Raises ValueError."""
    parts = [p.strip().lower() for p in str(spec).split("+") if p.strip()]
    mask, key = 0, None
    for part in parts:
        if part in MODIFIER_MASKS:
            mask |= MODIFIER_MASKS[part]
        elif key is None:
            key = part
        else:
            raise ValueError("more than one non-modifier key: %s" % spec)
    if key is None:
        raise ValueError("hotkey needs a normal key")
    if key not in KEY_CODES:
        raise ValueError("unsupported key on macOS: %s" % key)
    if not mask:
        raise ValueError("hotkey needs at least one modifier")
    return mask, KEY_CODES[key]


class ProcessSerialNumber(ctypes.Structure):
    _fields_ = [("highLongOfPSN", ctypes.c_uint32),
                ("lowLongOfPSN", ctypes.c_uint32)]


K_CURRENT_PROCESS = 2
K_PROCESS_TRANSFORM_TO_UI_ELEMENT = 4


def become_ui_element():
    """Give this process a window-server connection, without a Dock icon.

    RegisterEventHotKey returns success in *any* process, which is a trap: a
    plain command-line process has no connection to the window server, so the
    hotkey is registered and then never fires. Nothing reports an error —
    exactly the "shortcut does nothing" symptom.

    TransformProcessType promotes the process to a UI element: enough to
    receive events, but no Dock icon and no menu bar, which is right for a
    background listener.

    Returns 0 on success, or a negative OSStatus. Never raises.
    """
    if not AVAILABLE:
        return -1
    try:
        carbon.TransformProcessType.argtypes = [
            ctypes.POINTER(ProcessSerialNumber), ctypes.c_uint32]
        carbon.TransformProcessType.restype = ctypes.c_int32
        psn = ProcessSerialNumber(0, K_CURRENT_PROCESS)
        return int(carbon.TransformProcessType(
            ctypes.byref(psn), K_PROCESS_TRANSFORM_TO_UI_ELEMENT))
    except Exception:
        return -2


class EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32),
                ("eventKind", ctypes.c_uint32)]


class EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


K_EVENT_CLASS_KEYBOARD = 0x6B657962      # 'keyb'
K_EVENT_HOTKEY_PRESSED = 5
K_EVENT_HOTKEY_RELEASED = 6
K_EVENT_PARAM_DIRECT_OBJECT = 0x2D2D2D2D  # '----'
TYPE_EVENT_HOTKEY_ID = 0x686B6964         # 'hkid'
SIGNATURE = 0x534E5054                     # 'SNPT'

HANDLER = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p,
                           ctypes.c_void_p)


def listen(spec_map, on_fire, on_ready=None, on_release=None):
    """Register hotkeys and run the Carbon event loop. Blocks forever.

    `spec_map` is {id: spec}; `on_fire(id)` is called on each press.
    `on_ready(refused, ui_status)` is called once registration is done, with
    the list of ids macOS would not accept — a shortcut another app already
    owns registers as a failure here and nowhere else. Without it the app
    said "Shortcuts active: CMD+E" about a shortcut that had been refused,
    which is why pressing it did nothing.

    `ui_status` is what `become_ui_element` returned. 0 is a window-server
    connection; anything else is a process that can register a hotkey and
    will never be told it was pressed.
    Raises RuntimeError if Carbon is unusable or nothing could be registered.
    """
    if not AVAILABLE:
        raise RuntimeError("Carbon unavailable: %s" % (_error or "unknown"))

    # Must happen before registering: a process with no window-server
    # connection registers hotkeys that never fire.
    #
    # The result used to be thrown away — in the one function whose own
    # docstring says that ignoring this produces a shortcut that registers
    # cleanly and never fires. That is precisely the fault that then had to
    # be chased, and the number that would have named it in a second had
    # been computed and dropped on the floor. It is reported now.
    ui_status = become_ui_element()

    carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
    carbon.RegisterEventHotKey.argtypes = [
        ctypes.c_uint32, ctypes.c_uint32, EventHotKeyID, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
    carbon.RegisterEventHotKey.restype = ctypes.c_int32
    carbon.GetEventParameter.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
    carbon.GetEventParameter.restype = ctypes.c_int32
    carbon.GetEventKind.argtypes = [ctypes.c_void_p]
    carbon.GetEventKind.restype = ctypes.c_uint32

    ids = {}

    def handler(_next_handler, event, _user_data):
        hotkey_id = EventHotKeyID()
        status = carbon.GetEventParameter(
            event, K_EVENT_PARAM_DIRECT_OBJECT, TYPE_EVENT_HOTKEY_ID,
            None, ctypes.sizeof(hotkey_id), None, ctypes.byref(hotkey_id))
        if status == 0:
            key = ids.get(int(hotkey_id.id))
            if key is not None:
                try:
                    kind = int(carbon.GetEventKind(event))
                except Exception:
                    kind = K_EVENT_HOTKEY_PRESSED
                try:
                    if kind == K_EVENT_HOTKEY_RELEASED:
                        # The shortcut let go: what tells a tap from a
                        # hold for certain (main.snip_key_pressed). The
                        # key's state read afterwards cannot - a quick tap
                        # is over before it is first read.
                        if on_release is not None:
                            on_release(key)
                    else:
                        on_fire(key)
                except Exception:
                    pass
        return 0

    callback = HANDLER(handler)
    kinds = [K_EVENT_HOTKEY_PRESSED]
    if on_release is not None:
        kinds.append(K_EVENT_HOTKEY_RELEASED)
    specs = (EventTypeSpec * len(kinds))(
        *[EventTypeSpec(K_EVENT_CLASS_KEYBOARD, k) for k in kinds])
    target = carbon.GetApplicationEventTarget()
    result = carbon.InstallEventHandler(
        ctypes.c_void_p(target), callback, len(kinds), specs, None, None)
    if result != 0:
        raise RuntimeError("InstallEventHandler failed (%d)" % result)

    registered, refused = 0, []
    for index, (key, spec_text) in enumerate(spec_map.items(), start=1):
        try:
            mask, code = translate_spec(spec_text)
        except ValueError:
            refused.append(key)
            continue
        hotkey_id = EventHotKeyID(SIGNATURE, index)
        ref = ctypes.c_void_p()
        status = carbon.RegisterEventHotKey(
            code, mask, hotkey_id, ctypes.c_void_p(target), 0,
            ctypes.byref(ref))
        if status == 0:
            ids[index] = key
            registered += 1
        else:
            refused.append(key)
    if on_ready is not None:
        try:
            on_ready(refused, ui_status)
        except TypeError:
            on_ready(refused)          # an older caller
        except Exception:
            pass
    if not registered:
        raise RuntimeError("no hotkeys could be registered")

    # Keep a reference so the callback is not collected while in use.
    listen._callback = callback

    # RunApplicationEventLoop, not CFRunLoopRun. Hotkey presses arrive on the
    # *Carbon event queue*; a bare CoreFoundation run loop spins happily
    # without ever draining it, so the handler installed above is never
    # called. This is the loop that dispatches them.
    #
    # Which is why the old `except AttributeError: core.CFRunLoopRun()` is
    # gone. If RunApplicationEventLoop is not there, that fallback did the
    # one thing this comment says does not work — quietly, forever, with
    # every shortcut registering successfully and none of them ever firing,
    # and no error anywhere to say so. A missing symbol here is now a
    # failure, so the caller falls back to the key watcher, which needs a
    # permission but does deliver.
    try:
        carbon.RunApplicationEventLoop.restype = None
        carbon.RunApplicationEventLoop()
    except AttributeError:
        raise RuntimeError(
            "Carbon has no RunApplicationEventLoop on this macOS, so a "
            "registered hotkey would never be delivered")
