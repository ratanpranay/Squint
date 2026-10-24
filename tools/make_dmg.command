#!/bin/bash
# Build Squint-<version>-<arch>.dmg on this Mac.
#
#     bash tools/make_dmg.command
#
# Fetches a self-contained Python 3.12 for this Mac's processor, then hands
# over to tools/make_dmg.py, which installs the packages into it, builds
# Squint.app around it and packs the disk image. Needs nothing installed
# first: curl, tar, shasum, hdiutil and codesign are part of macOS.
#
# The Python is python-build-standalone - the same relocatable builds that
# uv and many other tools install - checked against the checksum file
# published with it.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
WORK="$ROOT/build/dmg.noindex"   # kept out of Spotlight and Launchpad
rm -rf "$ROOT/build/dmg"          # the folder earlier builds used
mkdir -p "$WORK"

case "$(uname -m)" in
    arm64)  TRIPLE="aarch64-apple-darwin" ;;
    x86_64) TRIPLE="x86_64-apple-darwin" ;;
    *) echo "Unsupported processor: $(uname -m)"; exit 1 ;;
esac

RUNTIME="$WORK/python"
# Tk 8.6, not 9. The newest Python builds carry Tk 9.0, which on macOS
# crashes when a screen is plugged in or out, draws see-through windows
# black and reports a trackpad as a new kind of event. These releases are
# from before that change; each is checked for Tk 8.6 before it is used.
TAGS="20250115 20250106 20241219 20241206 20241205 20241016 20241008 20241002 20240909 20240814 20240726 20240713"

if [ ! -x "$RUNTIME/bin/python3" ] || [ ! -d "$RUNTIME/lib/tk8.6" ]; then
    rm -rf "$RUNTIME"
    for TAG in $TAGS; do
        echo "[dmg] finding Python 3.12 with Tk 8.6 for $TRIPLE in $TAG ..."
        API="https://api.github.com/repos/astral-sh/python-build-standalone/releases/tags/$TAG"
        # On GitHub's build machines the token avoids the shared rate limit.
        AUTH=()
        [ -n "${GH_TOKEN:-}" ] && AUTH=(-H "Authorization: Bearer $GH_TOKEN")
        RELEASE="$(curl -fsSL ${AUTH[@]+"${AUTH[@]}"} "$API" || true)"
        URL="$(printf '%s' "$RELEASE" | grep -Eo "https://[^\"]*/cpython-3\.12\.[0-9]+(%2B|\+)[0-9]+-$TRIPLE-install_only\.tar\.gz" | head -1)"
        [ -z "$URL" ] && continue
        SUMS="$(printf '%s' "$RELEASE" | grep -Eo 'https://[^"]*/SHA256SUMS' | head -1)"
        NAME="$(basename "$URL" | sed 's/%2B/+/g')"
        echo "[dmg] downloading $NAME"
        curl -fL --progress-bar -o "$WORK/$NAME" "$URL" || continue
        if [ -n "$SUMS" ]; then
            WANT="$(curl -fsSL "$SUMS" | grep " $NAME\$" | awk '{print $1}')"
            HAVE="$(shasum -a 256 "$WORK/$NAME" | awk '{print $1}')"
            if [ -z "$WANT" ] || [ "$WANT" != "$HAVE" ]; then
                echo "Checksum does not match the published one. Stopping."
                rm -f "$WORK/$NAME"
                exit 1
            fi
            echo "[dmg] checksum ok"
        fi
        rm -rf "$RUNTIME"
        tar -xzf "$WORK/$NAME" -C "$WORK"      # unpacks into $WORK/python
        # Older builds link Tk into _tkinter and ship only its script
        # folder, so the folder is the test - not a libtk8.6.dylib.
        if [ -d "$RUNTIME/lib/tk8.6" ]; then
            echo "[dmg] Tk 8.6 - good"
            break
        fi
        echo "[dmg] $TAG has Tk 9, trying an older release"
        rm -rf "$RUNTIME"
    done
    if [ ! -d "$RUNTIME/lib/tk8.6" ]; then
        echo "Could not find a Python 3.12 build with Tk 8.6. Stopping."
        exit 1
    fi
    xattr -dr com.apple.quarantine "$RUNTIME" 2>/dev/null || true
fi

exec "$RUNTIME/bin/python3" "$ROOT/tools/make_dmg.py" --runtime "$RUNTIME" "$@"
