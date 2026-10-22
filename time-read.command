#!/bin/bash
# Times each stage of a screen read against the copy of Squint installed
# here. Changes nothing, installs nothing, needs no new build. Open the
# page you want to test BEFORE running this - it reads the screen as it
# finds it, and writes time-read.txt beside this file.
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
    echo "Run setup.command first - there is no environment here yet."
    read -r -p "Press return to close. " _
    exit 1
fi
".venv/bin/python" "$(pwd)/tools/time_read.py"
