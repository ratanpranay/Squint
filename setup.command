#!/bin/bash
# Squint — macOS setup. Double-click this file.
#
# There is no compile step: the app runs from the source in this folder, so a
# newer copy of these files takes effect the next time you start it.
set -u
cd "$(dirname "$0")"
ROOT="$(pwd)"
VENV="$ROOT/.venv"

echo
echo "  ==============================================="
echo "    Squint  -  setup (macOS)"
echo "  ==============================================="
echo

# ---- 1. Python ------------------------------------------------------
#
# Apple's /usr/bin/python3 (from CommandLineTools) is deliberately rejected.
# It is Python 3.9 linked against Tk 8.5, which is deprecated on macOS and
# unstable for GUI apps. We need 3.10+ with Tk 8.6+.
check_python() {
    "$1" - <<'PYEOF' >/dev/null 2>&1
import sys, tkinter
assert sys.version_info >= (3, 10), "python too old"
assert not sys.executable.startswith("/Library/Developer/CommandLineTools"), "apple stub"
assert not sys.base_prefix.startswith("/Library/Developer/CommandLineTools"), "apple stub"
root = tkinter.Tk(); ver = float(root.tk.call("info", "patchlevel").rsplit(".", 1)[0][:3]); root.destroy()
assert ver >= 8.6, "tk too old"
PYEOF
}

# Explicit paths matter: the python.org installer adds itself to PATH via
# your shell profile, which an already-open Terminal has not re-read. Without
# these, setup would still report "not found" right after you installed it.
CANDIDATES="python3.14 python3.13 python3.12 python3.11 python3.10"
for v in 3.14 3.13 3.12 3.11 3.10; do
    CANDIDATES="$CANDIDATES /Library/Frameworks/Python.framework/Versions/$v/bin/python$v"
    CANDIDATES="$CANDIDATES /opt/homebrew/bin/python$v /usr/local/bin/python$v"
done
CANDIDATES="$CANDIDATES /opt/homebrew/bin/python3 /usr/local/bin/python3 python3"

PY=""
for candidate in $CANDIDATES; do
    if [ -x "$candidate" ] || command -v "$candidate" >/dev/null 2>&1; then
        if check_python "$candidate"; then PY="$candidate"; break; fi
    fi
done

if [ -z "$PY" ]; then
    echo "  [1/4] No suitable Python found (needs 3.10+ with Tk 8.6+)."
    # Homebrew may be installed and simply not on this shell's PATH: a
    # double-clicked .command starts from a login shell that has never seen
    # the user's profile, so /opt/homebrew/bin is often missing from it.
    # Looking in the two places Homebrew actually lives is the difference
    # between installing Python automatically and sending somebody to a
    # download page they did not need.
    BREW=""
    for candidate in brew /opt/homebrew/bin/brew /usr/local/bin/brew; do
        if command -v "$candidate" >/dev/null 2>&1; then BREW="$candidate"; break; fi
    done

    if [ -n "$BREW" ]; then
        echo "        Installing one with Homebrew ..."
        "$BREW" install python@3.12 python-tk@3.12 >/dev/null 2>&1 || \
            "$BREW" install python-tk >/dev/null 2>&1 || true
        # Homebrew's own bin directory, in case this shell cannot see it.
        BREW_BIN="$(dirname "$BREW")"
        for v in 3.14 3.13 3.12 3.11 3.10; do
            CANDIDATES="$CANDIDATES $BREW_BIN/python$v"
        done
        for candidate in $CANDIDATES; do
            if [ -x "$candidate" ] || command -v "$candidate" >/dev/null 2>&1; then
                if check_python "$candidate"; then PY="$candidate"; break; fi
            fi
        done
    fi
fi

if [ -z "$PY" ]; then
    echo
    echo "  ==============================================="
    echo "    One thing to install first"
    echo "  ==============================================="
    echo
    echo "  macOS only ships Python 3.9, which uses a version of Tk that"
    echo "  crashes GUI apps. Squint needs 3.10 or newer."
    echo
    echo "  Squint would have installed it for you with Homebrew, but this"
    echo "  Mac does not have Homebrew. Two ways on, both fine:"
    echo
    echo "  A. Install Homebrew first, and Squint does the rest."
    echo "     It is the standard package manager for macOS, it asks for"
    echo "     your password, and it takes a few minutes. Then run"
    echo "     setup.command again and it will install Python itself."
    echo
    echo "  B. Install Python directly, no Terminal needed:"
    echo "     1. Download the latest Python for macOS (the big yellow"
    echo "        button) from the page that opens."
    echo "     2. Open the .pkg and click through the installer."
    echo "     3. Run setup.command again."
    echo
    echo "  Either way it installs alongside Apple's Python and changes"
    echo "  nothing about your system Python."
    echo
    # Homebrew is not installed unattended here on purpose. It wants an
    # admin password, it can pull down Apple's command-line tools, and it
    # changes what other software on the machine resolves to — none of
    # which a setup script should decide on somebody's behalf while they
    # are watching a progress bar.
    if [ ! -t 0 ]; then answer="n"; else
        read -r -p "  Open [A] Homebrew or [B] the Python download page? [A/b/n] " answer
    fi
    case "$answer" in
        [Nn]*) : ;;
        [Bb]*) open "https://www.python.org/downloads/macos/" 2>/dev/null || true ;;
        *) open "https://brew.sh" 2>/dev/null || true
           echo
           echo "  Homebrew's page is open. Its one-line install is on it."
           echo "  Afterwards: run setup.command again." ;;
    esac
    echo
    if [ -t 0 ]; then read -r -p "  Press return to close. " _; fi
    exit 1
fi
echo "  [1/4] Python: $("$PY" --version 2>&1)  ($("$PY" -c 'import sys;print(sys.executable)'))"

# ---- 2. environment + packages --------------------------------------
echo "  [2/4] Installing packages ..."
if [ ! -x "$VENV/bin/python" ]; then
    "$PY" -m venv "$VENV" || { echo "        could not create the environment"; exit 1; }
fi
"$VENV/bin/python" -m pip install --upgrade pip --quiet
"$VENV/bin/python" -m pip install --quiet -r "$ROOT/requirements.txt" || {
    echo "        package install failed - check your connection"; exit 1; }
# macOS-only: Apple Vision bindings and the global-hotkey listener.
"$VENV/bin/python" -m pip install --quiet pyobjc-core pyobjc-framework-Cocoa \
    pyobjc-framework-Quartz pyobjc-framework-Vision pynput || {
    echo "        could not install the macOS extras"; exit 1; }

# ---- 2a. offline translation engine ---------------------------------
# Optional but preferred: once a language is downloaded, translation needs
# no account, no key and no network, and cannot be rate-limited.
"$VENV/bin/python" -m pip install --quiet argostranslate >/dev/null 2>&1 && \
    echo "        Offline engine installed (download a language in Settings)." || \
    echo "        Offline engine unavailable; the app will use web services."
# Drag-and-drop of files onto the window. Optional: Tk has no drag-and-drop
# of its own, and the app is perfectly usable through the Open file button
# if this package will not install.
"$VENV/bin/python" -m pip install --quiet tkinterdnd2 >/dev/null 2>&1 && \
    echo "        Drag-and-drop enabled." || true

# ---- 2b. HTTPS certificates -----------------------------------------
#
# The python.org build ships without CA certificates and does not read the
# macOS keychain, so every HTTPS request fails with CERTIFICATE_VERIFY_FAILED
# until its own "Install Certificates.command" is run. That looks identical to
# the translation service being down, so it is done here rather than left as
# an instruction nobody follows. The app also points at certifi directly, so
# this is belt and braces.
for certfix in /Applications/Python*/Install\ Certificates.command; do
    [ -f "$certfix" ] && bash "$certfix" >/dev/null 2>&1
done
"$VENV/bin/python" - <<'PYEOF' 2>/dev/null
import ssl, urllib.request
try:
    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
except Exception:
    ctx = ssl.create_default_context()
try:
    urllib.request.urlopen("https://www.google.com/generate_204",
                           timeout=8, context=ctx)
    print("        HTTPS certificates OK.")
except Exception as exc:
    print("        HTTPS check: %s" % exc)
PYEOF

# ---- 3. OCR ---------------------------------------------------------
echo "  [3/4] Checking OCR ..."
if "$VENV/bin/python" -c 'import Vision' >/dev/null 2>&1; then
    echo "        Apple Vision is available - nothing to download."
else
    echo "        Apple Vision unavailable; falling back to Tesseract."
    if command -v tesseract >/dev/null 2>&1; then
        echo "        Found Tesseract: $(command -v tesseract)"
    elif command -v brew >/dev/null 2>&1; then
        echo "        Installing Tesseract with Homebrew ..."
        brew install tesseract || true
    else
        echo "        Install Homebrew (https://brew.sh) then: brew install tesseract"
    fi
    "$VENV/bin/python" "$ROOT/tools/fetch_deps.py" --no-prompt || true
fi

# ---- 3b. self-test ---------------------------------------------------
echo "  Checking every part ..."
"$VENV/bin/python" "$ROOT/tools/selftest.py"
SELFTEST=$?
if [ $SELFTEST -ne 0 ]; then
    echo
    echo "  Setup finished, but something above is broken."
    echo "  Send check-report.txt (run check.command) and it can be fixed."
    echo
fi

# ---- 4. app bundle --------------------------------------------------
echo "  [4/4] Building Squint.app ..."
chmod +x "$ROOT"/*.command 2>/dev/null || true
"$VENV/bin/python" "$ROOT/tools/make_app.py" >/dev/null 2>&1

if [ -d "$ROOT/Squint.app" ]; then
    echo "        built."
    if [ ! -t 0 ]; then move="y"; else
        read -r -p "        Move it to your Applications folder? [Y/n] " move
    fi
    case "$move" in
        [Nn]*)
            ln -sfn "$ROOT/Squint.app" "$HOME/Desktop/Squint.app" 2>/dev/null || true
            APP="$ROOT/Squint.app"
            echo "        left in this folder, with an alias on your Desktop."
            ;;
        *)
            rm -rf "$HOME/Applications/Squint.app" 2>/dev/null
            mkdir -p "$HOME/Applications" 2>/dev/null
            if cp -R "$ROOT/Squint.app" "$HOME/Applications/" 2>/dev/null; then
                APP="$HOME/Applications/Squint.app"
                echo "        installed to your Applications folder."
            else
                APP="$ROOT/Squint.app"
                echo "        could not copy; it is in this folder instead."
            fi
            ;;
    esac
else
    APP=""
    ln -sfn "$ROOT/Squint.command" "$HOME/Desktop/Squint.command" 2>/dev/null || true
    echo "        could not build the app; use Squint.command instead."
fi

HOTKEY=$("$VENV/bin/python" - <<'PYEOF'
import sys, os
sys.path.insert(0, os.getcwd())
from app import config
print(config.CONFIG["hotkey"].upper())
PYEOF
)

echo
echo "  ==============================================="
echo "    Ready."
echo
if [ -n "$APP" ]; then
    echo "    Start it:  the Squint icon"
else
    echo "    Start it:  double-click Squint.command"
fi
echo "    Shortcut:  $HOTKEY"
echo
echo "    If the shortcut does nothing, double-click"
echo "    shortcut-test.command - it says why."
echo
echo "    One permission is needed the first time:"
echo
echo "      Screen Recording  - to read text off the screen"
echo
echo "    System Settings > Privacy & Security > Screen Recording,"
echo "    enable Squint, then RESTART it. Until you do,"
echo "    captures come back blank."
echo
echo "    The shortcut itself is registered with macOS directly,"
echo "    so it needs no Accessibility permission."
echo "  ==============================================="
echo
if [ ! -t 0 ]; then
    answer="n"          # started by check.command; it will report instead
else
    read -r -p "  Start Squint now? [y/N] " answer
fi
case "$answer" in
    [Yy]*)
        if [ -n "$APP" ]; then
            open "$APP"
        else
            "$VENV/bin/python" "$ROOT/run_app.py" >/dev/null 2>&1 &
        fi
        ;;
esac
echo
