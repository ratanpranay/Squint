"""Where the seconds actually go when Squint reads the screen.

"Reading text…" sitting there for seconds is one symptom with about six
possible causes, and they are not distinguishable from the outside: a
missing winsdk sends every snip to the cloud, an extra language pack adds
a pass, a doubtful reading adds a network round-trip, and a cold Gemini key
adds a model-discovery walk before the first request. Guessing between
those and cutting a release for the guess is the expensive way to find out.

So this times each stage separately against the copy of Squint already
installed. It changes nothing, sends nothing anywhere that the app would
not have sent anyway, and needs no new build:

    put this file in the Squint folder as tools\\time_read.py
    double-click time-read.bat

Open the page you want to test first — it grabs the screen as it finds it.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WIDTH, HEIGHT = 965, 862          # about the size of the slow selection


def stamp(label, seconds, extra=""):
    print("  %-42s %7.2fs %s" % (label, seconds, extra))


def grab():
    """The middle of the primary screen, at about one selection's size."""
    import mss
    from PIL import Image
    opener = getattr(mss, "MSS", None) or mss.mss
    with opener() as sct:
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)
        full = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    w = min(WIDTH, full.width)
    h = min(HEIGHT, full.height)
    left = max(0, (full.width - w) // 2)
    top = max(0, (full.height - h) // 2)
    return full.crop((left, top, left + w, top + h))


def setting_lines():
    from app import config, ocr, profile
    del config
    out = []
    try:
        out.append("engine setting      : %s" % profile.current())
    except Exception as exc:
        out.append("engine setting      : ? (%s)" % exc)
    for name, call in (("reader chosen", ocr.ocr_choice),
                       ("reader that answers", ocr.engine_name),
                       ("local reader", ocr.local_engine_name)):
        try:
            out.append("%-20s: %s" % (name, call()))
        except Exception as exc:
            out.append("%-20s: ? (%s)" % (name, exc))
    try:
        readers = [r.__name__.rsplit(".", 1)[-1] for r in ocr.cloud_readers()]
        out.append("%-20s: %s" % ("cloud fallbacks",
                                  ", ".join(readers) or "none"))
    except Exception as exc:
        out.append("cloud fallbacks     : ? (%s)" % exc)
    return out


def windows_detail(image):
    """One line per installed pack, timed. This is the whole Windows path."""
    from app import ocr_windows as w
    print("winsdk available    : %s" % w.AVAILABLE)
    if not w.AVAILABLE:
        print("  -> every snip goes to the cloud, which is the slow path.")
        print("  -> %s" % w.unavailable_reason())
        return None

    start = time.time()
    installed = w.available_languages()
    stamp("listing installed packs", time.time() - start,
          ", ".join(installed) or "nothing")

    start = time.time()
    tags = w._candidate_tags(None)
    stamp("choosing which to try", time.time() - start, ", ".join(tags))

    start = time.time()
    bitmap = w._software_bitmap(image)
    stamp("converting the image", time.time() - start)

    readings = []
    for tag in tags:
        start = time.time()
        try:
            engine = w.OcrEngine.try_create_from_language(w.Language(tag))
            if engine is None:
                stamp("read as %s" % tag, time.time() - start, "no engine")
                continue
            result = w._run(engine.recognize_async(bitmap))
        except Exception as exc:
            stamp("read as %s" % tag, time.time() - start, "failed: %s" % exc)
            continue
        lines = w._lines_from(result)
        text = " ".join(line["text"] for line in lines)
        readings.append((tag, lines, text))
        stamp("read as %s" % tag, time.time() - start,
              "%d lines | %r" % (len(lines), text[:40]))

    # Why one reading beats another, in the numbers the chooser uses.
    print()
    print("  %-14s %7s %7s %7s %7s  %s"
          % ("reading", "chars", "script", "share", "score", "own script?"))
    for tag, _lines, text in readings:
        dense = "".join(text.split())
        try:
            share = w.script_share(text)
            real = w.has_real_script(text)
        except AttributeError:                 # a build before the fix
            share = (w.script_chars(text) / float(len(dense))
                     if dense else 0.0)
            real = w.script_chars(text) >= 2
        print("  %-14s %7d %7d %6.1f%% %7.0f  %s"
              % (tag, len(dense), w.script_chars(text), share * 100.0,
                 w.reading_score(text), "yes" if real else "no"))
    print()

    chosen = w.choose_reading(readings)
    if chosen is None:
        print("  nothing readable in any of them")
        return None
    tag, _lines, text = chosen
    print("  kept                : %s" % tag)
    misread = w.might_be_misread(text)
    print("  looks misread       : %s%s" % (
        misread, "  -> a cloud reader is asked as well" if misread else ""))
    return text


def cloud_detail(image):
    from app import ocr
    for reader in ocr.cloud_readers():
        name = reader.__name__.rsplit(".", 1)[-1]
        start = time.time()
        try:
            lines, used = reader.image_to_lines(image)
            stamp("%s" % name, time.time() - start,
                  "%d lines (%s)" % (len(lines), used))
        except Exception as exc:
            stamp("%s" % name, time.time() - start, "failed: %s" % exc)


def countdown(seconds=8):
    """Give the user time to put the page they mean in front.

    This reads the middle of the screen, and the middle of the screen is
    wherever the window they just launched this from happens to be. Two
    runs on two machines came back describing a file manager, which is a
    perfectly accurate answer to the wrong question - and English read as
    English comes back identical, so every line said "unchanged" and
    looked exactly like the failure being investigated.
    """
    print("Bring the page you want to test to the front now.")
    for left in range(seconds, 0, -1):
        sys.stdout.write("\r  grabbing the screen in %d... " % left)
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\r" + " " * 40 + "\r")
    sys.stdout.flush()


def main():
    print("Squint - where the reading time goes")
    print("=" * 62)
    for line in setting_lines():
        print(line)
    print()

    countdown()
    start = time.time()
    image = grab()
    stamp("screen grab", time.time() - start, "%dx%d" % image.size)
    try:
        image.save(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "time-read-grabbed.png"))
        print("  saved what it grabbed as time-read-grabbed.png - check it "
              "is the page you meant")
    except Exception:
        pass
    print()

    from app import platform_util
    if platform_util.IS_WINDOWS:
        print("-- this PC's own reader " + "-" * 38)
        windows_detail(image)
        print()

    print("-- cloud readers, one at a time " + "-" * 30)
    print("   (each of these is a network round-trip; the app only reaches")
    print("    them when the reading above looks wrong)")
    cloud_detail(image)
    print()

    print("-- the whole thing, as the app does it " + "-" * 23)
    from app import ocr
    start = time.time()
    lines = []
    try:
        lines, used = ocr.image_to_lines(image)
        stamp("ocr.image_to_lines", time.time() - start,
              "%d lines (%s)" % (len(lines), used))
    except Exception as exc:
        stamp("ocr.image_to_lines", time.time() - start, "failed: %s" % exc)
    note = ocr.reading_note()
    if note:
        print("  note: %s" % note)
    print()
    overlay_detail(lines)


def overlay_detail(lines):
    """What the snip path does to each line after it has been read.

    The card and the overlay disagree on the same page, over and over: the
    card comes back in English and the overlay comes back mostly in the
    original. They are two different code paths and the difference has to
    be visible per line, not per snip, because the interesting failures
    are partial — some lines translated, some not, and one drawn in the
    wrong box.
    """
    print("-- what the overlay does with those lines " + "-" * 20)
    if not lines:
        print("  nothing was read, so there is nothing to translate")
        return
    from app import config, overlay, translator
    target = str(config.CONFIG.get("target_lang", "en") or "en")
    held = overlay.stamped_addresses(lines)
    if held:
        print("  treated as a watermark: %s" % ", ".join(sorted(held)))

    start = time.time()
    try:
        texts = overlay.translate_grouped(lines, translator, target)
    except Exception as exc:
        stamp("overlay.translate_grouped", time.time() - start,
              "failed: %s" % exc)
        return
    stamp("overlay.translate_grouped", time.time() - start,
          "target=%s" % target)
    print()

    same = skipped = blank = 0
    for line, text in zip(lines, texts):
        source = str(line.get("text", "")).strip()
        out = str(text or "").strip()
        if overlay.carries_an_address(source, ignore=held):
            flag, skipped = "HELD  ", skipped + 1
        elif not out:
            flag, blank = "BLANK ", blank + 1
        elif out == source:
            flag, same = "SAME  ", same + 1
        else:
            flag = "ok    "
        print("  %s %-42s -> %s" % (flag, source[:42], out[:42]))
    print()
    print("  %d lines: %d held back, %d came back empty, %d came back "
          "unchanged" % (len(lines), skipped, blank, same))
    if same:
        print("  UNCHANGED is the one that matters: the overlay draws the")
        print("  original back over itself, so the snip looks like it")
        print("  worked and did nothing.")


class Tee:
    """Everything printed also lands in a file, because a console window
    that has to be selected and copied out of is a step too many."""

    def __init__(self, path):
        self.terminal = sys.stdout
        self.handle = open(path, "w", encoding="utf-8")

    def write(self, text):
        self.terminal.write(text)
        self.handle.write(text)

    def flush(self):
        self.terminal.flush()
        self.handle.flush()


if __name__ == "__main__":
    report = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "time-read.txt")
    tee = None
    try:
        tee = Tee(report)
        sys.stdout = tee
    except Exception:
        pass
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
    finally:
        if tee is not None:
            sys.stdout = tee.terminal
            try:
                tee.handle.close()
            except Exception:
                pass
    print()
    print("Written to: %s" % report)
    print("Open that file and paste it back.")
    print()
    input("Press Enter to close.")
