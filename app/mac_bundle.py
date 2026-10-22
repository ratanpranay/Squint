"""Keep Squint.app in step with the code it launches.

The bundle is a thin wrapper: a shell script that runs the source in this
folder. That is what makes an update cheap — replace the folder and the app
is updated. Except for the wrapper itself, which an update never touches,
and which is therefore frozen at whatever `setup.command` wrote the day it
was first run.

That went unnoticed for twenty-one releases and then cost a working Mac.
The wrapper carries a copy of the interpreter, checked before use — and the
check asked whether that copy could `import sys, tkinter`, which comes from
the framework and cannot fail. It could not see the environment's packages
at all. The app died on `from PIL import Image` before its first window,
silently, because a bundle has no console. The icon did nothing; the same
code from Terminal worked perfectly.

The launcher fix is one line. Getting it to anybody is the problem this
file exists for: a fault in the wrapper cannot be fixed by an update that
does not rebuild the wrapper, so it survives every release forever.

So the bundle is now checked at startup against the version running, and
rebuilt when it has fallen behind. Once per release, in the background,
and never in a way that can leave the person without an app: the new one is
built beside the old and swapped in, rather than the old one being deleted
first and rebuilt in place.
"""
import os
import plistlib
import shutil
import sys
import threading

from . import config


def log(message):
    """The same launch log the rest of the app writes to.

    Its own copy rather than `main.log`, because main imports this and a
    module cannot import the thing importing it.
    """
    try:
        with open(config.log_path(), "a", encoding="utf-8") as fh:
            fh.write(message.rstrip() + "\n")
    except Exception:
        pass

# Where a bundle can be. The one in the folder is what `setup.command`
# builds; the one in Applications is the copy people drag there.
PLACES = ("~/Applications/Squint.app", "/Applications/Squint.app")

# Long enough to be out of the way of starting up. Nothing waits on this.
AFTER = 4.0


def bundles():
    """Every Squint.app on this machine that launches *this* folder.

    The ROOT check matters. Somebody with two copies of Squint has two
    bundles, and rebuilding the other one would point it at this folder —
    quietly turning their second install into a second shortcut to the
    first.
    """
    here = os.path.abspath(config.app_dir())
    found = []
    for place in PLACES + (os.path.join(here, "Squint.app"),):
        app = os.path.abspath(os.path.expanduser(place))
        if app not in found and os.path.isdir(app) and root_of(app) == here:
            found.append(app)
    return found


def root_of(app):
    """The folder a bundle's launcher runs, or None."""
    try:
        script = os.path.join(app, "Contents", "MacOS", "Squint")
        with open(script, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("ROOT="):
                    return os.path.abspath(line[5:].strip().strip('"'))
                if line.startswith("PY=") or line.startswith("exec "):
                    break          # past the header; no ROOT in this one
    except Exception:
        pass
    return None


def version_of(app):
    """What the bundle says it is."""
    try:
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as fh:
            info = plistlib.load(fh)
        return str(info.get("CFBundleShortVersionString", "") or "")
    except Exception:
        return ""


def stale(app):
    return version_of(app) != config.build_id()


def rebuild(app):
    """Build a fresh bundle beside this one and swap it in.

    Not in place. `make_app.build` clears its destination first, and doing
    that to the app somebody is running — or worse, failing halfway — is
    how a launcher fix turns into a missing application. Built under
    another name, swapped by rename, and the old one removed only once the
    new one is where it belongs.

    Never called while the app is running — see `refresh`, which is where
    the reason is written down. Doing this to the bundle the running
    process was launched from breaks that process's standing with macOS,
    and it cost four releases to work that out. Kept because
    `check.command` does the same work from outside, where it is safe.
    """
    root = os.path.abspath(config.app_dir())
    sys.path.insert(0, os.path.join(root, "tools"))
    try:
        import make_app
    finally:
        try:
            sys.path.remove(os.path.join(root, "tools"))
        except ValueError:
            pass

    fresh, old = app + ".new", app + ".old"
    for path in (fresh, old):
        shutil.rmtree(path, ignore_errors=True)
    make_app.build(destination=fresh, root=root)
    if not os.path.isdir(fresh):
        raise OSError("the new bundle was not built")
    os.rename(app, old)
    try:
        os.rename(fresh, app)
    except Exception:
        os.rename(old, app)        # put back what was working
        raise
    shutil.rmtree(old, ignore_errors=True)


def refresh():
    """Say which bundles have fallen behind. Never raises, never rebuilds.

    It used to rebuild them, which meant renaming and deleting the very
    bundle the running app had been launched from. macOS does not treat
    that as a filing detail: an application whose bundle is moved out from
    under it stops being a well-formed application, and asking it to come
    to the front stops doing anything. The window stays, the menus stay,
    the code runs — and a borderless overlay created afterwards is never
    raised, because there is nothing left for macOS to raise it above.

    Which is precisely the fault this was written in the same release as:
    the snip fired, the screen was captured, the overlay was built at the
    right size in the right place, and nobody ever saw it. Four releases
    went into explaining a symptom of this function.

    So it reports and stops. `check.command` rebuilds the bundle, from
    outside the running app, where doing so is safe — and that is where
    the one line below sends people.
    """
    if sys.platform != "darwin":
        return []
    behind = []
    try:
        for app in bundles():
            was = version_of(app) or "unknown"
            if was == config.build_id():
                continue
            behind.append(app)
            log("bundle     : %s is from %s, this is %s — run check.command "
                "to refresh it" % (app, was, config.build_id()))
    except Exception as exc:
        log("bundle     : check failed — %s" % exc)
    return behind


def start():
    """Check in the background, a few seconds in.

    Rebuilding runs `codesign`, which is not instant, and nothing about the
    app depends on the answer. A person who never sees this happen is the
    intended experience.
    """
    if sys.platform != "darwin":
        return None
    thread = threading.Thread(target=_later, name="bundle-check", daemon=True)
    thread.start()
    return thread


def _later():
    import time
    time.sleep(AFTER)
    refresh()
