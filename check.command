#!/bin/bash
# Tests every part of Squint and says which one is broken.
# If the app has not been set up in this folder yet, it sets it up first,
# so this is always a safe single thing to run.
cd "$(dirname "$0")"
ROOT="$(pwd)"
OUT="$ROOT/check-report.txt"

echo
if [ -f "$ROOT/VERSION.txt" ]; then
    echo "  $(head -1 "$ROOT/VERSION.txt")"
fi
echo "  Folder: $ROOT"
echo

if [ ! -x "$ROOT/.venv/bin/python" ]; then
    echo "  This folder is not set up yet. Doing that first — a few minutes."
    echo "  ---------------------------------------------------------------"
    bash "$ROOT/setup.command" </dev/null
    echo "  ---------------------------------------------------------------"
    if [ ! -x "$ROOT/.venv/bin/python" ]; then
        echo
        echo "  Setup did not finish. The messages above say why."
        read -r -p "  Press return to close. " _
        exit 1
    fi
fi

# Always rebuild the app bundle. Its launcher is a file like any other, so an
# update that fixes the launcher does nothing until the bundle is rebuilt —
# and skipping that is exactly how a "fixed" app keeps failing identically.
echo "  Rebuilding the app icon ..."
"$ROOT/.venv/bin/python" "$ROOT/tools/make_app.py" >/dev/null 2>&1
if [ -d "$ROOT/Squint.app" ]; then
    mkdir -p "$HOME/Applications" 2>/dev/null
    rm -rf "$HOME/Applications/Squint.app" 2>/dev/null
    cp -R "$ROOT/Squint.app" "$HOME/Applications/" 2>/dev/null \
        && echo "  Updated: ~/Applications/Squint.app"
fi
chmod +x "$ROOT"/*.command 2>/dev/null || true
echo

"$ROOT/.venv/bin/python" "$ROOT/tools/selftest.py" 2>&1 | tee "$OUT"
echo
echo "  Saved to: $OUT"
read -r -p "  Press return to close. " _
