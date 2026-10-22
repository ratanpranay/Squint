"""Check every moving part and name the one that is broken.

Written because remote debugging by screenshot is slow: this runs on the
machine that has the problem and prints a verdict per subsystem, so a single
double-click replaces several rounds of questions.
"""
import os
import subprocess
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS, FAIL, WARN = "  ok  ", " FAIL ", " warn "
results = []


def check(name, fn, fatal=False):
    try:
        detail = fn()
        results.append((PASS, name, detail or ""))
        return True
    except Exception as exc:
        results.append((FAIL if fatal else WARN, name,
                        "%s: %s" % (type(exc).__name__, exc)))
        if os.environ.get("SNAP_TRACE"):
            traceback.print_exc()
        return False


def c_python():
    assert sys.version_info >= (3, 10), "needs 3.10+, this is %s" % (
        ".".join(map(str, sys.version_info[:3])))
    return "%s at %s" % (".".join(map(str, sys.version_info[:3])),
                         sys.executable)


def c_tk():
    import tkinter
    root = tkinter.Tk()
    version = root.tk.call("info", "patchlevel")
    root.destroy()
    assert float(str(version)[:3]) >= 8.6, "Tk %s is too old" % version
    return "Tk %s" % version


def c_window():
    """Build the real main window off-screen — the app's biggest risk."""
    import tkinter
    from app.ui_main import MainWindow

    class Fake:
        def __init__(self, root):
            self.root = root
            self.icon_path = None
        def trigger_snip(self): pass
        def refresh_tray(self): pass
        def apply_hotkeys(self, a, b): return True, ""
        def set_run_at_startup(self, e): return True, ""
        def show_window(self): pass
        def request_restart_for_theme(self): pass

    root = tkinter.Tk()
    root.withdraw()
    window = MainWindow(Fake(root))
    window.update_idletasks()
    count = len(window.winfo_children())
    window.destroy()
    root.destroy()
    assert count > 0, "window built but is empty"
    return "main window builds"


def c_foreground():
    """The check that would have caught 'it runs but never appears'."""
    import sys as _sys
    if _sys.platform != "darwin":
        return "n/a on this platform"
    from AppKit import NSApplication, NSApplicationActivationPolicyRegular
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    return "AppKit present; app can be promoted to the foreground"


def c_window_visible():
    """Build the window and confirm macOS actually puts it on screen."""
    import tkinter
    from app import platform_util
    platform_util.become_foreground_app()
    root = tkinter.Tk()
    root.geometry("320x140+120+120")
    root.update()
    root.update_idletasks()
    viewable = bool(root.winfo_viewable())
    geometry = root.winfo_geometry()
    root.destroy()
    assert viewable, ("a window was created but macOS did not display it "
                      "(geometry %s)" % geometry)
    return "a test window displayed at %s" % geometry


def c_screenshot():
    import mss
    from PIL import Image
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[0])
        image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    colours = image.convert("RGB").getcolors(maxcolors=4)
    if colours and len(colours) == 1:
        raise AssertionError(
            "capture is a single flat colour — macOS Screen Recording "
            "permission is almost certainly not granted to this app")
    return "%dx%d captured" % image.size


def c_ocr():
    from app import ocr
    from PIL import Image, ImageDraw, ImageFont
    engine = ocr.engine_name()
    image = Image.new("RGB", (420, 60), "white")
    draw = ImageDraw.Draw(image)
    try:
        from app import overlay
        font = overlay.load_font("default", 26)
    except Exception:
        font = ImageFont.load_default()
    draw.text((12, 14), "Hello world", font=font, fill="black")
    text, used = ocr.image_to_text(image)
    assert "ello" in text, "engine ran but read %r" % text[:40]
    return "%s read the test image (%s)" % (engine, used)


def _cjk_font(size):
    for path in ("/System/Library/Fonts/PingFang.ttc",
                 "/System/Library/Fonts/Hiragino Sans GB.ttc",
                 "/System/Library/Fonts/Supplemental/Songti.ttc",
                 "/System/Library/Fonts/STHeiti Light.ttc",
                 "/Library/Fonts/Arial Unicode.ttf"):
        if os.path.isfile(path):
            try:
                from PIL import ImageFont
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return None


def c_ocr_cjk():
    """Read Chinese, not just English.

    The English-only OCR check passed for days while the app turned a Chinese
    page into Latin gibberish, because Vision takes its language list in
    priority order and English was first. A test that only ever shows the
    engine English cannot notice that.
    """
    from app import ocr
    from PIL import Image, ImageDraw
    font = _cjk_font(30)
    if font is None:
        raise AssertionError("no Chinese font on this Mac to test with")
    phrase = "宝马全球纯电动车交付"
    image = Image.new("RGB", (460, 70), "white")
    ImageDraw.Draw(image).text((12, 14), phrase, font=font, fill="black")
    text, used = ocr.image_to_text(image)
    hits = sum(1 for ch in phrase if ch in text)
    assert hits >= len(phrase) * 0.6, (
        "read %r instead of %r — the engine is not recognising Chinese"
        % (text[:40], phrase))
    return "%d/%d characters correct (%s)" % (hits, len(phrase), used)


def c_ocr_cyrillic():
    """Read Russian, not the Latin letters that look like it.

    The Chinese check did not catch this: Cyrillic fails differently. Han
    characters have no Latin lookalikes, so a wrong alphabet there produces
    obvious noise, but АБВГДЕЁ reads cleanly and confidently as "AEBTAEE"
    — text, not gibberish, and nothing downstream can tell. Only comparing
    against what was actually written catches it.
    """
    from app import ocr
    from PIL import Image, ImageDraw, ImageFont
    phrase = "Доброе утро"
    font = None
    for path in ("/System/Library/Fonts/Helvetica.ttc",
                 "/System/Library/Fonts/Supplemental/Arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(path, 34)
            break
        except Exception:
            continue
    if font is None:
        raise AssertionError("no font available to draw Cyrillic with")
    image = Image.new("RGB", (420, 80), "white")
    ImageDraw.Draw(image).text((14, 18), phrase, font=font, fill="black")
    text, used = ocr.image_to_text(image)
    hits = sum(1 for ch in phrase if ch.strip() and ch in text)
    letters = sum(1 for ch in phrase if ch.strip())
    assert hits >= letters * 0.6, (
        "read %r instead of %r — Cyrillic is being read as Latin"
        % (text[:40], phrase))
    return "%d/%d characters correct (%s)" % (hits, letters, used)


def c_windows_ocr():
    """Windows should read with its own engine, not Tesseract.

    Tesseract is markedly worse on screen text and worst of all on
    Chinese, which is the language this app exists for — so on Windows
    this check failing means the build works but reads badly.
    """
    if sys.platform != "win32":
        return "n/a on this platform"
    from app import ocr, ocr_windows
    if not ocr_windows.AVAILABLE:
        raise AssertionError(ocr_windows.unavailable_reason())
    langs = ocr_windows.available_languages()
    if not langs:
        raise AssertionError(
            "Windows OCR has no languages installed. Add one under "
            "Settings > Time & Language > Language & region.")
    return "%s, languages: %s" % (ocr.engine_name(), ", ".join(langs[:6]))


def c_hotkey_backend():
    from app import hotkey_carbon
    if sys.platform != "darwin":
        return "n/a on this platform"
    if not hotkey_carbon.AVAILABLE:
        raise AssertionError("Carbon unavailable; will fall back to a watcher")
    return "Carbon available (consumes the keystroke, needs no permission)"


def c_hotkey_live():
    from app import config, hotkey
    manager = hotkey.HotkeyManager()
    hid = manager.register(config.CONFIG["hotkey"], lambda: None)
    manager.start()
    ready = manager.wait_ready(8.0)
    error = manager.error_for(hid)
    backend = getattr(manager, "backend", "?")
    manager.stop()
    if error:
        raise AssertionError(error)
    assert ready, "the watcher never reported ready"
    return "%s registered via %s" % (config.CONFIG["hotkey"].upper(), backend)


def c_architecture():
    """Is this Python the same architecture as the compiled packages?

    On Apple Silicon a universal Python can be started as Intel — which the
    app bundle did for days — and then every arm64 extension module refuses
    to load. The self-test never saw it because the self-test is run from
    Terminal, which starts natively. So check the thing itself: load a
    compiled module and report the machine type.
    """
    import platform
    machine = platform.machine()
    translated = ""
    if sys.platform == "darwin":
        try:
            out = subprocess.run(["sysctl", "-n", "sysctl.proc_translated"],
                                 capture_output=True, timeout=10)
            if out.stdout.strip() == b"1":
                translated = " RUNNING UNDER ROSETTA"
        except Exception:
            pass
    # Loading a compiled extension is the actual test; an arch mismatch
    # raises ImportError right here.
    from PIL import _imaging
    assert _imaging is not None
    assert not translated, (
        "this Python is running as Intel under Rosetta; the packages are "
        "native, so the app cannot load them")
    return "%s, compiled modules load%s" % (machine, translated)


def c_drag_drop():
    """Is drag-and-drop actually available?

    Tk has none of its own; it needs the tkdnd extension via tkinterdnd2.
    The app is fully usable without it, but it should not advertise a
    feature that does nothing — so this says plainly which it is.
    """
    from tkinterdnd2 import TkinterDnD
    assert TkinterDnD is not None
    return "tkinterdnd2 present — files can be dropped on the window"


def c_menubar():
    """Can the menu-bar icon be created?

    Only reports; the app runs without it. The first attempt at a status
    icon used pystray, whose macOS backend drives AppKit from its own
    thread and aborted the process — so this one is worth checking.
    """
    from app import menubar
    if not menubar.available():
        raise AssertionError(menubar.last_error() or "unavailable")
    return "AppKit present — icon can be created on the main thread"


def c_offline():
    """Offline translation: installed, and which languages are ready.

    Never fatal. The app works without it — this only says whether
    translation can happen without the network, an account or a bill.
    """
    from app import local_engine
    if not local_engine.available():
        raise AssertionError(local_engine.unavailable_reason())
    pairs = local_engine.installed_pairs()
    if not pairs:
        raise AssertionError(
            "engine installed, no languages downloaded yet "
            "(Settings > Offline translation)")
    return "%d language(s) ready: %s" % (
        len(pairs), ", ".join("%s->%s" % p for p in pairs))


def c_https():
    """Separate the network from the translation service.

    A failure here and a failure in Translation look the same from the app's
    point of view, but the fixes are completely different: one is a missing CA
    bundle on this machine, the other is a service refusing requests. Checking
    them apart names the right one.
    """
    import urllib.request
    from app import translator
    context = translator.ssl_context()
    urllib.request.urlopen("https://www.google.com/generate_204",
                           timeout=10, context=context)
    try:
        import certifi
        return "verified via certifi (%s)" % os.path.basename(certifi.where())
    except Exception:
        return "verified via the system CA store"


def c_translate():
    """Check the *content*, not just that bytes came back.

    The previous version asserted only that the result was non-empty, and so
    reported a cheerful ok for 'Error 500 (Server Error)!!1500.That's an' —
    Google's error page, delivered as a 200. A self-test that can be fooled by
    the failure it exists to catch is worse than no self-test.
    """
    from app import translator
    out = translator.translate("Guten Morgen", target="en").strip()
    assert out, "empty result"
    assert not translator._is_broken(out, "Guten Morgen"), \
        "service returned an error page, not a translation: %r" % out[:60]
    assert out.lower() != "guten morgen", "text came back untranslated"
    # It really should say this. Anything else means something is off even
    # though a plausible-looking string arrived.
    if "morning" not in out.lower():
        raise AssertionError("unexpected translation: %r" % out[:60])
    return "'Guten Morgen' -> '%s'  (via %s)" % (out[:30],
                                                 translator.active_backend())


def c_ai_translation():
    """Report whether the context-aware engine is configured."""
    from app import config, translator
    if not str(config.CONFIG.get("gemini_api_key", "") or "").strip():
        raise AssertionError(
            "no Gemini key set — Settings > Translation quality "
            "(free at aistudio.google.com)")
    out = translator._gemini("Guten Morgen", "auto", "en").strip()
    assert "morning" in out.lower(), "unexpected reply: %r" % out[:50]
    model = config.CONFIG.get("gemini_model") or "?"
    return "%s -> %r" % (model, out[:36])


def c_backends():
    """Report every translation service separately.

    'Translation' only says whether *something* worked. When it fails there is
    no way to tell a blocked network from a rate-limited service without
    trying each one, so try each one.
    """
    from app import translator
    verdicts = []
    for name, backend in translator.BACKENDS:
        try:
            out = backend("Guten Morgen", "auto", "en")
        except Exception as exc:
            verdicts.append("%s: %s" % (name, translator._describe(exc)))
            continue
        if translator._is_broken(out, "Guten Morgen"):
            verdicts.append("%s: error page" % name)
        elif "morning" in str(out).lower():
            verdicts.append("%s: OK" % name)
        else:
            verdicts.append("%s: odd (%r)" % (name, str(out)[:20]))
    working = [v for v in verdicts if v.endswith("OK")]
    assert working, "no backend works: " + "; ".join(verdicts)
    return "%d of %d work — %s" % (len(working), len(verdicts),
                                   "; ".join(verdicts))


def c_app_bundle():
    candidates = [os.path.expanduser("~/Applications/Squint.app"),
                  "/Applications/Squint.app",
                  os.path.join(ROOT, "Squint.app")]
    found = [p for p in candidates if os.path.isdir(p)]
    if not found:
        raise AssertionError("no app bundle built yet")
    app = found[0]
    notes = []
    icon = os.path.join(app, "Contents", "Resources", "icon.icns")
    notes.append("icon: %s" % ("yes" if os.path.isfile(icon) else "MISSING"))
    launcher = os.path.join(app, "Contents", "MacOS", "Squint")
    if os.path.isfile(launcher):
        with open(launcher, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("ROOT="):
                    target = line.strip().split("=", 1)[1].strip('"')
                    notes.append("points at: %s%s" % (
                        target, "" if os.path.isdir(target) else "  (MISSING!)"))
                    break
    try:
        verify = subprocess.run(["codesign", "--verify", "--strict", app],
                                capture_output=True, timeout=60)
        notes.append("signature: %s" % ("valid" if verify.returncode == 0
                                        else "none/invalid"))
    except Exception:
        pass
    return "%s  (%s)" % (app, "; ".join(notes))


def main():
    print("Squint self-test")
    print("=" * 62)
    check("Python", c_python, fatal=True)
    check("Architecture", c_architecture, fatal=True)
    check("Tk toolkit", c_tk, fatal=True)
    check("Main window", c_window, fatal=True)
    check("Foreground app", c_foreground)
    check("Window displays", c_window_visible, fatal=True)
    check("Screen capture", c_screenshot, fatal=True)
    check("OCR", c_ocr, fatal=True)
    check("OCR (Chinese)", c_ocr_cjk, fatal=True)
    check("OCR (Russian)", c_ocr_cyrillic, fatal=True)
    if sys.platform == "win32":
        check("Windows OCR", c_windows_ocr)
    check("Hotkey backend", c_hotkey_backend)
    check("Hotkey registration", c_hotkey_live, fatal=True)
    check("Drag and drop", c_drag_drop)
    check("Menu bar icon", c_menubar)
    check("Offline engine", c_offline)
    check("HTTPS / certificates", c_https, fatal=True)
    check("Translation", c_translate, fatal=True)
    check("AI translation", c_ai_translation)
    check("Services", c_backends)
    if sys.platform == "darwin":
        check("App bundle", c_app_bundle)

    print()
    for status, name, detail in results:
        print("[%s] %-22s %s" % (status, name, detail))
    print()

    failures = [r for r in results if r[0] == FAIL]
    if failures:
        print("PROBLEM: %s" % failures[0][1])
        print("  %s" % failures[0][2])
        print()
        print("Send this report back and it can be fixed directly.")
        return 1
    warnings = [r for r in results if r[0] == WARN]
    if warnings:
        print("Everything essential works. Non-fatal: %s"
              % ", ".join(w[1] for w in warnings))
        return 0
    print("Everything works.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
