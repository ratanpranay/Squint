"""Build Squint.app and the disk image that carries it. Runs on a Mac.

Started by tools/make_dmg.command, which fetches the Python this packs.

What the app is, and why:

**The code does not live in the app.** In-app updates rewrite the code,
and an app bundle whose contents change stops matching its signature —
macOS then calls it damaged, or quietly forgets the Screen Recording
permission it was given. So the bundle carries everything as one archive
and, the first time it is opened, unpacks it to
~/Library/Application Support/Squint/Program. That folder is laid out the
way setup.command lays out the Squint folder — the app, and its Python in
.venv — so the updater works on it exactly as it always has, and never
touches the app in /Applications.

**Its own Python.** A relocatable CPython 3.12 with Tk, and every package
already installed and compiled, Apple's Vision bindings included. Nothing
is downloaded when the app is first opened.

**The interpreter the Dock sees is inside the bundle.** macOS names a
process and picks its Dock icon from where its executable is, so the
launcher runs a copy of the interpreter from Contents/MacOS, pointed at the
unpacked Python. If that copy cannot start for any reason, the launcher
uses the unpacked Python directly: a wrong Dock icon is a blemish, an app
that will not open is not.

**Signed ad hoc, not by a developer.** That is free and keeps permissions
attached to the app between launches. A copy downloaded from the internet
is still stopped by Gatekeeper the first time; see the notes this prints.
"""
import argparse
import compileall
import os
import plistlib
import py_compile
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.make_release import (INCLUDE_DIRS, INCLUDE_FILES, SKIP,  # noqa: E402
                                build_stamp, version_of)

# ".noindex" keeps Spotlight out of it. Every Squint.app Spotlight finds
# is one more Squint in Launchpad, and a build leaves two behind.
WORK = os.path.join(ROOT, "build", "dmg.noindex")
OUT_DIR = os.path.join(ROOT, "dist-dmg")
BUNDLE_ID = "com.squint.app"

# Too large to carry for what it adds: the offline engine pulls in a
# machine-learning framework several gigabytes deep. Installable later from
# Settings, as on Windows.
LEFT_OUT = ("argostranslate",)
# Windows-only files.
NOT_ON_MAC = (".bat",)

LAUNCHER = r"""#!/bin/bash
# Squint.app. The code lives in Application Support, where updates can
# change it without touching this signed bundle. See tools/make_dmg.py.
BUNDLE="$(cd "$(dirname "$0")/../.." && pwd)"
PAYLOAD="$BUNDLE/Contents/Resources/Squint.tar.gz"
BUILT="$BUNDLE/Contents/Resources/build-id"
SUPPORT="$HOME/Library/Application Support/Squint"
APPDIR="$SUPPORT/Program"
LOG="$SUPPORT/launch.log"
mkdir -p "$SUPPORT" 2>/dev/null
echo "--- launcher started $(date) ---" >>"$LOG" 2>&1

# A script gives macOS no processor type to read, so it may start this under
# Rosetta, and then nothing native will load. Run it natively instead.
if [ "$(sysctl -n sysctl.proc_translated 2>/dev/null)" = "1" ] \
   && [ -z "${SNAP_NATIVE:-}" ] \
   && arch -arm64 /usr/bin/true 2>/dev/null; then
    export SNAP_NATIVE=1
    exec arch -arm64 /bin/bash "$0" "$@"
fi

say_alert() {
    echo "ALERT: $1" >>"$LOG" 2>&1
    osascript -e "display alert \"Squint could not start\" message \"$1\"" >/dev/null 2>&1
}

version_of() {       # the x.y.z at the top of a VERSION.txt, or 0.0.0
    local found
    found="$(head -1 "$1" 2>/dev/null | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
    echo "${found:-0.0.0}"
}

newer() {            # is $1 a later version than $2
    local IFS=.
    local a=($1) b=($2) i
    for i in 0 1 2; do
        [ "${a[$i]:-0}" -gt "${b[$i]:-0}" ] && return 0
        [ "${a[$i]:-0}" -lt "${b[$i]:-0}" ] && return 1
    done
    return 1
}

# Unpack on first open, and again when this app carries a newer build than
# the one unpacked. The Python is always replaced as a whole; the code is
# replaced unless what is unpacked is already newer, so opening an older
# disk image never undoes an in-app update.
if [ ! -x "$APPDIR/.venv/bin/python3" ] \
   || [ "$(cat "$APPDIR/.build-id" 2>/dev/null)" != "$(cat "$BUILT")" ]; then
    echo "unpacking $(cat "$BUILT")" >>"$LOG" 2>&1
    osascript -e 'display notification "Setting up for first use…" with title "Squint"' >/dev/null 2>&1
    STAGE="$SUPPORT/.unpack"
    rm -rf "$STAGE" && mkdir -p "$STAGE"
    if ! tar -xzf "$PAYLOAD" -C "$STAGE" >>"$LOG" 2>&1; then
        rm -rf "$STAGE"
        say_alert "The app could not be unpacked. Try downloading it again."
        exit 1
    fi
    mkdir -p "$APPDIR"
    rm -rf "$APPDIR/.venv.old"
    [ -d "$APPDIR/.venv" ] && mv "$APPDIR/.venv" "$APPDIR/.venv.old"
    mv "$STAGE/.venv" "$APPDIR/.venv"
    rm -rf "$APPDIR/.venv.old"
    if ! newer "$(version_of "$APPDIR/VERSION.txt")" "$(version_of "$STAGE/VERSION.txt")"; then
        echo "installing code $(version_of "$STAGE/VERSION.txt")" >>"$LOG" 2>&1
        rm -rf "$APPDIR/app" "$APPDIR/tools"
        (cd "$STAGE" && tar -cf - .) | (cd "$APPDIR" && tar -xf -)
    fi
    rm -rf "$STAGE"
    cp "$BUILT" "$APPDIR/.build-id"
    xattr -dr com.apple.quarantine "$APPDIR" 2>/dev/null || true
fi

cd "$APPDIR" || { say_alert "Could not open $APPDIR"; exit 1; }
export SQUINT_BUNDLE="$BUNDLE"

# The interpreter inside the bundle, so the Dock shows Squint rather than
# Python - if it starts and can see the packages. Otherwise the unpacked
# one, which always can.
# Some Python builds look for their library next to the interpreter
# (../lib); the copy in the bundle is told where it really is. Without it
# the copy cannot start, the unpacked Python runs instead, and macOS lists
# Squint as "python3.12" in its permission lists - so the switch next to
# "Squint" never takes effect.
PY="$APPDIR/.venv/bin/python3"
INNER="$BUNDLE/Contents/MacOS/Squint-python"
export DYLD_FALLBACK_LIBRARY_PATH="$APPDIR/.venv/lib:/usr/local/lib:/usr/lib"
if [ -x "$INNER" ] && PYTHONHOME="$APPDIR/.venv" "$INNER" -c "import tkinter, PIL" >>"$LOG" 2>&1; then
    export PYTHONHOME="$APPDIR/.venv"
    PY="$INNER"
    echo "using the bundled interpreter" >>"$LOG" 2>&1
else
    echo "using $PY" >>"$LOG" 2>&1
fi

"$PY" "$APPDIR/run_app.py" "$@" >>"$LOG" 2>&1
STATUS=$?
if [ $STATUS -ne 0 ]; then
    echo "exited with status $STATUS" >>"$LOG"
    say_alert "It stopped with an error. Details are in ~/Library/Application Support/Squint/launch.log"
fi
exit $STATUS
"""


def say(message):
    print("[dmg] %s" % message, flush=True)


def run(command, **kwargs):
    kwargs.setdefault("check", True)
    return subprocess.run(command, **kwargs)


def mac_requirements():
    """requirements.txt as it reads on a Mac, less what is left out."""
    wanted = []
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            spec, _, marker = line.partition(";")
            marker = marker.replace(" ", "")
            if marker and 'sys_platform=="darwin"' not in marker:
                continue
            name = re.split(r"[<>=!~\s\[]", spec.strip())[0].lower()
            if name in LEFT_OUT:
                continue
            wanted.append(spec.strip())
    return wanted


def copy_app(dest):
    def keep(name):
        return name not in SKIP and not name.endswith(NOT_ON_MAC)

    for folder in INCLUDE_DIRS:
        src = os.path.join(ROOT, folder)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dest, folder),
                            ignore=lambda d, names: [n for n in names
                                                     if not keep(n)])
    for name in INCLUDE_FILES:
        src = os.path.join(ROOT, name)
        if os.path.isfile(src) and keep(name):
            shutil.copy2(src, os.path.join(dest, name))


def compile_tree(*folders):
    mode = py_compile.PycInvalidationMode.CHECKED_HASH
    for folder in folders:
        compileall.compile_dir(folder, quiet=1, workers=0,
                               invalidation_mode=mode)


def build_icon(app, python):
    """Reuse make_app's icon builder, run with the packed Python (it has
    Pillow; the build Python does not)."""
    code = ("import sys; sys.path.insert(0, %r); import make_app; "
            "print(make_app.build_icon(%r, %r))"
            % (os.path.join(ROOT, "tools"), app,
               os.path.join(ROOT, "assets", "icon.png")))
    done = run([python, "-c", code], capture_output=True, text=True,
               check=False)
    return done.stdout.strip().endswith("True")


def check_inner(inner, venv):
    """The bundle's interpreter must start the way the launcher starts it.
    If it cannot, the launcher falls back to the unpacked Python and macOS
    files Squint's permissions under "python3.12" instead of "Squint"."""
    env = dict(os.environ)
    env["PYTHONHOME"] = venv
    env["DYLD_FALLBACK_LIBRARY_PATH"] = os.path.join(venv, "lib") + \
        ":/usr/local/lib:/usr/lib"
    done = run([inner, "-c", "import tkinter, PIL; print('ok')"], env=env,
               capture_output=True, text=True, check=False)
    if done.stdout.strip() != "ok":
        say("WARNING: the app's own interpreter did not start:")
        say((done.stderr or "").strip()[-400:])
        say("The app will still open, but permissions will be listed under")
        say("python3.12 instead of Squint.")
    else:
        say("interpreter ok")


def sign(app):
    """Ad hoc: free, and keeps permissions attached between launches. A
    broken signature is worse than none, so it is checked."""
    inner = os.path.join(app, "Contents", "MacOS", "Squint-python")
    run(["codesign", "--force", "--sign", "-", inner], capture_output=True)
    run(["codesign", "--force", "--sign", "-", app], capture_output=True)
    check = run(["codesign", "--verify", "--strict", app],
                capture_output=True, text=True, check=False)
    if check.returncode != 0:
        raise SystemExit("signature did not verify: %s" % check.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise SystemExit("run this on a Mac")

    version = version_of(build_stamp())
    arch = os.uname().machine
    say("Squint %s for %s" % (version, arch))

    stage = os.path.join(WORK, "stage")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    venv = os.path.join(stage, ".venv")
    shutil.copytree(args.runtime, venv, symlinks=True)
    python = os.path.join(venv, "bin", "python3")
    # The scripts in the folder ask for .venv/bin/python.
    if not os.path.exists(os.path.join(venv, "bin", "python")):
        os.symlink("python3", os.path.join(venv, "bin", "python"))

    say("packages")
    listing = os.path.join(WORK, "requirements-mac.txt")
    with open(listing, "w", encoding="utf-8") as fh:
        fh.write("\n".join(mac_requirements()) + "\n")
    run([python, "-m", "pip", "install", "--quiet",
         "--disable-pip-version-check", "--no-warn-script-location",
         "-r", listing])
    run([python, "-c", "import tkinter, PIL, fitz, Vision, Quartz; "
         "tkinter.Tcl(); print('imports ok')"])

    say("app")
    copy_app(stage)
    say("compiling")
    lib = os.path.join(venv, "lib")
    compile_tree(lib, os.path.join(stage, "app"),
                 os.path.join(stage, "tools"))

    build_id = "%s-%s-%d" % (version, arch, int(os.path.getmtime(listing)))

    say("packing the app")
    app = os.path.join(WORK, "Squint.app")
    shutil.rmtree(app, ignore_errors=True)
    macos = os.path.join(app, "Contents", "MacOS")
    resources = os.path.join(app, "Contents", "Resources")
    os.makedirs(macos)
    os.makedirs(resources)
    run(["tar", "-czf", os.path.join(resources, "Squint.tar.gz"),
         "-C", stage, "."])
    with open(os.path.join(resources, "build-id"), "w") as fh:
        fh.write(build_id + "\n")
    launcher = os.path.join(macos, "Squint")
    with open(launcher, "w", encoding="utf-8") as fh:
        fh.write(LAUNCHER)
    os.chmod(launcher, 0o755)
    inner = os.path.join(macos, "Squint-python")
    shutil.copy2(os.path.realpath(python), inner)
    os.chmod(inner, 0o755)
    check_inner(inner, venv)
    has_icon = build_icon(app, python)

    info = {
        "CFBundleName": "Squint",
        "CFBundleDisplayName": "Squint",
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleVersion": version,
        "CFBundleShortVersionString": version,
        "CFBundleExecutable": "Squint",
        "CFBundlePackageType": "APPL",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "LSArchitecturePriority": ["arm64", "x86_64"],
        "NSAppleEventsUsageDescription":
            "Squint uses this to show translations over other apps.",
        "NSScreenCaptureUsageDescription":
            "Squint reads text from the area of the screen you select.",
    }
    if has_icon:
        info["CFBundleIconFile"] = "icon"
    with open(os.path.join(app, "Contents", "Info.plist"), "wb") as fh:
        plistlib.dump(info, fh)
    sign(app)

    say("disk image")
    root = os.path.join(WORK, "dmgroot")
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    run(["ditto", app, os.path.join(root, "Squint.app")])
    os.symlink("/Applications", os.path.join(root, "Applications"))
    os.makedirs(OUT_DIR, exist_ok=True)
    label = "arm64" if arch == "arm64" else "intel"
    out = os.path.join(OUT_DIR, "Squint-%s-%s.dmg" % (version, label))
    if os.path.exists(out):
        os.remove(out)
    run(["hdiutil", "create", "-quiet", "-volname", "Squint", "-srcfolder",
         root, "-ov", "-format", "UDZO", out])
    # The disk image is the product. The working copies of the app would
    # otherwise sit in Launchpad beside the real one.
    shutil.rmtree(app, ignore_errors=True)
    shutil.rmtree(root, ignore_errors=True)
    say("wrote %s (%.1f MB)" % (out, os.path.getsize(out) / 1e6))
    say("")
    say("Built on this Mac, so it opens here without a warning. Downloaded")
    say("from the internet, macOS stops it the first time: open it, then")
    say("System Settings > Privacy & Security > Open Anyway.")


if __name__ == "__main__":
    main()
