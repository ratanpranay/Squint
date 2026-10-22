#!/bin/bash
# Writes diagnose.txt describing this install. Reads only.
cd "$(dirname "$0")"
OUT="$(pwd)/diagnose.txt"
{
  echo "Squint diagnostics"
  echo "Generated: $(date)"
  echo "Folder   : $(pwd)"
  echo
  echo "=== macOS ==="
  sw_vers 2>/dev/null
  echo "arch: $(uname -m)"
  echo
  echo "=== Install ==="
  if [ -x ".venv/bin/python" ]; then
      echo "environment: PRESENT ($(.venv/bin/python --version 2>&1))"
  else
      echo "environment: MISSING - setup.command has not run"
  fi
  ls -l app/main.py app/ui_main.py app/ocr.py 2>/dev/null | awk '{print $6,$7,$8,$9}'
  echo
  echo "=== OCR ==="
  .venv/bin/python - <<'PYEOF' 2>&1
import sys, os
sys.path.insert(0, os.getcwd())
try:
    from app import ocr, ocr_vision
    print("engine:", ocr.engine_name())
    print("vision available:", getattr(ocr_vision, "AVAILABLE", False))
    if not getattr(ocr_vision, "AVAILABLE", False):
        print("reason:", ocr_vision.unavailable_reason())
    else:
        langs = ocr_vision.supported_languages()
        print("vision languages (%d):" % len(langs), ", ".join(langs[:14]))
except Exception as exc:
    print("could not query OCR:", exc)
PYEOF
  command -v tesseract >/dev/null 2>&1 && tesseract --version 2>&1 | head -2
  echo
  echo "=== Settings ==="
  # With the keys taken out. This file exists to be sent to somebody, and
  # it was printing three live API keys in full — so anyone following the
  # instructions handed their keys to whoever was helping them, and to
  # whatever the message passed through on the way. Whether a key is set
  # is the useful fact; the key itself never is.
  { cat "$HOME/Library/Application Support/Squint/config.json" 2>/dev/null \
    || cat "$HOME/.config/Squint/config.json" 2>/dev/null \
    || echo "no config.json yet"; } \
    | sed -E 's/("[a-z_]*(api_key|token|secret)"[[:space:]]*:[[:space:]]*")[^"]+"/\1set, hidden"/g'
  echo
  echo "=== Launch log (last 40 lines) ==="
  tail -n 40 "$HOME/Library/Application Support/Squint/launch.log" 2>/dev/null \
    || echo "no launch log yet"
  echo
  echo "=== App bundle ==="
  for A in "$HOME/Applications/Squint.app" "/Applications/Squint.app" "$(pwd)/Squint.app"; do
    [ -d "$A" ] && echo "found: $A" && \
      grep -m1 '^ROOT=' "$A/Contents/MacOS/Squint" 2>/dev/null
  done
  echo
  echo "=== Log (last 60 lines) ==="
  tail -n 60 "$HOME/Library/Application Support/Squint/squint.log" 2>/dev/null \
    || echo "no log yet"
  echo
  echo "=== Reaching Google ==="
  # Which layer refuses, if one does. On a company network the answer is
  # usually TLS: a proxy that opens encrypted traffic presents its own
  # certificate, the system trusts it so browsers work and Python does not,
  # which is why a page can open in the browser while the app times out.
  .venv/bin/python -c "from app import netcheck;print(netcheck.summary()[1])" \
    2>&1 || echo "skipped - no .venv"
  echo
  echo "=== Packages ==="
  .venv/bin/python -m pip list 2>/dev/null
} > "$OUT"
echo "Written to: $OUT"
open -R "$OUT" 2>/dev/null || true
read -r -p "Press return to close. " _
