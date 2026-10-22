#!/bin/bash
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
    echo "Run setup.command first."
    read -r -p "Press return to close. " _
    exit 1
fi
# pythonw is what lets a Tk app own the menu bar and focus properly.
LAUNCHER=".venv/bin/pythonw"
[ -x "$LAUNCHER" ] || LAUNCHER=".venv/bin/python"
"$LAUNCHER" "$(pwd)/run_app.py" >/dev/null 2>&1 &
