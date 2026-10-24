"""What every tool in the radial menu shares: where files go, how the user
is told something finished, the small dialogs, background work, and the
helper programs fetched on first use (FFmpeg, 7-Zip)."""
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
import zipfile

from .. import config

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# One look for every window the toolkit opens. Matches the radial menu.
BG = "#1E2129"
PANEL = "#262A33"
ROW = "#2C3240"
LINE = "#3A404C"
TEXT = "#E8EAF0"
MUTED = "#A9AFBC"
ACCENT = "#3D7BF5"
TITLE = "#FFFFFF"       # headings
FAINT = "#5F6676"       # days outside the month, "Wk"
DIM = "#7D8597"         # week numbers
ERROR = "#F28B82"
GOOD = "#5FD38D"
LINK = "#8FB4FF"
WARN_BG = "#3A3320"
WARN_FG = "#F5D58A"
ON_ACCENT = "#FFFFFF"   # text on the accent colour
BUTTON_TEXT = "#FFFFFF"  # text on a plain (ROW) button

_DARK = dict(BG="#1E2129", PANEL="#262A33", ROW="#2C3240", LINE="#3A404C",
             TEXT="#E8EAF0", MUTED="#A9AFBC", TITLE="#FFFFFF",
             FAINT="#5F6676", DIM="#7D8597", ERROR="#F28B82",
             GOOD="#5FD38D", LINK="#8FB4FF", WARN_BG="#3A3320",
             WARN_FG="#F5D58A", BUTTON_TEXT="#FFFFFF")
_LIGHT = dict(BG="#F3F4F7", PANEL="#FAFAFC", ROW="#ECEEF2", LINE="#DCDFE5",
              TEXT="#1E2129", MUTED="#5B6270", TITLE="#111318",
              FAINT="#A3A9B5", DIM="#8A919E", ERROR="#C5221F",
              GOOD="#188038", LINK="#1A5FD6", WARN_BG="#FFF4D6",
              WARN_FG="#7A5600", BUTTON_TEXT="#1E2129")


def _mix(a, b, f):
    pa = [int(a[k:k + 2], 16) for k in (1, 3, 5)]
    pb = [int(b[k:k + 2], 16) for k in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(int(round(x + (y - x) * f))
                                   for x, y in zip(pa, pb))


def apply_theme(light, panel=None):
    """Light or dark for every panel, card, toast and bar. `panel` (a
    #RRGGBB) is the colour of the ring's glass, so the panel beside it is
    the same tone; the row and line colours follow from it."""
    palette = dict(_LIGHT if light else _DARK)
    if panel:
        palette["PANEL"] = panel
        towards = "#000000" if light else "#FFFFFF"
        palette["ROW"] = _mix(panel, towards, 0.07 if light else 0.08)
        palette["LINE"] = _mix(panel, towards, 0.14 if light else 0.16)
        palette["BG"] = panel
    globals().update(palette)
FONT = "Segoe UI" if IS_WINDOWS else ("Helvetica Neue" if IS_MAC
                                      else "Helvetica")

NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


def log(message):
    try:
        from ..main import log as main_log
        main_log("radial     : %s" % message)
    except Exception:
        pass


# -- folders -----------------------------------------------------------

# Everything the tools make goes under Downloads/Squint, one folder per
# tool, so there is a single place to look.
FOLDERS = {
    "shot": "Screenshots",
    "rec": "Recordings",
    "pdf": "PDF",
    "zip": "Zip",
    "send": "Received",
    "ext": "Extracted media",
}


def base_dir():
    path = os.path.join(os.path.expanduser("~"), "Downloads", "Squint")
    os.makedirs(path, exist_ok=True)
    return path


def squint_dir(tool):
    path = os.path.join(base_dir(), FOLDERS[tool])
    os.makedirs(path, exist_ok=True)
    return path


def pictures_dir():
    return squint_dir("shot")


def videos_dir():
    return squint_dir("rec")


def received_dir():
    return squint_dir("send")


def where(path):
    """'Downloads\\Squint\\PDF' for a result inside our folders, else ''."""
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.dirname(base_dir()))
    except ValueError:
        return ""
    if rel.startswith("..") or os.path.isabs(rel):
        return ""
    parts = rel.split(os.sep)
    return "\\".join(["Downloads"] + parts[:2])


def _settings_path():
    return os.path.join(config.data_dir(), "radial.json")


def setting(key, default=None):
    """The toolkit's own small settings (nickname and the like)."""
    try:
        import json
        with open(_settings_path(), encoding="utf-8") as fh:
            return json.load(fh).get(key, default)
    except (OSError, ValueError, AttributeError):
        return default


def set_setting(key, value):
    import json
    try:
        with open(_settings_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data[key] = value
    tmp = _settings_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, _settings_path())


def tools_dir():
    path = os.path.join(config.data_dir(), "tools")
    os.makedirs(path, exist_ok=True)
    return path


def stamp():
    return time.strftime("%Y-%m-%d %H.%M.%S")


def unique(path):
    """`path`, or `path (2)` and so on when something is already there."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists("%s (%d)%s" % (base, n, ext)):
        n += 1
    return "%s (%d)%s" % (base, n, ext)


def into(tool, name):
    """A new, unused file name in that tool's folder."""
    return unique(os.path.join(squint_dir(tool), name))


def reveal(path):
    try:
        from .. import platform_util
        platform_util.reveal(path)
    except Exception:
        pass


def run(args, **kw):
    """A helper program, with no console window flashing up on Windows."""
    kw.setdefault("creationflags", NO_WINDOW)
    kw.setdefault("stdout", subprocess.PIPE)
    kw.setdefault("stderr", subprocess.PIPE)
    return subprocess.run(args, **kw)


# -- telling the user --------------------------------------------------

def screen_scale(root):
    """The display scaling under the pointer (1.0 at 100 %)."""
    try:
        from .. import platform_util
        x, y = root.winfo_pointerxy()
        return max(1.0, (platform_util.monitor_scaling(x, y) or 100) / 100.0)
    except Exception:
        return 1.0


def px_font(scale, size, bold=False):
    """The same pixel sizes the ring's panel uses."""
    return (FONT, -int(round(size * scale)), "bold" if bold else "normal")


class Toast:
    """A small card in the bottom-right corner that goes away by itself.
    Clicking it opens what it is about, when there is something to open."""

    _open = []

    def __init__(self, root, message, path=None, seconds=4.5):
        for old in Toast._open[:]:
            old.close()
        self.path = path
        win = self.win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=LINE)
        s = screen_scale(root)
        inner = tk.Frame(win, bg=PANEL, padx=int(16 * s), pady=int(12 * s))
        inner.pack(padx=1, pady=1)
        tk.Label(inner, text=message, bg=PANEL, fg=TEXT,
                 font=px_font(s, 13), justify="left",
                 wraplength=int(320 * s)).pack(anchor="w")
        if path:
            tk.Label(inner, text="Click to show", bg=PANEL, fg=ACCENT,
                     font=px_font(s, 11)).pack(anchor="w",
                                               pady=(int(4 * s), 0))
        for w in (win, inner) + tuple(inner.winfo_children()):
            w.bind("<Button-1>", self._click)
        win.update_idletasks()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        win.geometry("+%d+%d" % (sw - w - 24, sh - h - 72))
        Toast._open.append(self)
        win.after(int(seconds * 1000), self.close)

    def _click(self, _e=None):
        if self.path:
            reveal(self.path)
        self.close()

    def close(self):
        try:
            self.win.destroy()
        except Exception:
            pass
        if self in Toast._open:
            Toast._open.remove(self)


def tell(ctrl, message, path=None):
    if path and where(path):
        message += "\n" + where(path)
    log(message.replace("\n", " / "))
    try:
        Toast(ctrl.root, message, path)
    except Exception:
        if getattr(ctrl, "tray", None):
            ctrl.tray.notify(message)


def failed(ctrl, what, exc):
    log("%s failed: %r" % (what, exc))
    tell(ctrl, "%s did not work.\n%s" % (what, exc))


# -- background work ---------------------------------------------------

def in_background(ctrl, work, done=None, what="That", progress=None):
    """Run `work()` off the Tk thread; call `done(result)` back on it.

    Nothing in `work` may touch a window: Tk is only safe from its own
    thread. A `progress` window given here is closed on the Tk thread
    whichever way the work ends."""
    box = queue.Queue()

    def runner():
        try:
            box.put((True, work()))
        except Exception as exc:          # noqa: BLE001 - reported to user
            import traceback
            log(traceback.format_exc())
            box.put((False, exc))

    threading.Thread(target=runner, daemon=True, name="radial-work").start()

    def poll():
        try:
            ok, value = box.get_nowait()
        except queue.Empty:
            ctrl.root.after(120, poll)
            return
        if progress is not None:
            progress.close()
        if not ok:
            failed(ctrl, what, value)
        elif done is not None:
            try:
                done(value)
            except Exception as exc:      # noqa: BLE001
                failed(ctrl, what, exc)

    ctrl.root.after(120, poll)


def download(url, dest, progress=None, label=""):
    req = urllib.request.Request(url, headers={"User-Agent": "Squint"})
    ctx = None
    try:
        from .. import updater
        ctx = updater._contexts()[0]
    except Exception:
        pass
    with urllib.request.urlopen(req, timeout=60, context=ctx) as resp, \
            open(dest + ".part", "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            out.write(chunk)
            got += len(chunk)
            if progress and total:
                progress.set(got / total, "%s  %d of %d MB"
                             % (label, got >> 20, total >> 20))
    os.replace(dest + ".part", dest)
    return dest


FFMPEG_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/"
              "latest/ffmpeg-master-latest-win64-gpl.zip")


# The Mac's: Martin Riedl's static builds, Apple Silicon or Intel.
FFMPEG_MAC_URL = ("https://ffmpeg.martin-riedl.de/redirect/latest/macos/"
                  "%s/release/ffmpeg.zip")


def ffmpeg_path():
    found = shutil.which("ffmpeg")
    if IS_MAC:
        mine = os.path.join(tools_dir(), "ffmpeg", "ffmpeg")
        if os.path.isfile(mine):
            return mine
        for brew in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
            if os.path.isfile(brew):
                return brew
        return found
    if not IS_WINDOWS:
        return found
    mine = os.path.join(tools_dir(), "ffmpeg", "ffmpeg.exe")
    return mine if os.path.isfile(mine) else found


def _get_ffmpeg_mac(progress=None):
    import platform
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") \
        else "amd64"
    folder = os.path.join(tools_dir(), "ffmpeg")
    os.makedirs(folder, exist_ok=True)
    archive = os.path.join(tools_dir(), "ffmpeg-download.zip")
    download(FFMPEG_MAC_URL % arch, archive, progress,
             "Getting the video tools")
    out = os.path.join(folder, "ffmpeg")
    with zipfile.ZipFile(archive) as zf:
        name = next((n for n in zf.namelist()
                     if os.path.basename(n) == "ffmpeg"), None)
        if not name:
            raise RuntimeError("the video tools download was not as expected")
        with zf.open(name) as src, open(out + ".part", "wb") as dst:
            shutil.copyfileobj(src, dst)
    os.remove(archive)
    os.chmod(out + ".part", 0o755)
    os.replace(out + ".part", out)
    return out


def get_ffmpeg(progress=None):
    """FFmpeg, downloaded once the first time it is needed. Kept out of the
    install so everyone else never pays for it."""
    have = ffmpeg_path()
    if have:
        return have
    if IS_MAC:
        return _get_ffmpeg_mac(progress)
    if not IS_WINDOWS:
        raise RuntimeError("FFmpeg is not installed")
    folder = os.path.join(tools_dir(), "ffmpeg")
    os.makedirs(folder, exist_ok=True)
    archive = os.path.join(tools_dir(), "ffmpeg-download.zip")
    download(FFMPEG_URL, archive, progress, "Getting the video tools")
    with zipfile.ZipFile(archive) as zf:
        for name in zf.namelist():
            if name.endswith(("/bin/ffmpeg.exe", "/bin/ffprobe.exe")):
                with zf.open(name) as src, \
                        open(os.path.join(folder, os.path.basename(name)),
                             "wb") as out:
                    shutil.copyfileobj(src, out)
    os.remove(archive)
    return os.path.join(folder, "ffmpeg.exe")


# 7-Zip from its official GitHub releases. 7zr.exe reads only .7z, which
# is what the full command-line 7za.exe ships in.
SEVENZIP_VERSIONS = ("25.01", "25.00", "24.09", "24.08")


def sevenzip_path():
    if IS_MAC:
        mine = os.path.join(tools_dir(), "7zip", "7zz")
        if os.path.isfile(mine):
            return mine
    if IS_WINDOWS:
        mine = os.path.join(tools_dir(), "7zip", "7za.exe")
        if os.path.isfile(mine):
            return mine
        for base in (os.environ.get("ProgramFiles", ""),
                     os.environ.get("ProgramFiles(x86)", "")):
            candidate = os.path.join(base, "7-Zip", "7z.exe")
            if base and os.path.isfile(candidate):
                return candidate
    return shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")


def get_7zip(progress=None):
    have = sevenzip_path()
    if have:
        return have
    if IS_MAC:
        return _get_7zip_mac(progress)
    if not IS_WINDOWS:
        raise RuntimeError("7-Zip is not installed")
    folder = os.path.join(tools_dir(), "7zip")
    os.makedirs(folder, exist_ok=True)
    last = None
    for ver in SEVENZIP_VERSIONS:
        base = "https://github.com/ip7z/7zip/releases/download/%s/" % ver
        extra = "7z%s-extra.7z" % ver.replace(".", "")
        try:
            seven_r = download(base + "7zr.exe",
                               os.path.join(folder, "7zr.exe"),
                               progress, "Getting 7-Zip")
            pack = download(base + extra, os.path.join(folder, extra),
                            progress, "Getting 7-Zip")
            done = run([seven_r, "e", "-y", "-o" + folder, pack,
                        "x64\\7za.exe", "x64\\7za.dll", "x64\\7zxa.dll"])
            os.remove(pack)
            if os.path.isfile(os.path.join(folder, "7za.exe")):
                return os.path.join(folder, "7za.exe")
            last = done.stderr.decode(errors="replace")
        except Exception as exc:          # noqa: BLE001 - try the next one
            last = exc
    raise RuntimeError("could not get 7-Zip (%s)" % last)


def _get_7zip_mac(progress=None):
    """7-Zip's own macOS build (one universal 7zz binary)."""
    import tarfile
    folder = os.path.join(tools_dir(), "7zip")
    os.makedirs(folder, exist_ok=True)
    last = None
    for ver in SEVENZIP_VERSIONS:
        name = "7z%s-mac.tar.xz" % ver.replace(".", "")
        url = "https://github.com/ip7z/7zip/releases/download/%s/%s" % (
            ver, name)
        try:
            pack = download(url, os.path.join(folder, name), progress,
                            "Getting 7-Zip")
            with tarfile.open(pack, "r:xz") as tar:
                member = tar.getmember("7zz")
                with tar.extractfile(member) as src, \
                        open(os.path.join(folder, "7zz"), "wb") as out:
                    shutil.copyfileobj(src, out)
            os.remove(pack)
            path = os.path.join(folder, "7zz")
            os.chmod(path, 0o755)
            return path
        except Exception as exc:          # noqa: BLE001 - try the next one
            last = exc
    raise RuntimeError("could not get 7-Zip (%s)" % last)


class FlatButton(tk.Label):
    """A button drawn as a label. On a Mac, tk.Button is the system's own
    white button and ignores the colours given to it, which left white text
    on white. This looks the same everywhere and behaves like a button."""

    def __init__(self, parent, text="", command=None, bg=None, fg=None,
                 activebackground=None, activeforeground=None, **kw):
        for k in ("relief", "bd", "highlightthickness", "cursor"):
            kw.pop(k, None)
        super().__init__(parent, text=text, bg=bg, fg=fg, cursor="hand2",
                         **kw)
        self._command = command
        self._colours = (bg, fg)
        self._active = (activebackground or bg, activeforeground or fg)
        self.bind("<Button-1>", lambda _e: self.invoke())
        self.bind("<Enter>", lambda _e: self._paint(True))
        self.bind("<Leave>", lambda _e: self._paint(False))

    def _paint(self, on):
        if str(self.cget("state")) == "disabled":
            return
        bg, fg = self._active if on else self._colours
        try:
            super().configure(bg=bg, fg=fg)
        except tk.TclError:
            pass

    def configure(self, cnf=None, **kw):
        if "command" in kw:
            self._command = kw.pop("command")
        if "bg" in kw or "fg" in kw:
            self._colours = (kw.get("bg", self._colours[0]),
                             kw.get("fg", self._colours[1]))
        for k in ("relief", "bd", "highlightthickness", "activebackground",
                  "activeforeground"):
            kw.pop(k, None)
        return super().configure(cnf, **kw)

    config = configure

    def invoke(self):
        if str(self.cget("state")) == "disabled" or self._command is None:
            return None
        return self._command()


class PillButton(tk.Canvas):
    """A pill-shaped button: a smooth rounded shape with the words on it.
    Takes the options the panels give a tk.Button (bg, fg, font, padx,
    pady, command, state, active colours); the shape is redrawn to
    whatever size it is given."""

    _IGNORED = ("relief", "bd", "highlightthickness", "cursor",
                "activebackground", "activeforeground", "justify",
                "wraplength", "borderwidth", "overrelief")

    def __init__(self, parent, text="", command=None, bg=None, fg=None,
                 activebackground=None, activeforeground=None, font=None,
                 padx=16, pady=7, anchor="center", width=None, mark=None,
                 outline=None, height=None, **kw):
        for k in self._IGNORED:
            kw.pop(k, None)
        try:
            under = parent.cget("bg")
        except tk.TclError:
            under = PANEL
        super().__init__(parent, bg=under, highlightthickness=0, bd=0,
                         cursor="hand2")
        self._o = {"text": text, "bg": bg or ROW, "fg": fg or TEXT,
                   "abg": activebackground, "afg": activeforeground,
                   "font": font or (FONT, -12), "padx": padx, "pady": pady,
                   "anchor": anchor, "width": width, "state": "normal",
                   "mark": mark, "outline": outline, "height": height}
        self._command = command
        self._hover = False
        self._drawn = None
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<Button-1>", lambda _e: self.invoke())
        self.bind("<Configure>", self._resized)
        self._size()
        self._draw()

    def _metrics(self):
        import tkinter.font as tkfont
        f = tkfont.Font(font=self._o["font"])
        return f.measure(self._o["text"]), f.metrics("linespace")

    def _size(self):
        tw, th = self._metrics()
        w = self._o["width"] or tw + 2 * int(self._o["padx"])
        h = self._o["height"] or th + 2 * int(self._o["pady"])
        tk.Canvas.configure(self, width=w, height=h)
        self._want = (w, h)

    def _resized(self, e):
        if self._drawn != (e.width, e.height):
            self._draw(e.width, e.height)

    def _colours(self):
        o = self._o
        if o["state"] == "disabled":
            return ROW, MUTED
        if self._hover:
            return (o["abg"] or _mix(o["bg"], "#FFFFFF", 0.12),
                    o["afg"] or o["fg"])
        return o["bg"], o["fg"]

    def _draw(self, w=None, h=None):
        if not w:
            w = self.winfo_width() if self.winfo_ismapped() else 0
        w = int(w) or self._want[0]
        h = int(h or 0) or self._want[1]
        self._drawn = (w, h)
        self.delete("all")
        fill, fg = self._colours()
        r = h / 2.0
        # Plain shape underneath, the smooth picture on top.
        self.create_oval(0, 0, h, h, fill=fill, outline="")
        self.create_oval(w - h, 0, w, h, fill=fill, outline="")
        self.create_rectangle(r, 0, w - r, h, fill=fill, outline="")
        try:
            from . import icons
            self._img = icons.pill(w, h, fill, self._o["outline"],
                                   master=self)
            self.create_image(0, 0, image=self._img, anchor="nw")
        except Exception:
            pass
        if self._o["mark"]:
            # A dot under the words (a day with something planned).
            d = max(2, h / 14.0)
            self.create_oval(w / 2.0 - d, h - 3 * d - d, w / 2.0 + d,
                             h - 3 * d + d, fill=self._o["mark"], outline="")
        if self._o["anchor"] == "w":
            self.create_text(int(self._o["padx"]), h / 2.0, anchor="w",
                             text=self._o["text"], fill=fg,
                             font=self._o["font"])
        else:
            self.create_text(w / 2.0, h / 2.0, text=self._o["text"],
                             fill=fg, font=self._o["font"])

    def _set_hover(self, on):
        if self._o["state"] == "disabled":
            on = False
        if on != self._hover:
            self._hover = on
            self._draw(*self._drawn) if self._drawn else self._draw()

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        mine = {"text": "text", "bg": "bg", "background": "bg", "fg": "fg",
                "foreground": "fg", "activebackground": "abg",
                "activeforeground": "afg", "font": "font", "padx": "padx",
                "pady": "pady", "state": "state", "anchor": "anchor"}
        changed = False
        for k in list(kw):
            if k == "command":
                self._command = kw.pop(k)
            elif k in mine:
                self._o[mine[k]] = kw.pop(k)
                changed = True
            elif k in self._IGNORED:
                kw.pop(k)
        if "width" in kw:
            self._o["width"] = kw.pop("width")
            changed = True
        if kw:
            tk.Canvas.configure(self, **kw)
        if changed:
            self._size()
            self._draw(*self._want) if not self.winfo_ismapped() \
                else self._draw()

    config = configure

    def cget(self, key):
        mine = {"text": "text", "bg": "bg", "fg": "fg", "state": "state",
                "font": "font"}
        if key in mine:
            return self._o[mine[key]]
        return tk.Canvas.cget(self, key)

    def invoke(self):
        if self._o["state"] == "disabled" or self._command is None:
            return None
        return self._command()


def _button(parent, text, command, primary=False):
    cls = PillButton
    return cls(parent, text=text, command=command,
                     bg=ACCENT if primary else ROW,
                     fg=ON_ACCENT if primary else BUTTON_TEXT,
                     activebackground=ACCENT, activeforeground="#FFFFFF",
                     relief="flat", bd=0, highlightthickness=0, padx=16, pady=7,
                     font=(FONT, -12), cursor="hand2")


def finder_selection(pid):
    """macOS: the files selected in Finder, if Finder was in front."""
    try:
        from AppKit import NSRunningApplication
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(
            int(pid))
        if app is None or str(app.bundleIdentifier()) != "com.apple.finder":
            return []
    except Exception:
        return []
    script = ('tell application "Finder" to set s to selection as alias list\n'
              'set out to ""\n'
              'repeat with f in s\n'
              'set out to out & POSIX path of f & linefeed\n'
              'end repeat\n'
              'return out')
    try:
        done = run(["osascript", "-e", script], timeout=6)
        paths = [p.strip() for p in
                 done.stdout.decode("utf-8", "replace").splitlines()]
        return [p.rstrip("/") for p in paths if p and os.path.exists(p)]
    except Exception:
        return []


def explorer_selection(hwnd):
    """The files selected in the Explorer window `hwnd` (Finder on a Mac),
    if that is what was in front when the menu was opened. [] otherwise."""
    if IS_MAC and hwnd:
        return finder_selection(hwnd)
    if not IS_WINDOWS or not hwnd:
        return []
    script = (
        "$h=%d;foreach($w in (New-Object -ComObject Shell.Application)"
        ".Windows()){try{if($w.HWND -eq $h){foreach($i in "
        "$w.Document.SelectedItems()){$i.Path}}}catch{}}" % int(hwnd))
    try:
        done = run(["powershell", "-NoProfile", "-NonInteractive",
                    "-Command", script], timeout=6)
        paths = [p.strip() for p in
                 done.stdout.decode("utf-8", "replace").splitlines()]
        return [p for p in paths if p and os.path.exists(p)]
    except Exception:
        return []


def _mac_choose_files(title, exts, many):
    """macOS's own file window, centred and movable.

    Tk's dialog on a Mac is a sheet glued to its parent window; with the
    hidden parent this needs, it appeared stuck in a corner and could not
    be moved. AppleScript's `choose file` is the ordinary open window."""
    prompt = title.replace("\\", "\\\\").replace('"', '\\"')
    kinds = ""
    if exts:
        kinds = " of type {%s}" % ", ".join(
            '"%s"' % e.lstrip(".") for e in exts)
    script = ('activate\n'
              'set picked to choose file with prompt "%s"%s%s\n'
              'set out to ""\n'
              'if class of picked is list then\n'
              'repeat with f in picked\n'
              'set out to out & POSIX path of f & linefeed\n'
              'end repeat\n'
              'else\n'
              'set out to POSIX path of picked\n'
              'end if\n'
              'return out' % (prompt, kinds,
                              " with multiple selections allowed"
                              if many else ""))
    menu = None
    try:
        from .menu import RadialMenu
        menu = RadialMenu.current
        if menu is not None:
            menu.win.withdraw()            # nothing may sit over the window
    except Exception:
        menu = None
    try:
        done = run(["osascript", "-e", script], timeout=3600)
    finally:
        if menu is not None and not menu.closed:
            try:
                menu.win.deiconify()
                menu.win.lift()
            except Exception:
                pass
    if done.returncode != 0:
        return []                          # cancelled
    paths = [p.strip() for p in
             done.stdout.decode("utf-8", "replace").splitlines()]
    return [p.rstrip("/") or p for p in paths if p]


def pick_files(ctrl, title, types, many=True, selection=None):
    """Explorer's selection when it fits `types`, otherwise a file dialog."""
    exts = tuple(e.lower() for _label, pattern in types
                 for e in pattern.replace("*", "").split()
                 if e.startswith(".") and len(e) > 1)
    if selection:
        fits = [p for p in selection
                if not exts or p.lower().endswith(exts)]
        if fits:
            return fits if many else fits[:1]
    if IS_MAC:
        return _mac_choose_files(title, exts, many)
    from tkinter import filedialog
    parent = tk.Toplevel(ctrl.root)
    parent.withdraw()
    parent.attributes("-topmost", True)
    try:
        if many:
            got = filedialog.askopenfilenames(parent=parent, title=title,
                                              filetypes=types)
            return list(got)
        got = filedialog.askopenfilename(parent=parent, title=title,
                                         filetypes=types)
        return [got] if got else []
    finally:
        parent.destroy()


def key_down(name):
    """Is Enter or Escape held right now, whichever window has focus?
    Watched, not taken: the key still reaches the app in front."""
    if IS_MAC:
        try:
            from .. import platform_util
            return platform_util.key_is_down({"enter": "return",
                                              "esc": "escape"}[name])
        except Exception:
            return False
    if not IS_WINDOWS:
        return False
    import ctypes
    vk = {"enter": 0x0D, "esc": 0x1B}[name]
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return False


class StopBar:
    """A floating bar while something records: what is running, a timer,
    Stop and Cancel. Enter (anywhere) stops, Escape cancels."""

    def __init__(self, ctrl, label, on_stop, on_cancel, limit=None,
                 avoid=None):
        self.ctrl = ctrl
        self.on_stop = on_stop
        self.on_cancel = on_cancel
        self.limit = limit
        self.started = time.time()
        self.done = False
        win = self.win = tk.Toplevel(ctrl.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=LINE)
        s = screen_scale(ctrl.root)
        bar = tk.Frame(win, bg=PANEL, padx=int(12 * s), pady=int(8 * s))
        bar.pack(padx=1, pady=1)
        self.dot = tk.Label(bar, text="●", bg=PANEL, fg="#F05252",
                            font=px_font(s, 15))
        self.dot.pack(side="left")
        self.time = tk.Label(bar, text="0:00", bg=PANEL, fg=TEXT,
                             font=px_font(s, 13, True), width=5)
        self.time.pack(side="left", padx=(int(6 * s), int(8 * s)))
        tk.Label(bar, text=label, bg=PANEL, fg=MUTED,
                 font=px_font(s, 12)).pack(side="left", padx=(0, int(12 * s)))
        for text, cmd, primary in (("Stop  (Enter)", self.stop, True),
                                   ("Cancel  (Esc)", self.cancel, False)):
            b = _button(bar, text, cmd, primary)
            b.configure(font=px_font(s, 12), padx=int(14 * s),
                        pady=int(6 * s))
            b.pack(side="left", padx=(0, int(6 * s)))
        win.update_idletasks()
        w = win.winfo_reqwidth()
        x = (win.winfo_screenwidth() - w) // 2
        y = 12
        if avoid and avoid[1] < 70:
            y = win.winfo_screenheight() - win.winfo_reqheight() - 70
        win.geometry("+%d+%d" % (x, y))
        # Keys that were already down when this opened (the Enter that
        # confirmed a dialog) do not count.
        self._armed = {"enter": not key_down("enter"),
                       "esc": not key_down("esc")}
        self._tick()

    def _tick(self):
        if self.done:
            return
        secs = time.time() - self.started
        try:
            self.time.configure(text="%d:%02d" % (secs // 60, secs % 60))
            self.dot.configure(fg="#F05252" if int(secs * 2) % 2 == 0
                               else PANEL)
        except Exception:
            return
        for name, action in (("enter", self.stop), ("esc", self.cancel)):
            down = key_down(name)
            if down and self._armed[name]:
                action()
                return
            if not down:
                self._armed[name] = True
        if self.limit and secs >= self.limit:
            self.stop()
            return
        self.win.after(60, self._tick)

    def _finish(self, action):
        if self.done:
            return
        self.done = True
        try:
            self.win.destroy()
        except Exception:
            pass
        action()

    def stop(self):
        self._finish(self.on_stop)

    def cancel(self):
        self._finish(self.on_cancel)


# -- clipboard ---------------------------------------------------------

def image_to_clipboard(image):
    """Put a picture on the clipboard, so it pastes anywhere."""
    if IS_MAC:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        image.save(tmp.name)
        try:
            done = run(["osascript", "-e", 'set the clipboard to (read '
                        '(POSIX file "%s") as «class PNGf»)' % tmp.name],
                       timeout=10)
            return done.returncode == 0
        finally:
            try:
                os.remove(tmp.name)
            except OSError:
                pass
    if not IS_WINDOWS:
        return False
    import ctypes
    import io
    from ctypes import wintypes as wt
    buf = io.BytesIO()
    image.convert("RGB").save(buf, "BMP")
    data = buf.getvalue()[14:]               # a DIB is a BMP without its header
    k32 = ctypes.windll.kernel32
    u32 = ctypes.windll.user32
    k32.GlobalAlloc.restype = wt.HGLOBAL
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [wt.HGLOBAL]
    k32.GlobalUnlock.argtypes = [wt.HGLOBAL]
    u32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
    handle = k32.GlobalAlloc(0x0042, len(data))
    pointer = k32.GlobalLock(handle)
    ctypes.memmove(pointer, data, len(data))
    k32.GlobalUnlock(handle)
    for _ in range(10):
        if u32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        u32.EmptyClipboard()
        u32.SetClipboardData(8, handle)       # CF_DIB
    finally:
        u32.CloseClipboard()
    return True


def system_light():
    """True when Windows or macOS is set to light mode."""
    try:
        if IS_WINDOWS:
            import winreg
            with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes"
                    r"\Personalize") as key:
                return bool(winreg.QueryValueEx(key, "AppsUseLightTheme")[0])
        if IS_MAC:
            from Foundation import NSUserDefaults
            style = NSUserDefaults.standardUserDefaults().stringForKey_(
                "AppleInterfaceStyle")
            return str(style or "").lower() != "dark"
    except Exception:
        pass
    return False
