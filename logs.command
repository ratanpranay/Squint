#!/bin/bash
# Double-click this to collect every log into one file on your Desktop.
DIR="$HOME/Library/Application Support/Squint"
OUT="$HOME/Desktop/squint-logs.txt"
{
    echo "=== version ==="
    cat "$(dirname "$0")/VERSION.txt" 2>/dev/null
    echo
    for f in "$DIR"/*.log; do
        [ -f "$f" ] || continue
        echo "=== $(basename "$f") ==="
        tail -80 "$f"
        echo
    done
} > "$OUT" 2>&1
echo
echo "  Saved to your Desktop as squint-logs.txt"
echo "  Drag that file into the chat."
open -R "$OUT" 2>/dev/null
read -r -p "  Press return to close. " _
