#!/bin/bash
# Double-click this to find out whether the keyboard shortcut really works.
cd "$(dirname "$0")"
ROOT="$(pwd)"
if [ ! -x "$ROOT/.venv/bin/python" ]; then
    echo "  Run setup.command first."
    read -r -p "  Press return to close. " _
    exit 1
fi
"$ROOT/.venv/bin/python" "$ROOT/tools/hotkey_probe.py"
echo
read -r -p "  Press return to close. " _
