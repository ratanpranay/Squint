"""Update the app in place, without a re-install.

The app runs from source, and that is what makes this cheap: a new build is
the `app` folder plus a handful of scripts — a few hundred kilobytes — while
the expensive part of an install, the `.venv` with its packages, does not
change from one build to the next. So an update replaces code and leaves
the environment alone.

The one rule that makes it safe on Windows: **never touch .venv**. Python
holds `python.exe` open for as long as it is running, and a file Windows
has open cannot be replaced. `.py` files are read at import and released,
so they can be. Everything here follows from that.

The user's settings, API key and downloaded languages live in the data
folder, not the install folder, so they are never in the blast radius.

Nothing is applied that has not been checked first: the download must match
the checksum the release published, and the unpacked folder must actually
look like Squint. The previous code is kept for one generation so a bad
update can be rolled back rather than reinstalled.
"""
import hashlib
import json
import os
import re
import shutil
import ssl
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

from . import config

TIMEOUT = 20
USER_AGENT = "Squint-updater"

# Where to ask what the newest build is. A plain file on the release, not
# the GitHub API: the API is rate-limited per IP, which on a shared office
# connection means it can refuse for reasons that have nothing to do with
# this user.
DEFAULT_FEED = ("https://github.com/%s/releases/latest/download/version.json")
REPO = "ratanpranay/squint"

# What an update is allowed to replace. Everything else in the folder —
# .venv above all, but also anything the user has put there — is left
# exactly as it is.
REPLACE_DIRS = ("app", "tools", "assets")
REPLACE_FILES = ("VERSION.txt", "requirements.txt", "requirements-offline.txt",
                 "run_app.py", "README.md", "PUBLISHING.md", "setup.bat",
                 "build.bat",
                 "debug.bat", "diagnose.bat", "uninstall.bat", "Squint.bat",
                 "setup.command", "check.command", "debug.command",
                 "diagnose.command", "logs.command", "Squint.command",
                 "shortcut-test.command", "glossary.txt")
NEVER_TOUCH = (".venv", "languages", "logs", "vendor", "build", "dist")

# A release that does not contain these is not Squint, and unpacking it
# over a working install would leave nothing that runs.
REQUIRED = ("VERSION.txt", os.path.join("app", "main.py"),
            os.path.join("app", "config.py"))


class UpdateError(RuntimeError):
    pass


# -- which build is newer -------------------------------------------------
#
# Builds are stamped "2026-08-31 (as)". Comparing those as strings works
# until the letters roll over from (z) to (aa), which sorts wrong. A
# release may therefore carry an explicit integer `serial`; when it does
# not, one is derived from the date and the letters, which is right as long
# as the naming holds.

def _letters_value(letters):
    value = 0
    for char in letters.lower():
        if "a" <= char <= "z":
            value = value * 26 + (ord(char) - 96)
    return value


# Version numbers replaced date-and-letter stamps at 1.0.0. Both have to
# keep sorting correctly, in one direction: every machine in the world
# running a lettered build must be offered 1.0.0, or the rename strands
# them on the last build of the old scheme with no way back.
#
# A lettered serial is the date times a thousand plus the letters —
# 20260831053 for 2026-08-31 (ba), about 2×10^10, and it can only grow
# with the calendar. Versions start above any date this scheme could ever
# reach, so the smallest version outranks the largest stamp by
# construction rather than by luck.
VERSION_BASE = 10 ** 12
SEMVER = re.compile(r"\b(\d+)\.(\d+)\.(\d+)\b")


def build_serial(stamp):
    """A sortable number for a build stamp. 0 when it cannot be read."""
    if stamp is None:
        return 0
    text = str(stamp)
    version = SEMVER.search(text)
    if version:
        major, minor, patch = (int(part) for part in version.groups())
        # Room for a thousand patches and a thousand minors before either
        # can carry into the field above it. 1.2.3 sorts under 1.10.0, the
        # way a version number is meant to and a string comparison does
        # not.
        return (VERSION_BASE + major * 1000000 + minor * 1000 + patch)
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    date = 0
    if match:
        date = int("%s%s%s" % match.groups())
    letters = re.search(r"\(([a-zA-Z]+)\)", text)
    return date * 1000 + _letters_value(letters.group(1) if letters else "")


def current_build():
    return config.build_id()


class Release:
    """What the server says is available."""

    def __init__(self, data):
        self.build = str(data.get("build", "")).strip()
        self.url = str(data.get("url", "")).strip()
        self.sha256 = str(data.get("sha256", "")).strip().lower()
        self.notes = str(data.get("notes", "")).strip()
        try:
            self.serial = int(data.get("serial") or 0)
        except Exception:
            self.serial = 0
        if not self.serial:
            self.serial = build_serial(self.build)
        # An escape hatch for the day the naming changes, or a bad build
        # has to be pulled back. Without it, a release whose serial sorts
        # lower than what people already have can never reach them —
        # everyone is simply stranded on the broken version, with no way
        # to say "take this one anyway".
        self.force = bool(data.get("force"))

    def is_newer_than(self, stamp):
        if self.force:
            return self.build.strip() != str(stamp or "").strip()
        return self.serial > build_serial(stamp)

    def __repr__(self):
        return "<Release %s>" % self.build


def feed_url():
    url = str(config.CONFIG.get("update_feed", "") or "").strip()
    return url or (DEFAULT_FEED % REPO)


# A 404 means two completely different things depending on which of the
# two files is missing, and the fixes are in different places. Saying "no
# release published yet" while the app is displaying that release's notes,
# which is what happened, sends the reader off to look for a release that
# is plainly there.
NOT_FOUND = {
    "feed": "No release published yet, or the update address is wrong.",
    "download": ("The release is published but the file it points to is "
                 "not there — usually the zip was not attached to it, or "
                 "was attached under a different name. Nothing was "
                 "changed."),
}


def _contexts():
    """The ways to trust the update server, best first: Mozilla's list of
    public roots together with this computer's own (translator), then the
    computer's own alone, then the Mac keychain.

    The system's list alone was all the updater used, and on a Windows
    that had not yet been sent the root the update server's certificate
    hangs from - Windows fetches roots when a browser first needs them -
    every check failed with "unable to get local issuer certificate",
    while translating, which used Mozilla's list, worked."""
    out = []
    try:
        from .translator import ssl_context, keychain_context
        first = ssl_context()
        if first is not None:
            out.append(first)
    except Exception:
        keychain_context = None
    try:
        out.append(ssl.create_default_context())
    except Exception:
        pass
    try:
        if keychain_context is not None:
            mac = keychain_context()
            if mac is not None:
                out.append(mac)
    except Exception:
        pass
    return out or [None]


def _open(url, what="feed"):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    contexts = _contexts()
    for i, context in enumerate(contexts):
        try:
            return urllib.request.urlopen(request, timeout=TIMEOUT,
                                          context=context)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise UpdateError(NOT_FOUND.get(what, NOT_FOUND["feed"]))
            raise UpdateError("The update server answered HTTP %s."
                              % exc.code)
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, ssl.SSLError) and i < len(contexts) - 1:
                continue                 # the next way of trusting it
            raise UpdateError("Could not reach the update server: %s"
                              % reason)


def check(url=None):
    """The newest release, or None when this is already it."""
    with _open(url or feed_url()) as response:
        raw = response.read().decode("utf-8", "replace")
    try:
        release = Release(json.loads(raw))
    except Exception:
        raise UpdateError("The update server sent something unreadable.")
    if not release.url:
        raise UpdateError("The release does not say where to download it.")
    return release if release.is_newer_than(current_build()) else None


# -- checking quietly, in the background ---------------------------------
#
# An Update button in Settings is a button nobody presses. Most people
# never open Settings again after the first day, so a release would sit
# there unnoticed and the whole mechanism would be theatre.
#
# So the app looks once a day, on its own, and mentions it once. Never
# downloads anything, never interrupts: it fetches one small file and, if
# there is something new, puts a line in the window. Pressing the button is
# still the user's decision.
CHECK_EVERY = 23 * 3600
CHECK_DELAY_MS = 8000        # let the app finish starting first


def auto_check_enabled():
    return bool(config.CONFIG.get("check_for_updates", True))


def due_for_check(now=None):
    """True when a day has passed. Also true on a clock that went
    backwards — a wrong clock should not stop updates for ever."""
    if not auto_check_enabled():
        return False
    import time
    now = time.time() if now is None else now
    try:
        last = float(config.CONFIG.get("update_last_check", 0) or 0)
    except Exception:
        last = 0
    return last > now or (now - last) >= CHECK_EVERY


def note_check(now=None):
    import time
    config.CONFIG.set("update_last_check", time.time() if now is None else now)


def already_mentioned(build):
    """Say it once. A build the user has already been told about and not
    installed is a decision, not an oversight."""
    return str(config.CONFIG.get("update_seen_build", "")) == str(build)


def mark_mentioned(build):
    config.CONFIG.set("update_seen_build", str(build))


def check_quietly():
    """For the background check. Returns a Release worth mentioning, or
    None — and never raises, because nothing here is worth interrupting
    anyone over. An update server that is down is not the user's problem.
    """
    if not due_for_check():
        return None
    try:
        release = check()
    except Exception:
        # Deliberately still recorded: a network that is refusing should
        # not mean trying again every few seconds for the rest of the day.
        note_check()
        return None
    note_check()
    remember_available(release)
    if release is None or already_mentioned(release.build):
        return None
    return release


def remember_available(release):
    """Kept for the dot on Updates, which stays until the build is
    installed — unlike the line in the window, which is said once."""
    config.CONFIG.set("update_available",
                      str(release.build) if release is not None else "")


def pending_build():
    """The newer build the last check found, or ""."""
    build = str(config.CONFIG.get("update_available", "") or "")
    if not build or build_serial(build) <= build_serial(current_build()):
        return ""
    return build


def download(release, progress=None, into=None):
    """Fetch the zip and prove it is the one the release described."""
    folder = into or tempfile.mkdtemp(prefix="squint-update-")
    path = os.path.join(folder, "update.zip")
    digest = hashlib.sha256()
    with _open(release.url, what="download") as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with open(path, "wb") as out:
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / float(total))
    if release.sha256 and digest.hexdigest() != release.sha256:
        # Refuse rather than repair. A zip that is not the one the release
        # describes is either damaged in transit or not the release at all,
        # and unpacking it over a working install is how a broken update
        # becomes an app that will not start.
        try:
            os.remove(path)
        except Exception:
            pass
        raise UpdateError("The download does not match the checksum the "
                          "release published. Nothing was changed.")
    return path


def _unpack(zip_path, folder):
    """Extract, refusing any member that would escape the folder."""
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            target = os.path.normpath(os.path.join(folder, member))
            if not target.startswith(os.path.normpath(folder) + os.sep) \
                    and target != os.path.normpath(folder):
                raise UpdateError("The update archive is not safe to unpack.")
        archive.extractall(folder)
    return folder


def _find_root(folder):
    """The release may be zipped with or without a top-level folder."""
    candidates = [folder]
    try:
        entries = [os.path.join(folder, name)
                   for name in os.listdir(folder)]
    except Exception:
        entries = []
    candidates += [path for path in entries if os.path.isdir(path)]
    for candidate in candidates:
        if all(os.path.exists(os.path.join(candidate, item))
               for item in REQUIRED):
            return candidate
    raise UpdateError("The download does not look like Squint — it is "
                      "missing app/main.py. Nothing was changed.")


def install(zip_path, target=None, keep_backup=True):
    """Swap the new code in. Returns the folder holding the old code.

    The environment, downloaded languages and logs are not touched, which
    is what makes this quick and what makes it safe to do while the app is
    running: Windows will not let a running python.exe be replaced, and
    nothing here tries to.
    """
    target = target or config.app_dir()
    if not os.access(target, os.W_OK):
        raise UpdateError("Squint is installed somewhere this account "
                          "cannot write to (%s). Move the folder somewhere "
                          "like C:\\Squint and try again." % target)

    staging = tempfile.mkdtemp(prefix="squint-new-")
    backup = tempfile.mkdtemp(prefix="squint-old-")
    try:
        root = _find_root(_unpack(zip_path, staging))

        for name in REPLACE_DIRS:
            source = os.path.join(root, name)
            if not os.path.isdir(source):
                continue
            live = os.path.join(target, name)
            if os.path.isdir(live):
                shutil.move(live, os.path.join(backup, name))
            shutil.copytree(source, live)

        for name in REPLACE_FILES:
            source = os.path.join(root, name)
            if not os.path.isfile(source):
                continue
            live = os.path.join(target, name)
            if os.path.isfile(live):
                shutil.copy2(live, os.path.join(backup, name))
            shutil.copy2(source, live)
    except Exception:
        # Put back whatever was moved before the failure, so a half-applied
        # update never becomes the installed one.
        _restore(backup, target)
        shutil.rmtree(backup, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    if not keep_backup:
        shutil.rmtree(backup, ignore_errors=True)
        return None
    return backup


def _restore(backup, target):
    for name in os.listdir(backup):
        source = os.path.join(backup, name)
        live = os.path.join(target, name)
        try:
            if os.path.isdir(source):
                shutil.rmtree(live, ignore_errors=True)
                shutil.move(source, live)
            else:
                shutil.copy2(source, live)
        except Exception:
            pass


def rollback(backup, target=None):
    """Undo the last install. Kept for one generation."""
    target = target or config.app_dir()
    if not backup or not os.path.isdir(backup):
        raise UpdateError("There is nothing to roll back to.")
    _restore(backup, target)
    return True


def requirements_changed(backup, target=None):
    """True when the packages need reinstalling.

    Almost never, which is the point: reinstalling packages on every update
    would turn a three-second swap into the thing this replaces.
    """
    target = target or config.app_dir()
    old = os.path.join(backup or "", "requirements.txt")
    new = os.path.join(target, "requirements.txt")
    if not os.path.isfile(new):
        return False
    if not os.path.isfile(old):
        return True
    try:
        with open(old, "rb") as a, open(new, "rb") as b:
            return a.read() != b.read()
    except Exception:
        return True


#: What each requirement is called when it is imported. A package's
#: name on the index and its name in an import statement are different
#: things more often than not, and there is no way to work one out from
#: the other.
IMPORT_NAMES = {
    "pillow": "PIL",
    "pymupdf": "fitz",
    "python-docx": "docx",
    "deep-translator": "deep_translator",
    "pyobjc-framework-vision": "Vision",
    "pyobjc-framework-quartz": "Quartz",
}


def _wanted(line):
    """A requirement line as (package, applies to this machine)."""
    line = line.split("#", 1)[0].strip()
    if not line:
        return None, False
    name, _sep, marker = line.partition(";")
    package = re.split(r"[<>=!~\[]", name.strip(), 1)[0].strip().lower()
    if not package:
        return None, False
    marker = marker.strip()
    if marker:
        # Only the one marker this file uses, read plainly rather than
        # with a parser: a marker nobody can read is a requirement nobody
        # can check.
        want = re.search(r'sys_platform\s*==\s*[\'"]([^\'"]+)[\'"]', marker)
        if want and want.group(1) != sys.platform:
            return package, False
    return package, True


def missing_packages(target=None):
    """Which of this build's requirements are not installed.

    The point of asking. Whether a package is *there* is the question
    that matters, and until now the only thing ever asked was whether
    `requirements.txt` had changed since the last update — which answers
    a different question and answers it wrong in the one case that
    matters. A build that adds a package, fails to install it, and is
    then updated again has an unchanged requirements file and a missing
    package, and every check of the file says there is nothing to do.
    That is exactly what happened: the drag-and-drop extension was added
    in one release, not installed by it, and then not installed by the
    next one either, because by then the file had stopped changing.
    """
    import importlib.util
    target = target or config.app_dir()
    listing = os.path.join(target, "requirements.txt")
    missing = []
    try:
        with open(listing, encoding="utf-8") as fh:
            lines = fh.readlines()
    except Exception:
        return missing
    for line in lines:
        package, applies = _wanted(line)
        if not package or not applies:
            continue
        module = IMPORT_NAMES.get(package, package.replace("-", "_"))
        try:
            if importlib.util.find_spec(module) is None:
                missing.append(package)
        except Exception:
            missing.append(package)
    return missing


def own_environment(target=None):
    """True when the app is running from the environment setup made for it.

    Both setup scripts make `.venv` inside the app's folder and install
    into it. Anything else — a developer's environment, a test runner, the
    system's own Python — is not this app's to install packages into, and
    doing it anyway is how a background repair turns into a change to
    somebody's machine they never asked for.
    """
    target = target or config.app_dir()
    try:
        mine = os.path.normcase(os.path.realpath(os.path.join(target,
                                                              ".venv")))
        running = os.path.normcase(os.path.realpath(sys.prefix))
        return running == mine
    except Exception:
        return False


def install_requirements(target=None, progress=None):
    """Install the packages this build needs. Returns (ok, what happened).

    This exists because the alternative was a sentence. When a build
    needed a package the previous one did not, the app said "run setup
    once after it restarts" in a status line and then restarted four
    hundred milliseconds later — so the sentence was on screen for less
    time than it takes to read, and the packages were never installed.
    The one release that actually needed it shipped a feature that
    silently did nothing for everybody who updated from inside the app.

    Installing is the same one command the setup scripts run, with the
    same interpreter the app is already running under, so there is no
    second copy of anything and nothing to get out of step.
    """
    import subprocess
    target = target or config.app_dir()
    listing = os.path.join(target, "requirements.txt")
    if not os.path.isfile(listing):
        return True, "nothing to install"
    exe = sys.executable
    if not exe:
        return False, "could not find the Python this is running under"
    if progress:
        progress("Installing packages…")
    # Wheels shipped with the app, for packages PyPI has only as source.
    #
    # The Python the Windows installer puts down is the embeddable one,
    # and it cannot build a package from source: pip builds in an isolated
    # environment whose paths the embeddable interpreter's ._pth file does
    # not let it see, so every build fails with "Cannot import
    # 'setuptools.build_meta'". PaddleOCR's config library needs one such
    # package (antlr4-python3-runtime 4.9.3, source only). Handing pip a
    # ready-made wheel means nothing has to be built at all.
    command = [exe, "-m", "pip", "install", "--quiet",
               "--disable-pip-version-check", "--prefer-binary"]
    wheels = os.path.join(target, "assets", "wheels")
    if os.path.isdir(wheels):
        command += ["--find-links", wheels]
    command += ["-r", listing]
    kwargs = {"cwd": target, "stdout": subprocess.PIPE,
              "stderr": subprocess.STDOUT}
    if os.name == "nt":
        # No console window flashing up over whatever is on screen.
        kwargs["creationflags"] = 0x08000000                # NO_WINDOW

    def run(args):
        try:
            return subprocess.run(args, timeout=900, **kwargs), None
        except Exception as exc:
            return None, str(exc)[:200]

    done, error = run(command)
    if error:
        return False, error
    if done.returncode != 0 and _needs_a_build(done.stdout):
        # Something else from source, that no shipped wheel covers. Put
        # the build tools where this interpreter can see them and build
        # without the isolated environment it cannot reach.
        prepared, error = run([exe, "-m", "pip", "install", "--quiet",
                               "--disable-pip-version-check",
                               "setuptools", "wheel"])
        if not error and prepared.returncode == 0:
            done, error = run(command[:4] + ["--no-build-isolation"]
                              + command[4:])
            if error:
                return False, error
    if done.returncode != 0:
        tail = (done.stdout or b"").decode("utf-8", "replace").strip()
        return False, (tail.splitlines() or ["pip failed"])[-1][:200]
    return True, "packages installed"


def _needs_a_build(output):
    said = (output or b"").decode("utf-8", "replace")
    return ("BackendUnavailable" in said or "setuptools" in said
            or "build_meta" in said or "Failed to build" in said)


def python_for_relaunch():
    """The interpreter to start the new copy with.

    sys.executable is right whenever the app was started from the venv,
    which is how setup.bat and the shortcut both do it.
    """
    exe = sys.executable or ""
    if os.name == "nt":
        # pythonw keeps a console window from flashing up on every start.
        quiet = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.isfile(quiet):
            return quiet
    return exe


def restart():
    """Start the new code and leave. Never returns."""
    import subprocess
    target = config.app_dir()
    script = os.path.join(target, "run_app.py")
    exe = python_for_relaunch()
    if not exe or not os.path.isfile(script):
        raise UpdateError("Could not work out how to restart. Close Squint "
                          "and start it again to finish the update.")
    kwargs = {"cwd": target, "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200   # detached
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([exe, script], **kwargs)
    # _exit, not sys.exit: the tray icon and the global hotkeys both have
    # threads that would otherwise keep this process alive next to the one
    # that just started, leaving two Squints fighting over one shortcut.
    os._exit(0)
