#!/bin/bash
# Same app, with output shown. Use this if something misbehaves.
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
    echo "Run setup.command first."
    read -r -p "Press return to close. " _
    exit 1
fi
echo "Starting Squint with output shown. Ctrl-C or close to quit."
echo "---------------------------------------------------------------"
.venv/bin/python "$(pwd)/run_app.py"
echo "---------------------------------------------------------------"
echo "Exited with code $?."
read -r -p "Press return to close. " _
