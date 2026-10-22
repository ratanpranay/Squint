"""Swap the Mac app's window toolkit from Tk 9 back to Tk 8.6, by update.

The Mac app ships with a Python whose Tk is 9.0. On macOS that version
crashes when the display set-up changes (a screen plugged in or out, a
resolution change, waking with a monitor attached): a double release in
TKContentView resetTkLayerBitmapContext, seen in a crash report. It also
paints see-through windows black and reports a trackpad as a different
event. Tk 8.6 has none of this, and is what the Windows build uses.

The Python and its Tk live outside the signed app, under
~/Library/Application Support/Squint/Program/.venv, so an update may
change them. This fetches a Python 3.12 build of the same family whose Tk
is 8.6, takes from it only the Tk parts (the _tkinter module, the Tcl and
Tk libraries and their script folders), puts them in beside the Tk 9
ones, checks that Python loads them, and otherwise puts things back. The
new files are used from the next start.

Only for the Mac app. A Mac running Squint from setup.command has its own
Python, and Windows is untouched.
"""
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import urllib.request

from . import config

API = "https://api.github.com/repos/astral-sh/python-build-standalone/releases/tags/%s"
# Releases of the same Python builds from before they moved to Tk 9, newest
# first. Each is checked for Tk 8.6 before anything is taken from it.
TAGS = ("20250115", "20250106", "20241219", "20241206", "20241205", "20241016", "20241008", "20241002", "20240909", "20240814", "20240726", "20240713")

# What is taken from the download, relative to its python/ folder.
WANTED_DIRS = ("lib/tcl8.6/", "lib/tk8.6/", "lib/tcl8/", "lib/itcl4", "lib/thread2")
WANTED_FILES = ("lib/libtcl8.6.dylib", "lib/libtk8.6.dylib")
TKINTER = "lib/python3.12/lib-dynload/_tkinter.cpython-312-darwin.so"

_state = {"thread": None, "result": None}


def _log(message):
    try:
        from .main import log
        log("toolkit    : %s" % message)
    except Exception:
        pass


def venv_root():
    """The Mac app's Python, or None when this is not the Mac app."""
    if sys.platform != "darwin":
        return None
    prefix = os.path.realpath(sys.prefix)
    if "Application Support/Squint/Program/.venv" not in prefix:
        return None
    return prefix


def current_tk():
    try:
        import tkinter
        return float(tkinter.TkVersion)
    except Exception:
        return 0.0


def needed():
    """True on the Mac app while its Tk is 9, and the swap has not been
    done or given up on."""
    root = venv_root()
    if root is None or current_tk() < 9.0:
        return False
    if config.CONFIG.get("tk86_swap_failed"):
        return False
    return not already_swapped(root)


def already_swapped(root):
    return os.path.isdir(os.path.join(root, "lib", "tk8.6")) and \
        os.path.isfile(os.path.join(root, TKINTER + ".tk9"))


def _triple():
    import platform
    return ("aarch64-apple-darwin" if platform.machine() == "arm64"
            else "x86_64-apple-darwin")


def _open(url, timeout=60):
    request = urllib.request.Request(url, headers={"User-Agent": "Squint"})
    try:
        from .translator import ssl_context
        context = ssl_context()
    except Exception:
        context = None
    return urllib.request.urlopen(request, timeout=timeout, context=context)


def _asset(tag):
    with _open(API % tag, timeout=30) as reply:
        release = json.loads(reply.read().decode("utf-8"))
    suffix = "-%s-install_only.tar.gz" % _triple()
    for asset in release.get("assets") or []:
        name = asset.get("name", "")
        if name.startswith("cpython-3.12.") and name.endswith(suffix):
            return asset.get("browser_download_url")
    return None


def _wanted(member):
    name = member.name
    if not name.startswith("python/"):
        return None
    rel = name[len("python/"):]
    if rel in WANTED_FILES or rel == TKINTER:
        return rel
    if any(rel.startswith(d) for d in WANTED_DIRS):
        return rel
    return None


def _fetch(url, stage):
    """Stream the archive, keeping only the Tk parts. True if Tk 8.6 was in
    it."""
    found = False
    with _open(url, timeout=120) as reply:
        with tarfile.open(fileobj=reply, mode="r|gz") as archive:
            for member in archive:
                rel = _wanted(member)
                if rel is None:
                    continue
                if member.issym() or member.islnk():
                    continue
                dest = os.path.join(stage, rel)
                if member.isdir():
                    os.makedirs(dest, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    continue
                with open(dest, "wb") as out:
                    shutil.copyfileobj(source, out)
                os.chmod(dest, member.mode | 0o200)
                # Older builds link Tcl and Tk into _tkinter itself and
                # ship only the script folders; newer ones have separate
                # libraries. The tk8.6 folder is in both.
                if rel.startswith("lib/tk8.6/"):
                    found = True
    return found and os.path.isfile(os.path.join(stage, TKINTER))


def _install(stage, root):
    """Put the staged files in place. Every file lands by rename, so a
    library the running app has loaded is never written over."""
    placed = []
    for base, _dirs, files in os.walk(stage):
        for name in files:
            source = os.path.join(base, name)
            rel = os.path.relpath(source, stage)
            dest = os.path.join(root, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if rel == TKINTER and os.path.exists(dest):
                backup = dest + ".tk9"
                if not os.path.exists(backup):
                    shutil.copy2(dest, backup)
            temp = dest + ".new"
            shutil.copy2(source, temp)
            os.replace(temp, dest)
            placed.append(rel)
    return placed


def _restore(root):
    dest = os.path.join(root, TKINTER)
    backup = dest + ".tk9"
    if os.path.exists(backup):
        os.replace(backup, dest)


def _works(root):
    """Start the app's own Python and see that it now gets Tk 8.6."""
    code = ("import tkinter, sys; t = tkinter.Tcl(); "
            "sys.exit(0 if tkinter.TkVersion < 9 else 3)")
    env = dict(os.environ)
    env["PYTHONHOME"] = root
    env["TCL_LIBRARY"] = os.path.join(root, "lib", "tcl8.6")
    env["TK_LIBRARY"] = os.path.join(root, "lib", "tk8.6")
    try:
        result = subprocess.run([sys.executable, "-c", code], env=env,
                                capture_output=True, timeout=60)
        if result.returncode != 0:
            _log("check failed: %s" % (result.stderr or b"")[-300:])
        return result.returncode == 0
    except Exception as exc:
        _log("check failed: %s" % exc)
        return False


def undo_after_crash(detail):
    """Called when Squint failed to start. If Tk 8.6 is in place and the
    failure came from the window toolkit or pictures, put Tk 9 back and stop
    trying. True if it did."""
    root = venv_root()
    if root is None or not os.path.isfile(os.path.join(root, TKINTER + ".tk9")):
        return False
    words = ("tkinter", "Tcl", "_imagingtk", "ImageTk", "tk8.6")
    if not any(w in (detail or "") for w in words):
        return False
    _restore(root)
    config.CONFIG.set("tk86_swap_failed", True)
    return True


def swap():
    """Do the whole thing. Returns (ok, message). Never leaves the app
    without a working Tk: anything short of a checked success is undone."""
    root = venv_root()
    if root is None:
        return False, "not the Mac app"
    stage = os.path.join(config.data_dir(), "toolkit-stage")
    last = "no release with Tk 8.6 was found"
    for tag in TAGS:
        shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(stage, exist_ok=True)
        try:
            url = _asset(tag)
            if not url:
                continue
            if not _fetch(url, stage):
                last = "%s has no Tk 8.6" % tag
                continue
        except Exception as exc:
            last = "%s: %s" % (tag, str(exc)[:120])
            continue
        try:
            placed = _install(stage, root)
        except Exception as exc:
            _restore(root)
            last = "could not put it in place: %s" % str(exc)[:120]
            break
        if _works(root):
            shutil.rmtree(stage, ignore_errors=True)
            _log("Tk 8.6 from %s in place (%d files)" % (tag, len(placed)))
            return True, "ok"
        _restore(root)
        last = "Tk 8.6 from %s did not load" % tag
        break
    shutil.rmtree(stage, ignore_errors=True)
    _log("swap not done: %s" % last)
    return False, last


def start(on_done=None):
    """Run `swap` in the background, once."""
    thread = _state.get("thread")
    if thread is not None and thread.is_alive():
        return False

    def work():
        try:
            ok, message = swap()
        except Exception as exc:
            ok, message = False, str(exc)[:160]
        if not ok:
            config.CONFIG.set("tk86_swap_failed", True)
        _state["result"] = (ok, message)
        if on_done:
            try:
                on_done(ok, message)
            except Exception:
                pass

    thread = threading.Thread(target=work, daemon=True)
    _state["thread"] = thread
    thread.start()
    return True
