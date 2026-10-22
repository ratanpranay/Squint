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
    "conv": "Converted",
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
        inner = tk.Frame(win, bg=PANEL, padx=16, pady=12)
        inner.pack(padx=1, pady=1)
        tk.Label(inner, text=message, bg=PANEL, fg=TEXT, font=(FONT, 10),
                 justify="left", wraplength=320).pack(anchor="w")
        if path:
            tk.Label(inner, text="Click to show", bg=PANEL, fg=MUTED,
                     font=(FONT, 9)).pack(anchor="w", pady=(4, 0))
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


class Progress:
    """A small window with a bar, for work that takes more than a moment."""

    def __init__(self, root, title):
        win = self.win = tk.Toplevel(root)
        win.title(title)
        win.configure(bg=BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        self.label = tk.Label(win, text=title, bg=BG, fg=TEXT,
                              font=(FONT, 10), anchor="w", width=46)
        self.label.pack(padx=18, pady=(16, 8), anchor="w")
        self.canvas = tk.Canvas(win, width=360, height=8, bg=ROW,
                                highlightthickness=0)
        self.canvas.pack(padx=18, pady=(0, 18))
        self.bar = self.canvas.create_rectangle(0, 0, 0, 8, fill=ACCENT,
                                                width=0)
        self.value = 0.0
        self.text = title

    def set(self, fraction, text=None):
        """Thread-safe: only stores; the window reads it on a timer."""
        self.value = max(0.0, min(1.0, fraction))
        if text:
            self.text = text

    def pump(self):
        try:
            self.canvas.coords(self.bar, 0, 0, 360 * self.value, 8)
            self.label.configure(text=self.text)
            self.win.after(150, self.pump)
        except Exception:
            pass

    def close(self):
        try:
            self.win.destroy()
        except Exception:
            pass


# -- helper programs fetched on first use ------------------------------

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


def ffmpeg_path():
    found = shutil.which("ffmpeg")
    if not IS_WINDOWS:
        return found
    mine = os.path.join(tools_dir(), "ffmpeg", "ffmpeg.exe")
    return mine if os.path.isfile(mine) else found


def get_ffmpeg(progress=None):
    """FFmpeg, downloaded once (about 140 MB) the first time it is
    needed. Kept out of the install so everyone else never pays for it."""
    have = ffmpeg_path()
    if have:
        return have
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


def with_tool(ctrl, getter, title, then, anchor=None):
    """Make sure a helper program is here, fetching it in a card with a
    progress bar the first time, then call `then(path)` on the Tk thread."""
    finder = {"ffmpeg": ffmpeg_path, "7zip": sevenzip_path}[getter]
    have = finder()
    if have:
        then(have)
        return
    from .card import Card, ensure_tool
    card = Card(ctrl, title, anchor)

    def finish(path):
        ctrl.root.after(50, lambda: then(path))
        return None

    card.run(lambda p: ensure_tool(p, getter), finish, title)


# -- small dialogs -----------------------------------------------------

def _dialog(root, title):
    win = tk.Toplevel(root)
    win.title(title)
    win.configure(bg=BG)
    win.resizable(False, False)
    win.attributes("-topmost", True)
    return win


def _center(win):
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    x = (win.winfo_screenwidth() - w) // 2
    y = (win.winfo_screenheight() - h) // 3
    win.geometry("+%d+%d" % (x, y))
    win.lift()
    win.focus_force()


def _button(parent, text, command, primary=False):
    return tk.Button(parent, text=text, command=command,
                     bg=ACCENT if primary else ROW, fg="#FFFFFF",
                     activebackground=ACCENT, activeforeground="#FFFFFF",
                     relief="flat", bd=0, highlightthickness=0, padx=16, pady=7,
                     font=(FONT, 10),
                     cursor="hand2")


def ask_password(root, title, intro, optional=True, confirm=True,
                 extra_check=None):
    """A password, "" for none (when optional), or None if cancelled.

    `extra_check` is (label, default) for one checkbox; when given, the
    result is (password, checked)."""
    win = _dialog(root, title)
    result = {"value": None}
    frame = tk.Frame(win, bg=BG, padx=20, pady=16)
    frame.pack()
    tk.Label(frame, text=intro, bg=BG, fg=TEXT, font=(FONT, 10),
             justify="left", wraplength=340).grid(row=0, column=0,
                                                  columnspan=2, sticky="w")
    first = tk.StringVar()
    second = tk.StringVar()
    tk.Label(frame, text="Password", bg=BG, fg=MUTED,
             font=(FONT, 9)).grid(row=1, column=0, sticky="w", pady=(12, 2))
    e1 = tk.Entry(frame, textvariable=first, show="•", width=34,
                  bg=ROW, fg=TEXT, insertbackground=TEXT, relief="flat",
                  font=(FONT, 11))
    e1.grid(row=2, column=0, columnspan=2, sticky="we", ipady=5)
    row = 3
    if confirm:
        tk.Label(frame, text="Again", bg=BG, fg=MUTED,
                 font=(FONT, 9)).grid(row=row, column=0, sticky="w",
                                      pady=(8, 2))
        tk.Entry(frame, textvariable=second, show="•", width=34, bg=ROW,
                 fg=TEXT, insertbackground=TEXT, relief="flat",
                 font=(FONT, 11)).grid(row=row + 1, column=0, columnspan=2,
                                       sticky="we", ipady=5)
        row += 2
    check = tk.BooleanVar(value=bool(extra_check and extra_check[1]))
    if extra_check:
        tk.Checkbutton(frame, text=extra_check[0], variable=check, bg=BG,
                       fg=TEXT, selectcolor=ROW, activebackground=BG,
                       activeforeground=TEXT, font=(FONT, 9),
                       anchor="w", justify="left",
                       wraplength=330).grid(row=row, column=0, columnspan=2,
                                            sticky="w", pady=(10, 0))
        row += 1
    note = tk.Label(frame, text="", bg=BG, fg="#F28B82", font=(FONT, 9))
    note.grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))
    buttons = tk.Frame(frame, bg=BG)
    buttons.grid(row=row + 1, column=0, columnspan=2, sticky="e",
                 pady=(10, 0))

    def ok(_e=None):
        pw = first.get()
        if confirm and pw != second.get():
            note.configure(text="The two passwords are not the same.")
            return
        if not pw and not optional:
            note.configure(text="Type a password.")
            return
        result["value"] = (pw, check.get()) if extra_check else pw
        win.destroy()

    def cancel(_e=None):
        win.destroy()

    if optional:
        _button(buttons, "No password", lambda: (first.set(""),
                                                 second.set(""), ok())
                ).pack(side="left", padx=(0, 8))
    _button(buttons, "Cancel", cancel).pack(side="left", padx=(0, 8))
    _button(buttons, "OK", ok, primary=True).pack(side="left")
    win.bind("<Return>", ok)
    win.bind("<Escape>", cancel)
    _center(win)
    e1.focus_set()
    win.wait_window()
    return result["value"]


def ask_choice(root, title, intro, choices):
    """One of `choices` (list of (key, label)), or None."""
    win = _dialog(root, title)
    result = {"value": None}
    frame = tk.Frame(win, bg=BG, padx=20, pady=16)
    frame.pack()
    tk.Label(frame, text=intro, bg=BG, fg=TEXT, font=(FONT, 10),
             justify="left", wraplength=340).pack(anchor="w", pady=(0, 10))
    for key, label in choices:
        def pick(k=key):
            result["value"] = k
            win.destroy()
        b = _button(frame, label, pick)
        b.configure(anchor="w", width=34)
        b.pack(fill="x", pady=2)
    win.bind("<Escape>", lambda _e: win.destroy())
    _center(win)
    win.wait_window()
    return result["value"]


def ask_text(root, title, intro, default=""):
    win = _dialog(root, title)
    result = {"value": None}
    frame = tk.Frame(win, bg=BG, padx=20, pady=16)
    frame.pack()
    tk.Label(frame, text=intro, bg=BG, fg=TEXT, font=(FONT, 10),
             justify="left", wraplength=340).pack(anchor="w")
    var = tk.StringVar(value=default)
    entry = tk.Entry(frame, textvariable=var, width=36, bg=ROW, fg=TEXT,
                     insertbackground=TEXT, relief="flat", font=(FONT, 11))
    entry.pack(fill="x", pady=(10, 0), ipady=5)
    buttons = tk.Frame(frame, bg=BG)
    buttons.pack(anchor="e", pady=(12, 0))

    def ok(_e=None):
        result["value"] = var.get()
        win.destroy()

    _button(buttons, "Cancel", win.destroy).pack(side="left", padx=(0, 8))
    _button(buttons, "OK", ok, primary=True).pack(side="left")
    win.bind("<Return>", ok)
    win.bind("<Escape>", lambda _e: win.destroy())
    _center(win)
    entry.focus_set()
    entry.select_range(0, "end")
    win.wait_window()
    return result["value"]


# -- which files -------------------------------------------------------

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


def save_as(ctrl, title, initial, types):
    from tkinter import filedialog
    parent = tk.Toplevel(ctrl.root)
    parent.withdraw()
    parent.attributes("-topmost", True)
    try:
        return filedialog.asksaveasfilename(
            parent=parent, title=title, filetypes=types,
            initialdir=os.path.dirname(initial),
            initialfile=os.path.basename(initial),
            defaultextension=os.path.splitext(initial)[1])
    finally:
        parent.destroy()


def pick_folder(ctrl, title):
    from tkinter import filedialog
    parent = tk.Toplevel(ctrl.root)
    parent.withdraw()
    parent.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(parent=parent, title=title)
    finally:
        parent.destroy()


# -- keys while something runs -----------------------------------------

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
        bar = tk.Frame(win, bg=PANEL, padx=12, pady=8)
        bar.pack(padx=1, pady=1)
        self.dot = tk.Label(bar, text="●", bg=PANEL, fg="#F05252",
                            font=(FONT, 12))
        self.dot.pack(side="left")
        self.time = tk.Label(bar, text="0:00", bg=PANEL, fg=TEXT,
                             font=(FONT, 10, "bold"), width=5)
        self.time.pack(side="left", padx=(6, 8))
        tk.Label(bar, text=label, bg=PANEL, fg=MUTED,
                 font=(FONT, 9)).pack(side="left", padx=(0, 12))
        _button(bar, "Stop  (Enter)", self.stop, primary=True).pack(
            side="left", padx=(0, 6))
        _button(bar, "Cancel  (Esc)", self.cancel).pack(side="left")
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
