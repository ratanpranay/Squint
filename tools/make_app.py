"""Build Squint.app — a real macOS application bundle.

Two reasons this matters beyond having an icon to click:

* macOS attributes permissions to the thing that launched the process. Run
  from Terminal, the Screen Recording and Accessibility grants belong to
  Terminal, and they silently stop applying the moment you launch any other
  way. Given to a bundle, they belong to this app.
* A bundle gets a Dock icon, appears in Spotlight, and can be dragged to
  Applications like anything else.

The bundle is a thin wrapper: its executable is a shell script that runs the
same source in this folder, so updating the folder still updates the app.
"""
import os
import plistlib
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLE_ID = "com.squint.app"

LAUNCHER = """#!/bin/bash
# Thin launcher: the real code lives in the project folder.
ROOT="__ROOT__"
LOGDIR="$HOME/Library/Application Support/Squint"
LOG="$LOGDIR/launch.log"
mkdir -p "$LOGDIR" 2>/dev/null

# Logged before anything can go wrong, so that an empty log is itself an
# answer: it means macOS never ran this script (a Gatekeeper or signature
# problem), rather than the app starting and failing.
echo "--- launcher started $(date) ---" >>"$LOG" 2>&1

# Run natively on Apple Silicon.
#
# A bundle whose executable is a shell script gives LaunchServices no Mach-O
# header to read an architecture from, and it can start the script under
# Rosetta. Everything then runs as Intel: the universal python picks its
# x86_64 half, and every compiled package in the environment — all built
# arm64 — refuses to load:
#
#   ImportError: ... (have 'arm64', need 'x86_64')
#
# The app dies before its first window. It works perfectly from Terminal,
# because a Terminal launch is native. Re-exec ourselves natively so the
# architecture no longer depends on who started us.
# SNAP_NATIVE guards against looping if the re-exec somehow lands translated
# again; one attempt is all this ever needs.
if [ "$(sysctl -n sysctl.proc_translated 2>/dev/null)" = "1" ] \
   && [ -z "${SNAP_NATIVE:-}" ] \
   && arch -arm64 /usr/bin/true 2>/dev/null; then
    echo "started under Rosetta - re-running natively as arm64" >>"$LOG" 2>&1
    export SNAP_NATIVE=1
    exec arch -arm64 /bin/bash "$0" "$@"
fi
echo "arch: $(uname -m)  translated: $(sysctl -n sysctl.proc_translated 2>/dev/null || echo 0)" >>"$LOG" 2>&1

say_alert() {
    echo "ALERT: $1" >>"$LOG" 2>&1
    osascript -e "display alert \"Squint could not start\" message \"$1\"" >/dev/null 2>&1
}

if [ ! -d "$ROOT" ]; then
    say_alert "The Squint folder has moved or been deleted. Expected: $ROOT"
    exit 1
fi
cd "$ROOT" || exit 1

# Plain `python`, not `pythonw`. In a virtual environment pythonw is often a
# stub that is not linked against the framework build, and the difference only
# shows up when launched from a bundle — the process starts, draws nothing and
# exits. `python` is the one verified to work here.
PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
    say_alert "Run setup.command in the Squint folder first."
    exit 1
fi

# Prefer the interpreter that lives inside the bundle.
#
# macOS decides an app's Dock icon and its name in the menu bar from the
# executable's path: a binary under Something.app/Contents/MacOS belongs to
# that bundle, and anything else belongs to nothing. This launcher is a
# shell script, so the process you actually see is whatever python it
# execs — and a python in .venv/bin is outside the bundle. The Dock
# therefore showed the Python rocket and the menu said "Python", on an app
# whose icon was perfectly correct everywhere Finder looked at the bundle
# rather than at the process.
#
# So a copy of the interpreter is placed in Contents/MacOS with a
# pyvenv.cfg beside it, which is exactly the shape of a virtual
# environment. It is verified before use and the original is kept as the
# fallback: a wrong icon is a blemish, and an app that will not start is
# not.
# The check asks for the packages, not for the interpreter.
#
# It used to ask whether the copy could `import sys, tkinter`. Both of those
# come from the framework Python that every copy shares, so the answer was
# yes even when the copy could not see the environment's packages at all —
# it verified the one thing that could not fail. The app then started with
# an interpreter that had no PIL, died on its first import, and did it
# silently, because a bundle has no console. From outside: the icon does
# nothing. From Terminal: works perfectly.
#
# PIL is the right thing to ask for. It is installed, it is not part of any
# Python, and app/ocr.py imports it on line 6 — so if this passes and the
# app still cannot start, the fault is somewhere worth looking.
BUNDLED="$(dirname "$0")/Squint-python"
if [ -x "$BUNDLED" ] \
   && "$BUNDLED" -c "import tkinter, PIL" >/dev/null 2>&1
then
    echo "using the bundled interpreter" >>"$LOG" 2>&1
    PY="$BUNDLED"
else
    echo "bundled interpreter cannot see the packages - using .venv" >>"$LOG" 2>&1
fi

{
    echo "--- launch $(date) ---"
    echo "root: $ROOT"
    echo "python: $PY"
} >>"$LOG" 2>&1

# A GUI app has no console, so anything it prints would vanish. Keeping it
# means a failed launch leaves something to read instead of nothing at all.
"$PY" "$ROOT/run_app.py" "$@" >>"$LOG" 2>&1
STATUS=$?
if [ $STATUS -ne 0 ]; then
    echo "exited with status $STATUS" >>"$LOG"
    say_alert "It stopped with an error. Details are in Console, or run debug.command in the Squint folder."
fi
exit $STATUS
"""


def build_icon(app_path, png_path):
    """PNG -> .icns using iconutil, which every Mac has."""
    if not os.path.isfile(png_path):
        return False
    iconset = os.path.join(app_path, "icon.iconset")
    shutil.rmtree(iconset, ignore_errors=True)
    os.makedirs(iconset, exist_ok=True)
    try:
        from PIL import Image
    except Exception:
        shutil.rmtree(iconset, ignore_errors=True)
        return False

    source = Image.open(png_path).convert("RGBA")
    # The exact set iconutil expects; missing sizes make it refuse.
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            pixels = size * scale
            name = "icon_%dx%d%s.png" % (size, size,
                                         "@2x" if scale == 2 else "")
            source.resize((pixels, pixels), Image.LANCZOS).save(
                os.path.join(iconset, name))

    icns = os.path.join(app_path, "Contents", "Resources", "icon.icns")
    os.makedirs(os.path.dirname(icns), exist_ok=True)
    try:
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns],
                       check=True, capture_output=True, timeout=120)
        ok = os.path.isfile(icns)
    except Exception:
        ok = False
    shutil.rmtree(iconset, ignore_errors=True)
    return ok


def read_version(root):
    """The number at the top of VERSION.txt, or a harmless default."""
    try:
        with open(os.path.join(root, "VERSION.txt"), encoding="utf-8") as fh:
            first = fh.readline().strip()
        found = re.search(r"(\d+\.\d+\.\d+)", first)
        if found:
            return found.group(1)
    except Exception:
        pass
    return "1.0.0"


def bundle_interpreter(macos, root):
    """Copy the venv's python into Contents/MacOS, as a venv of its own.

    Three pieces, and all three are needed: the binary, a pyvenv.cfg beside
    it saying where the real installation is, and the library directory the
    packages live in. Python finds its environment by looking for
    pyvenv.cfg next to the executable or one level up, so a copy of the
    interpreter with those two things around it behaves exactly like
    .venv/bin/python — while living at a path macOS recognises as part of
    the application.

    Failure here is not fatal anywhere. The launcher checks the copy works
    before using it and falls back to .venv, so the worst outcome is the
    icon that was there before.
    """
    try:
        source = os.path.realpath(os.path.join(root, ".venv", "bin",
                                               "python"))
        if not os.path.isfile(source):
            return False
        target = os.path.join(macos, "Squint-python")
        shutil.copy2(source, target)
        os.chmod(target, 0o755)

        config = os.path.join(root, ".venv", "pyvenv.cfg")
        if os.path.isfile(config):
            shutil.copy2(config, os.path.join(macos, "pyvenv.cfg"))

        lib = os.path.join(root, ".venv", "lib")
        link = os.path.join(macos, "lib")
        if os.path.isdir(lib):
            if os.path.islink(link) or os.path.exists(link):
                try:
                    os.remove(link)
                except Exception:
                    shutil.rmtree(link, ignore_errors=True)
            os.symlink(lib, link)
        return True
    except Exception:
        return False


def build(destination=None, root=None):
    root = root or ROOT
    app = destination or os.path.join(root, "Squint.app")
    shutil.rmtree(app, ignore_errors=True)

    macos = os.path.join(app, "Contents", "MacOS")
    resources = os.path.join(app, "Contents", "Resources")
    os.makedirs(macos, exist_ok=True)
    os.makedirs(resources, exist_ok=True)

    executable = os.path.join(macos, "Squint")
    with open(executable, "w", encoding="utf-8") as fh:
        fh.write(LAUNCHER.replace("__ROOT__", root))
    os.chmod(executable, 0o755)

    has_icon = build_icon(app, os.path.join(root, "assets", "icon.png"))
    bundle_interpreter(macos, root)
    version = read_version(root)

    info = {
        "CFBundleName": "Squint",
        "CFBundleDisplayName": "Squint",
        "CFBundleIdentifier": BUNDLE_ID,
        # Read from VERSION.txt rather than written here, where it sat at
        # 1.2.0 through eight releases. A version nobody updates is worse
        # than none: macOS caches it, and "which build is this" then has a
        # confident wrong answer.
        "CFBundleVersion": version,
        "CFBundleShortVersionString": version,
        "CFBundleExecutable": "Squint",
        "CFBundlePackageType": "APPL",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        # Ask for the native architecture first. The launcher re-execs itself
        # if this is ignored (a script executable gives LaunchServices nothing
        # to inspect), but stating the preference is cheap.
        "LSArchitecturePriority": ["arm64", "x86_64"],
        # Shown in the permission prompts, so say why plainly.
        "NSAppleEventsUsageDescription":
            "Squint uses this to show translations over other apps.",
        "NSScreenCaptureUsageDescription":
            "Squint reads text from the area of the screen you select.",
        "NSCameraUsageDescription":
            "Squint shows your camera in Selfie check, only while it is "
            "open. Nothing is recorded or sent.",
    }
    if has_icon:
        info["CFBundleIconFile"] = "icon"

    with open(os.path.join(app, "Contents", "Info.plist"), "wb") as fh:
        plistlib.dump(info, fh)

    # Ad-hoc signature keeps the permission grant attached to this bundle
    # across restarts. But a *broken* signature is worse than none — macOS
    # refuses to launch the app at all — so it is verified, and stripped if
    # it did not take. (--deep is deprecated and can produce exactly that
    # broken state, so it is not used.)
    signed = False
    try:
        result = subprocess.run(["codesign", "--force", "--sign", "-", app],
                                capture_output=True, timeout=180)
        if result.returncode == 0:
            check = subprocess.run(["codesign", "--verify", "--strict", app],
                                   capture_output=True, timeout=120)
            signed = check.returncode == 0
        if not signed:
            subprocess.run(["codesign", "--remove-signature", app],
                           capture_output=True, timeout=120)
    except Exception:
        pass

    return app, has_icon


def main():
    destination = sys.argv[1] if len(sys.argv) > 1 else None
    app, has_icon = build(destination)
    print("built: %s" % app)
    print("icon : %s" % ("yes" if has_icon else "NO - iconutil failed"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
