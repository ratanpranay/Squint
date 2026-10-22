"""Pay the first translation's costs while nobody is waiting for it.

Every expensive thing in this app is imported where it is used rather than
at the top of a file, which is right: an app that loads a PDF library on a
machine that never opens a PDF is an app that takes three seconds longer to
appear. But lazy does not mean free — it means the bill arrives on the
first press of the shortcut instead of at startup, which is the one moment
somebody is watching the screen and waiting.

Measured on this machine, cold, once each:

    the PDF library           3050 ms
    the translation client     790 ms
    the imaging library        550 ms
    the language guesser       290 ms   (the first guess, not the import)

Nearly five seconds, and all of it lands on the first snip or the first
document rather than on the second. It is worse on a machine the app was
only just installed on: a virus scanner reads every one of those binary
extensions the first time something opens them, once, and a new PC is
exactly where every file is being opened for the first time. That is why
the app feels slowest on the newest computer, which otherwise makes no
sense at all.

So the bill is paid here, on one background thread, a second or so after
the window is up. Nothing waits on it, nothing fails if it does not
finish, and by the time anyone has read the page and reached for the
shortcut the libraries are loaded and the connection to the translation
service is already open.

Order matters. The things a first *snip* needs come first, because that is
the common case and the one the shortcut is for; the PDF library is last,
because it is the most expensive by a wide margin and the fewest people
need it in their first minute.
"""
import threading
import time

#: Set once the thread has finished, so a second call does nothing.
_done = threading.Event()
_started = threading.Lock()
#: What was warmed and what it cost, for the log.
_report = []


def ready():
    return _done.is_set()


def report():
    """What happened, as one line for the log."""
    if not _report:
        return ""
    total = sum(ms for _name, ms in _report)
    parts = ", ".join("%s %.0fms" % (name, ms) for name, ms in _report)
    return "warm-up %.0fms total — %s" % (total, parts)


def start(delay=0.0, wait=False):
    """Warm everything, on a thread of its own. Safe to call twice."""
    if _done.is_set():
        return
    if not _started.acquire(blocking=False):
        return
    thread = threading.Thread(target=_work, args=(delay,), daemon=True,
                              name="squint-warmup")
    thread.start()
    if wait:
        thread.join()


def _time(name, fn):
    """Run it, remember what it cost, and never let it matter."""
    started = time.time()
    try:
        fn()
    except Exception:
        # Every one of these is an optimisation. A machine without the PDF
        # library is a machine that cannot translate a PDF, which is a
        # thing to say when a PDF is opened — not a reason to log an
        # error at startup on a machine that was never going to open one.
        return
    _report.append((name, 1000 * (time.time() - started)))


def _work(delay):
    if delay:
        time.sleep(delay)

    # -- what a first snip needs ---------------------------------------
    _time("imaging", _imaging)
    _time("reader", _reader)
    _time("language", _language)
    _time("translator", _translator)
    _time("connection", _connection)

    # -- and what a first document needs, which is the expensive one ---
    _time("pdf", _pdf)

    _done.set()
    try:
        from .main import log
        line = report()
        if line:
            log(line)
    except Exception:
        pass


def _imaging():
    from PIL import Image, ImageDraw, ImageFont     # noqa: F401


def _reader():
    """Load whichever reader this machine leads with, and its languages.

    The cheapest thing that makes it happen, not the app's own reading
    pipeline. Asked to read a blank square, that pipeline tries every
    reader in turn and then tries again at other settings, because a page
    with nothing on it looks exactly like a page it has failed to read —
    thirteen seconds of a processor core to warm something that needs
    about a tenth of one. What has to happen is that the engine opens its
    language data, and one call at the lowest level does that.
    """
    from PIL import Image
    blank = Image.new("RGB", (16, 16), "white")
    for name in ("ocr_windows", "ocr_vision"):
        try:
            module = __import__("app." + name, fromlist=[name])
        except Exception:
            continue
        try:
            if not module.available():
                continue
        except Exception:
            pass
        try:
            module.image_to_text(blank)
            return
        except Exception:
            pass
    try:
        import pytesseract
        pytesseract.get_languages()
        pytesseract.image_to_string(blank)
    except Exception:
        pass


def _language():
    """The guesser loads a profile for every language it knows, on its
    first guess rather than on import."""
    from . import translator
    translator.guess_source("hello world, this is a sentence")


def _translator():
    import deep_translator                          # noqa: F401


def _connection():
    """Open the line to the translation service before it is needed.

    `http_pool` keeps a connection between requests, so the second
    translation onwards skips the address lookup, the connection and the
    encryption handshake. The first one pays all three — a third of a
    second to a server on another continent. Opening it here means the
    first one someone actually waits for is the second one the app has
    made.
    """
    from . import translator
    warm = getattr(translator, "warm_connection", None)
    if warm:
        warm()


def _pdf():
    try:
        import pymupdf                              # noqa: F401
    except Exception:
        import fitz                                 # noqa: F401
