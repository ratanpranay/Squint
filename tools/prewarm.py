"""Load everything once, at install time, so the first use is not the slow one.

Run by the Windows installer as its last step, hidden, with the progress bar
still on screen. Nothing here changes anything; it only makes the machine
read and check every file the app will need.

Why at install time as well as at startup: on a machine that has never run
the app, the first load of each library is slow twice over — the files come
off the disk for the first time, and the virus scanner reads every binary
extension once before letting it load. `warmup` already moves that cost off
the first snip in every session. Doing it here as well means the very first
session, the one on a brand-new PC, starts from files the machine has
already seen.
"""
import importlib
import os
import pkgutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

STARTED = time.time()
LIBRARIES = ("PIL.Image", "PIL.ImageDraw", "PIL.ImageFont", "PIL.ImageGrab",
             "mss", "pytesseract", "deep_translator", "requests", "certifi",
             "langdetect", "pystray", "fitz", "pymupdf", "docx", "lxml.etree",
             "reportlab.pdfgen.canvas", "tkinterdnd2",
             "winsdk.windows.media.ocr", "winsdk.windows.graphics.imaging",
             "winsdk.windows.storage.streams", "winsdk.windows.globalization")


def say(message):
    print("[prewarm %5.1fs] %s" % (time.time() - STARTED, message), flush=True)


def load(name):
    try:
        importlib.import_module(name)
        return True
    except Exception as exc:              # an optimisation, never a failure
        say("skipped %s: %s" % (name, str(exc)[:120]))
        return False


def main():
    for name in LIBRARIES:
        load(name)
    say("libraries")

    import app
    for info in pkgutil.iter_modules(app.__path__):
        name = "app." + info.name
        # The platform-specific readers for other systems fail to import
        # here by design.
        if info.name in ("ocr_vision", "mac_bundle"):
            continue
        load(name)
    say("app modules")

    # Tk and its drag-and-drop extension are native libraries loaded when
    # the first window is made, not on import.
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
        root.withdraw()
        root.update_idletasks()
        root.destroy()
        say("windowing")
    except Exception as exc:
        say("windowing skipped: %s" % str(exc)[:120])

    # The app's own warm-up, step by step, with the reader last: it is the
    # one step that talks to the operating system's text recognition, and
    # if that fails hard on some machine everything else is already done.
    try:
        from app import warmup
        for name in ("imaging", "language", "translator", "connection",
                     "pdf", "reader"):
            warmup._time(name, getattr(warmup, "_" + name))
            say("warmed %s" % name)
        say(warmup.report() or "warm-up done")
    except Exception as exc:
        say("warm-up skipped: %s" % str(exc)[:120])
    return 0


# The installer waits for this, so it must end whatever happens inside it:
# one library that hangs on one machine must not leave an install stuck on
# "Preparing". Everything runs on a daemon thread and the process leaves
# when the thread is done or the time is up, whichever is first.
LIMIT_SECONDS = 90


if __name__ == "__main__":
    import threading
    worker = threading.Thread(target=main, daemon=True)
    worker.start()
    worker.join(LIMIT_SECONDS)
    if worker.is_alive():
        say("stopped after %ds - the rest warms up on first start"
            % LIMIT_SECONDS)
    sys.stdout.flush()
    os._exit(0)
