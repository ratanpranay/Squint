"""Global hotkeys.

Two implementations behind one interface:

* Windows uses the raw RegisterHotKey API — no admin rights, no polling, and
  Windows itself guarantees delivery from any foreground app.
* macOS has no equivalent, so it uses pynput's global listener, which sits on
  a Quartz event tap. That requires the user to grant Accessibility (or
  Input Monitoring) permission; without it the listener runs but never sees
  a key, which is why `permission_hint()` exists.
"""
import json
import os
import subprocess
import sys
import threading
import time

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    import ctypes.wintypes as wt
else:                       # keep the module importable everywhere
    ctypes = None
    wt = None

# How long to wait before restarting a watcher that has ended, by attempt.
# The last one repeats for ever: a shortcut is not a feature that may be
# unavailable, so the app keeps trying for as long as it is running.
REVIVE_DELAYS = (0.5, 1.0, 2.0, 5.0, 15.0, 30.0)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_MODS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN, "super": MOD_WIN, "cmd": MOD_WIN,
}

# Virtual-key codes for the keys we let users bind.
_VK = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "esc": 0x1B, "escape": 0x1B, "space": 0x20,
    "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "insert": 0x2D, "delete": 0x2E,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD,
    "\\": 0xDC, ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
    "printscreen": 0x2C, "prtsc": 0x2C,
}
for _i in range(1, 25):
    _VK["f%d" % _i] = 0x6F + _i
for _c in "0123456789":
    _VK[_c] = ord(_c)
for _c in "abcdefghijklmnopqrstuvwxyz":
    _VK[_c] = ord(_c.upper())


def parse(spec):
    """'ctrl+alt+t' -> (modifiers, vk). Raises ValueError on bad input."""
    parts = [p.strip().lower() for p in str(spec).split("+") if p.strip()]
    if not parts:
        raise ValueError("empty hotkey")
    mods = 0
    key = None
    for part in parts:
        if part in _MODS:
            mods |= _MODS[part]
        elif key is None:
            key = part
        else:
            raise ValueError("more than one non-modifier key: %s" % spec)
    if key is None:
        raise ValueError("hotkey needs a normal key, not only modifiers")
    if key not in _VK:
        raise ValueError("unsupported key: %s" % key)
    if not mods:
        raise ValueError("hotkey needs at least one modifier (ctrl/alt/shift/win)")
    return mods | MOD_NOREPEAT, _VK[key]


# Keys that are safe with a single modifier because almost nothing else
# binds them. Everything else — a plain letter or digit — is contested.
_UNCONTESTED = tuple("f%d" % n for n in range(1, 25)) + (
    "insert", "scroll_lock", "pause", "print", "printscreen", "menu")


def risky(spec):
    """Why this shortcut is likely to be taken by another app, or "".

    Not a refusal. A single modifier and a letter does work; it is simply
    that whichever application is in front gets it first, so it works
    everywhere except the one program the user was reading — which is a
    very confusing way for a shortcut to be broken, and looks like the app
    failing rather than a collision.

    Two examples that came up: ⌘E is "Use Selection for Find" across macOS,
    and Ctrl+E is bound in Office and most browsers' address bars.
    """
    try:
        parts = [p.strip().lower() for p in str(spec).split("+") if p.strip()]
    except Exception:
        return ""
    mods = [p for p in parts if p in _MODS or p in ("cmd", "super", "win")]
    keys = [p for p in parts if p not in mods]
    if len(mods) != 1 or len(keys) != 1:
        return ""
    key = keys[0]
    if key in _UNCONTESTED:
        return ""
    if len(key) > 1 and key not in _VK:
        return ""
    name = "+".join(parts).upper()
    return ("%s is one modifier and one key, which most apps also use for "
            "something. It will work everywhere except the program that "
            "already owns it — and that is usually the one you are trying "
            "to read. Adding a second modifier makes it yours." % name)


def forbidden(spec):
    """True for a spec that must never be registered, whatever its source.

    shortcut_field.py already refuses to let anyone *capture* bare Cmd+letter
    on macOS — it would take over Cmd+C, Cmd+V, Cmd+W, Cmd+Q system-wide.
    This is the same rule applied again at registration time, so a value
    that reached config some other way (a build from before that guard
    existed, a hand-edited config file) still cannot be loaded and armed on
    the next launch.
    """
    if not IS_MAC:
        return False
    try:
        parts = [p.strip().lower() for p in str(spec).split("+") if p.strip()]
    except Exception:
        return False
    mods = [p for p in parts if p in _MODS]
    keys = [p for p in parts if p not in mods]
    if len(keys) != 1:
        return False
    return mods == ["cmd"] and not keys[0].startswith("f")


def permission_hint():
    """What the user has to do for global hotkeys to be delivered."""
    if IS_MAC:
        return ("If the shortcut is registered with macOS directly it needs "
                "no permission, but another app may already own that "
                "combination — try a different one in Settings. If the app "
                "fell back to watching the keyboard, grant Accessibility in "
                "System Settings > Privacy & Security and restart.")
    return ""


def normalise(spec):
    """Canonical, lower-case, modifiers first: 'Cmd + Shift+T' -> 'cmd+shift+t'."""
    parts = [p.strip().lower() for p in str(spec).split("+") if p.strip()]
    mods = [p for p in parts if p in _MODS or p in ("cmd", "super", "win")]
    keys = [p for p in parts if p not in mods]
    order = {"ctrl": 0, "control": 0, "cmd": 1, "win": 1, "super": 1,
             "alt": 2, "shift": 3}
    mods.sort(key=lambda m: order.get(m, 9))
    return "+".join(mods + keys)


class PynputHotkeyManager(threading.Thread):
    """Global hotkeys via a listener running in a separate process.

    The listener cannot live in this process. pynput's macOS backend calls
    Text Input Services from its own thread, and macOS aborts any UI
    application that touches TIS/TSM off the main thread — which Tk already
    owns. The result is an immediate crash, not a warning.

    So the watcher is a child process with no GUI, and it reports presses as
    lines on stdout. That also means a wedged listener can be restarted
    without taking the app down with it.
    """

    daemon = True

    def __init__(self):
        super().__init__(name="hotkeys", daemon=True)
        self._bindings = {}
        self._specs = {}
        self._errors = {}
        self._next_id = 1
        self._process = None
        self._reader = None
        self._ready = threading.Event()
        self._started = threading.Event()
        self._lock = threading.Lock()
        self._stopping = False
        self._paused = False    # let go while Settings records a new one
        self._revivals = 0      # how many times the watcher has been revived
        self.backend = "?"      # "carbon" (consumes keys) or "watcher"
        self.ui_status = "?"    # 0 = the watcher can be told about presses
        self.notes = []         # why a backend was rejected, in its words
        # When each shortcut was last pressed and let go, for telling a
        # tap from a hold (see `released`). Only Carbon says when a
        # shortcut is let go; it says so at start-up (RELEASES).
        self.reports_release = False
        self._pressed_at = {}
        self._released_at = {}

    def released(self, hid):
        """Whether the shortcut `hid` has been let go since it was last
        pressed: True or False - or None when this backend cannot tell."""
        if not self.reports_release or hid is None:
            return None
        pressed = self._pressed_at.get(hid)
        if pressed is None:
            return None
        let_go = self._released_at.get(hid)
        return bool(let_go is not None and let_go >= pressed)

    # -- public API (same shape as the Windows manager) ----------------
    def register(self, spec, callback):
        parse(spec)                      # validate early, same rules
        hid = self._next_id
        self._next_id += 1
        with self._lock:
            self._bindings[hid] = callback
            self._specs[hid] = spec
        if self.is_alive() or self._started.is_set():
            self._restart()
        return hid

    def unregister(self, hid):
        with self._lock:
            self._bindings.pop(hid, None)
            self._specs.pop(hid, None)
        if self._started.is_set():
            self._restart()

    def rebind(self, hid, spec):
        cb = self._bindings.get(hid)
        if cb is None:
            return hid, "unknown hotkey"
        try:
            parse(spec)
        except ValueError as exc:
            return hid, str(exc)
        self.unregister(hid)
        new_id = self.register(spec, cb)
        self._ready.wait(3.0)
        return new_id, self._errors.get(new_id)

    def _note_refused(self, payload):
        """Record which shortcuts the system would not accept."""
        try:
            refused = {int(x) for x in json.loads(payload or "[]")}
        except Exception:
            refused = set()
        with self._lock:
            for hid in list(self._specs):
                if hid in refused:
                    self._errors[hid] = (
                        "%s was refused by macOS — another app is probably "
                        "using it. Try a different combination."
                        % self._specs[hid])
                else:
                    self._errors.pop(hid, None)

    def error_for(self, hid):
        return self._errors.get(hid)

    def wait_ready(self, timeout=3.0):
        return self._ready.wait(timeout)

    def stop(self):
        self._stopping = True
        self._kill_child()

    def run(self):
        self._started.set()
        # Before the first child is started, never after: this cannot tell
        # our own listener from somebody else's, and at this moment we do
        # not have one.
        self.sweep_orphans()
        self._restart()

    # -- internals -----------------------------------------------------
    def _pynput_spec(self, spec):
        """'cmd+shift+t' -> '<cmd>+<shift>+t', which is pynput's syntax."""
        out = []
        for part in normalise(spec).split("+"):
            if part in ("ctrl", "control"):
                out.append("<ctrl>")
            elif part in ("cmd", "win", "super"):
                out.append("<cmd>")
            elif part == "alt":
                out.append("<alt>")
            elif part == "shift":
                out.append("<shift>")
            elif len(part) == 1:
                out.append(part)
            else:
                out.append("<%s>" % part)
        return "+".join(out)

    @staticmethod
    def wanted_backend():
        """"auto", or one the person has pinned in the settings.

        Imported here rather than at the top: config imports this module,
        and a module cannot import the thing importing it.
        """
        try:
            from . import config
            value = str(config.CONFIG.get("hotkey_backend", "auto") or "auto")
            return value.strip().lower()
        except Exception:
            return "auto"

    def _revive(self):
        """Start the watcher again after it has ended unexpectedly.

        Backing off, because a watcher that cannot start at all — no
        pynput, no display — would otherwise be relaunched in a tight loop
        forever. It never gives up entirely: the last delay repeats, so a
        machine that recovers gets its shortcut back without the person
        having to notice anything happened, and one that does not recover
        costs a process every half minute.
        """
        if self._stopping or self._paused:
            return
        self._revivals += 1
        delay = REVIVE_DELAYS[min(self._revivals, len(REVIVE_DELAYS)) - 1]
        if self._revivals <= len(REVIVE_DELAYS):
            self.notes.append(
                "the shortcut watcher stopped and is being restarted "
                "(attempt %d)" % self._revivals)
        timer = threading.Timer(delay, self._revive_now)
        timer.daemon = True
        timer.start()

    def _revive_now(self):
        if self._stopping or self._paused:
            return
        try:
            self._restart()
        except Exception:
            pass

    def alive(self):
        """Is the watcher actually running? The honest health check."""
        process = self._process
        return bool(process is not None and process.poll() is None)

    def check(self):
        """Restart the watcher if it is not running. Safe to call often.

        The reader thread notices a watcher that exits, and calling this on
        a timer covers the case where the reader itself is what went — a
        thread that dies takes the only thing watching the watcher with it.
        Nothing else in the app would ever notice.
        """
        if self._stopping or self._paused or not self._started.is_set():
            return False
        if self.alive():
            return False
        self._revive()
        return True

    def pause(self):
        """Let go of the shortcuts for a moment.

        A registered global shortcut *consumes* the keystroke — that is what
        makes it global rather than a suggestion. So while Squint holds
        Ctrl+Cmd+T, pressing Ctrl+Cmd+T into the box in Settings that
        records a new shortcut never reaches the box: the registration eats
        it and fires a snip instead. The one combination a person most
        wants to retype is the one they cannot.

        Nothing clever is needed. Let go while the box is listening.
        """
        self._paused = True
        self._kill_child()

    def resume(self):
        self._paused = False
        self._restart()

    def _kill_child(self):
        process, self._process = self._process, None
        if process is None:
            return
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _set_error_for_all(self, message):
        with self._lock:
            for hid in self._bindings:
                self._errors[hid] = message

    def sweep_orphans(self):
        """Kill listeners left behind by earlier runs. Returns how many.

        A listener that outlives its app keeps its global shortcut
        registration, and macOS goes on delivering the shortcut to it —
        into a pipe nobody is reading. One machine had accumulated more
        than forty, some of them from before this app was renamed, and the
        shortcut had not worked there for days: every new Squint registered
        successfully, reported itself ready, and never received a press.

        Listeners now quit when their parent does, so this is for the ones
        already out there. It is deliberately narrow — the exact script
        path, this user only, never this process's own child, which has not
        been started yet at the point this runs.
        """
        if IS_WINDOWS:
            return 0
        # Matched on the full command line, not on the name alone.
        #
        # `pgrep -f hotkey_listener.py` was the obvious way and it is
        # dangerous: it matches anything that merely *mentions* the script
        # — the shell that launched it, an editor with the file open, a
        # test running it by name. It killed its own terminal the first
        # time it ran. A listener is a process whose command line has the
        # script as an argument followed by the JSON map of shortcuts, and
        # nothing else looks like that.
        killed = 0
        mine = {os.getpid(), os.getppid()}
        try:
            listing = subprocess.run(["ps", "-axo", "pid=,command="],
                                     capture_output=True, text=True,
                                     timeout=15)
            for line in (listing.stdout or "").splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) != 2:
                    continue
                try:
                    pid = int(parts[0])
                except ValueError:
                    continue
                command = parts[1]
                if pid in mine:
                    continue
                if "/app/hotkey_listener.py " not in command:
                    continue
                if '{"' not in command:
                    continue          # no shortcut map: not a listener
                try:
                    os.kill(pid, 15)
                    killed += 1
                except Exception:
                    pass
        except Exception:
            pass
        if killed:
            self.notes.append(
                "cleared %d shortcut listener(s) left behind by earlier "
                "runs — each one was still holding the shortcut" % killed)
        return killed

    def _restart(self):
        if self._stopping or getattr(self, "_paused", False):
            self._ready.set()
            return
        self._kill_child()
        self._ready.clear()

        with self._lock:
            specs = dict(self._specs)
        if not specs:
            self._ready.set()
            return

        mapping = {}
        for hid, spec in specs.items():
            try:
                mapping[str(hid)] = {"spec": normalise(spec),
                                     "pynput": self._pynput_spec(spec)}
                self._errors.pop(hid, None)
            except Exception as exc:
                self._errors[hid] = str(exc)
        if not mapping:
            self._ready.set()
            return

        script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "hotkey_listener.py")
        # Which backend to use, handed down rather than looked up again, so
        # the child never has to read the settings for itself.
        environ = dict(os.environ)
        environ.setdefault("SQUINT_HOTKEY_BACKEND", self.wanted_backend())
        self.notes = []
        try:
            self._process = subprocess.Popen(
                [sys.executable, script, json.dumps(mapping)],
                # A real pipe for stdin, held open and never written to.
                # It is how the listener knows this app is still alive:
                # when this process ends, the write end closes and the
                # child sees end-of-file. Inheriting instead — which is
                # what happened before — hands it whatever the launcher
                # had, and from an app icon that is /dev/null, which is
                # at end-of-file the instant it is read.
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, env=environ,
                cwd=os.path.dirname(os.path.dirname(script)))
        except Exception as exc:
            self._set_error_for_all("could not start the key watcher: %s" % exc)
            self._ready.set()
            return

        self._reader = threading.Thread(target=self._read_child, daemon=True,
                                        name="hotkey-reader")
        self._reader.start()

    def _read_child(self):
        process = self._process
        if process is None or process.stdout is None:
            self._ready.set()
            return
        try:
            for raw in process.stdout:
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("NOTE "):
                    # Why a backend was rejected, said while somebody can
                    # still act on it. These used to go to the child's
                    # stderr, which is read only once the child has ended.
                    self.notes.append(line[5:].strip())
                    continue
                if line == "RELEASES":
                    self.reports_release = True
                    continue
                if line.startswith("UP "):
                    try:
                        self._released_at[int(line[3:])] = time.monotonic()
                    except ValueError:
                        pass
                    continue
                if line.startswith("UI "):
                    # Whether the watcher process has a window-server
                    # connection. Without one it registers shortcuts that
                    # are never delivered, which looks identical to a
                    # shortcut that was never registered.
                    self.ui_status = line[3:].strip()
                    continue
                if line.startswith("READY"):
                    parts = line.split(None, 2)
                    self.backend = parts[1] if len(parts) > 1 else "?"
                    # A watcher that got this far is working, so the next
                    # failure starts its backoff from the beginning rather
                    # than inheriting the delay of one hours ago.
                    self._revivals = 0
                    # The child names the shortcuts macOS refused. Recording
                    # them here is what lets Settings say "this one was
                    # rejected" instead of reporting every shortcut active.
                    self._note_refused(parts[2] if len(parts) > 2 else "")
                    self._ready.set()
                    continue
                try:
                    hid = int(line)
                except ValueError:
                    continue
                self._pressed_at[hid] = time.monotonic()
                callback = self._bindings.get(hid)
                if callback:
                    try:
                        callback()
                    except Exception:
                        pass
        except Exception:
            pass

        # The child ended. Whatever it wrote to stderr explains why.
        message = ""
        try:
            if process.stderr is not None:
                message = (process.stderr.read() or "").strip()
        except Exception:
            pass
        if not self._stopping:
            if "PYNPUT_MISSING" in message:
                self._set_error_for_all(
                    "the key watcher is not installed — run setup again")
            elif message:
                self._set_error_for_all(
                    "the key watcher stopped: %s" % message.splitlines()[0])
        self._ready.set()
        # And bring it back.
        #
        # This used to be the end of the story: the watcher died, the error
        # was written down, and the shortcut was gone for the rest of the
        # session. Every single cause of a dead shortcut this week ended
        # here — an orphan holding the registration, a watchdog shooting
        # the listener at startup, a child that crashed — and in every case
        # the app sat there with a dead watcher and no attempt to fix it.
        #
        # A keyboard shortcut is not a feature that may be unavailable. It
        # is how the app is used. If the thing that provides it stops, the
        # only acceptable response is to start it again.
        self._revive()


class WindowsHotkeyManager(threading.Thread):
    """Owns a message-loop thread; hotkeys must be registered on that thread."""

    daemon = True

    def __init__(self):
        super().__init__(name="hotkeys", daemon=True)
        if not IS_WINDOWS:
            raise RuntimeError("WindowsHotkeyManager needs Windows")
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._bindings = {}      # id -> callback
        self._pending = []       # [(id, mods, vk)]
        self._next_id = 1
        self._thread_id = None
        self._ready = threading.Event()
        self._errors = {}        # id -> error string
        self._specs = {}         # id -> spec
        self.notes = []          # same shape as the other manager

    def alive(self):
        """The message loop runs in this thread; if it is up, so are the
        shortcuts. There is no child process to lose on Windows."""
        return self.is_alive()

    def check(self):
        """Nothing to revive. Kept so callers need not ask which platform
        they are on — the app checks its shortcuts on a timer and that
        timer should not have to know."""
        return False

    # -- public API ---------------------------------------------------
    def register(self, spec, callback):
        """Returns hotkey id. Safe to call before or after start()."""
        mods, vk = parse(spec)
        hid = self._next_id
        self._next_id += 1
        self._bindings[hid] = callback
        self._specs[hid] = spec
        if self._thread_id is None:
            self._pending.append((hid, mods, vk))
        else:
            # Ask the loop thread to do the registration.
            self._ready.clear()
            self._user32.PostThreadMessageW(
                self._thread_id, 0x0400, wt.WPARAM(hid),
                wt.LPARAM((mods << 16) | vk))
        return hid

    def unregister(self, hid):
        self._bindings.pop(hid, None)
        self._specs.pop(hid, None)
        if self._thread_id is not None:
            self._user32.PostThreadMessageW(
                self._thread_id, 0x0401, wt.WPARAM(hid), wt.LPARAM(0))

    def rebind(self, hid, spec):
        """Rebind a hotkey. Returns (new_id, error_or_None)."""
        cb = self._bindings.get(hid)
        if cb is None:
            return hid, "unknown hotkey"
        try:
            parse(spec)
        except ValueError as exc:
            return hid, str(exc)
        self.unregister(hid)
        new_id = self.register(spec, cb)
        self.wait_ready(2.0)
        return new_id, self._errors.get(new_id)

    def error_for(self, hid):
        return self._errors.get(hid)

    def wait_ready(self, timeout=3.0):
        return self._ready.wait(timeout)

    def pause(self):
        """Let go of the shortcuts while Settings records a new one.

        RegisterHotKey consumes the keystroke exactly as macOS's does, so
        the combination somebody is trying to retype into the box is the
        one combination the box can never see. Windows has the same bug for
        the same reason.
        """
        for hid in list(self._bindings):
            try:
                self._user32.PostThreadMessageW(
                    self._thread_id, 0x0401, wt.WPARAM(hid), wt.LPARAM(0))
            except Exception:
                pass

    def resume(self):
        for hid, spec in list(self._specs.items()):
            try:
                mods, vk = parse(spec)
                self._user32.PostThreadMessageW(
                    self._thread_id, 0x0400, wt.WPARAM(hid),
                    wt.LPARAM((mods << 16) | vk))
            except Exception:
                pass

    def stop(self):
        if self._thread_id is not None:
            self._user32.PostThreadMessageW(
                self._thread_id, WM_QUIT, wt.WPARAM(0), wt.LPARAM(0))

    # -- internals ----------------------------------------------------
    def _do_register(self, hid, mods, vk):
        ok = self._user32.RegisterHotKey(None, hid, mods, vk)
        if not ok:
            code = ctypes.get_last_error()
            if code == 1409:
                msg = ("that shortcut is already taken by another program "
                       "(%s)" % self._specs.get(hid, "?"))
            else:
                msg = "could not register %s (win32 error %d)" % (
                    self._specs.get(hid, "?"), code)
            self._errors[hid] = msg
        else:
            self._errors.pop(hid, None)
        return bool(ok)

    def run(self):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._thread_id = kernel32.GetCurrentThreadId()
        for hid, mods, vk in self._pending:
            self._do_register(hid, mods, vk)
        self._pending = []
        self._ready.set()

        msg = wt.MSG()
        while True:
            res = self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if res in (0, -1):
                break
            if msg.message == WM_HOTKEY:
                cb = self._bindings.get(msg.wParam)
                if cb:
                    try:
                        cb()
                    except Exception:
                        pass
            elif msg.message == 0x0400:      # register request
                mods = (msg.lParam >> 16) & 0xFFFF
                vk = msg.lParam & 0xFFFF
                self._do_register(msg.wParam, mods, vk)
                self._ready.set()
            elif msg.message == 0x0401:      # unregister request
                self._user32.UnregisterHotKey(None, msg.wParam)

        for hid in list(self._bindings):
            self._user32.UnregisterHotKey(None, hid)


# Kept for callers that referred to the macOS class by name.
MacHotkeyManager = PynputHotkeyManager


def HotkeyManager():
    """The right implementation for this platform.

    Windows gets the native API; everything else gets the pynput listener,
    so the app remains runnable (and testable) outside Windows rather than
    refusing to start.
    """
    return WindowsHotkeyManager() if IS_WINDOWS else PynputHotkeyManager()
