"""Run check: the whole snip, on this computer, on pages whose text is known.

Squint is built and tested on a machine that has neither Apple's reader,
nor Windows', nor this computer's graphics chip. What a snip does here -
read, translate, lay out - was only ever checked by using it, and what went
wrong showed up as a page left half in German or a snip that took eight
seconds. This puts three pages through the same path a snip takes, with
this computer's reader and engines, and checks what came back:

  read        every line of the page was read (a line counts when the
              reader's text is at least 80% the same);
  translated  every paragraph came back in the language translated into,
              none left as it was;
  laid out    every translated line has its translation drawn over it;
  time        reading and translating took no more than the three seconds
              a snip may take (app/budget.py).

And the parts of the app those depend on: which reader and engine are in
use, whether the offline model is ready, whether the shortcut can tell a
tap from a hold, whether selected text can be copied.

The pages are drawn here, in the system's own typeface, at the size text
is on this screen. The result is written to selfcheck.txt beside the log,
and summed up on the screen.
"""
import difflib
import os
import sys
import time
import traceback

from PIL import Image, ImageDraw

from . import budget, config

IS_MAC = sys.platform == "darwin"

# Each page: a title and its lines; a blank line separates paragraphs.
PAGES_DE = (
    ("Listing", (
        "Beschreibung",
        "",
        "Ich verkaufe mein Rennrad in der Rahmengröße 56 cm mit vielen",
        "hochwertigen Komponenten und einem frischen Service.",
        "",
        "Komponenten:",
        "- Die hintere Bremse wurde durch eine neue ersetzt.",
        "- Als Kurbel ist eine leichte Carbonkurbel verbaut. Leider",
        "funktioniert der Leistungsmesser aktuell nicht. Der Neupreis",
        "lag bei etwa 2.500-3000€.",
        "- Neue Reifen",
        "",
        "Das Rad ist gerne gefahren worden....Alle Spuren zu zeigen",
        "wäre dann zu viel...",
        "",
        "Bei Interesse schreib mir gerne, ich antworte schnellstmöglich!",
    )),
    ("Article", (
        "Neue Regeln für Mieter ab dem nächsten Jahr",
        "",
        "Wer eine Wohnung mietet, muss sich ab Januar auf einige",
        "Änderungen einstellen. Die Nebenkosten werden künftig genauer",
        "abgerechnet, und Vermieter müssen den Verbrauch jedes Monats",
        "mitteilen. Für viele Haushalte bedeutet das mehr Klarheit.",
        "",
        "Verbraucherschützer begrüßen die Neuerung, warnen aber vor",
        "höheren Kosten für die Ablesung. Die Regelung gilt zunächst",
        "für drei Jahre und wird danach überprüft.",
    )),
    ("Labels", (
        "Startseite",
        "Konto",
        "Warenkorb",
        "Versand und Lieferung",
        "Hilfe und Kontakt",
        "Zahlungsarten",
    )),
)

PAGES_EN = (
    ("Listing", (
        "Description",
        "",
        "I am selling my road bike, frame size 56 cm, with many high-end",
        "components and a fresh service.",
        "",
        "Components:",
        "- The rear brake was replaced with a new one.",
        "- The crank is a light carbon crank. Unfortunately the power",
        "meter does not work at the moment. It cost about 2,500-3,000",
        "euros new.",
        "- New tyres",
        "",
        "The bike has been ridden a lot....Showing every mark would be",
        "too much...",
        "",
        "If you are interested, write to me and I will reply quickly!",
    )),
    ("Article", (
        "New rules for tenants from next year",
        "",
        "Anyone who rents a flat will have to get used to a few changes",
        "from January. Service charges will be billed more precisely,",
        "and landlords will have to report the consumption every month.",
        "For many households this means more clarity.",
        "",
        "Consumer groups welcome the change but warn of higher costs",
        "for meter reading. The rule applies for three years at first",
        "and will be reviewed after that.",
    )),
    ("Labels", (
        "Home",
        "Account",
        "Basket",
        "Shipping and delivery",
        "Help and contact",
        "Payment methods",
    )),
)

FOUND = 0.8            # how alike the reader's line must be to count as read


def _pages(target):
    """German pages, or English ones when translating into German."""
    if str(target or "").lower().startswith("de"):
        return PAGES_EN, "en"
    return PAGES_DE, "de"


def _scale():
    """Pixels to a point of text on this screen: Retina is two."""
    if IS_MAC:
        return 2.0
    try:
        from . import platform_util
        percent = platform_util.monitor_scaling(0, 0)
        if percent:
            return max(1.0, percent / 100.0)
    except Exception:
        pass
    return 1.0


def draw_page(lines, scale=1.0):
    """The page as a screen would show it: dark text on white, 16-point
    type, 1.5 line spacing."""
    from . import overlay
    size = int(round(16 * scale))
    font = overlay.load_font("default", size)
    pitch = int(round(size * 1.5))
    margin = int(round(24 * scale))
    width = int(round(720 * scale))
    height = margin * 2 + pitch * len(lines)
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    y = margin
    for line in lines:
        if line:
            draw.text((margin, y), line, font=font, fill=(28, 28, 30))
        y += pitch
    return image


def _best_match(wanted, read):
    best = 0.0
    for text in read:
        best = max(best, difflib.SequenceMatcher(
            None, wanted.lower(), text.lower()).ratio())
    return best


def check_page(title, lines, source, target, translator, log=print):
    """One page through the snip's path. Returns a dict of what was found."""
    from . import langid, ocr, overlay
    result = {"page": title, "problems": []}
    wanted = [l for l in lines if l.strip()]
    image = draw_page(lines, _scale())
    started = time.monotonic()
    read, used = ocr.image_to_lines(image, source=None)
    read_ms = 1000 * (time.monotonic() - started)
    result["reader"] = used
    texts = [l.get("text", "") for l in read]
    missed = [w for w in wanted if _best_match(w, texts) < FOUND]
    result["read"] = (len(wanted) - len(missed), len(wanted))
    for w in missed:
        result["problems"].append("not read: %s" % w)
    started = time.monotonic()
    floor = int(round(10 * _scale()))
    out, blocks, _tall = overlay.progressive(
        image, read, translator, target, "auto", floor)
    translate_ms = 1000 * (time.monotonic() - started)
    result["engine"] = config.CONFIG.get("last_backend", "") or "?"
    # A paragraph left in the language it was in.
    left = []
    seen = set()
    for line in read:
        para = line.get("para")
        if para in seen:
            continue
        seen.add(para)
        source_text = " ".join(l.get("text", "") for l in read
                               if l.get("para") == para).strip()
        answer = str(line.get("para_text") or "").strip()
        if not source_text or not any(c.isalpha() for c in source_text):
            continue
        if not answer or answer == source_text or \
                langid.in_language(answer, source) is True:
            left.append(source_text)
    for text in left:
        result["problems"].append("left untranslated: %s" % text[:70])
    covered = overlay.lines_covered(blocks)
    held = overlay.held_back(read)
    should = sum(1 for i, l in enumerate(read)
                 if l.get("text", "").strip() and i not in held)
    result["laid_out"] = (covered, should)
    if covered < should:
        result["problems"].append("%d of %d lines have no translation drawn"
                                  % (should - covered, should))
    total = read_ms + translate_ms
    result["ms"] = (int(read_ms), int(translate_ms), int(total))
    if total > budget.DONE_MS:
        result["problems"].append("took %.1f s (limit %.1f s)"
                                  % (total / 1000.0, budget.DONE_MS / 1000.0))
    return result


def environment(controller=None):
    """The parts a snip depends on, in plain words."""
    from . import ocr
    out = []
    try:
        out.append(("reader", "Apple Vision" if ocr.use_vision() else
                    "Windows" if ocr.use_windows_ocr() else "other"))
    except Exception:
        pass
    try:
        from . import offline_model, profile
        out.append(("offline model", "ready" if offline_model.ready()
                    else "not ready"))
        out.append(("engine choice", str(profile.current())))
    except Exception:
        pass
    target = config.CONFIG.get("target_lang", "en")
    out.append(("translating into", target))
    try:
        hotkeys = getattr(controller, "hotkeys", None)
        if IS_MAC and hotkeys is not None:
            out.append(("tap or hold", "told by the system"
                        if getattr(hotkeys, "reports_release", False)
                        else "guessed from the keys (not told)"))
    except Exception:
        pass
    try:
        from . import selection
        out.append(("copy selected text", "allowed" if selection.permitted()
                    else "NOT allowed (Accessibility)"))
    except Exception:
        pass
    out.append(("icon on selected text",
                "on" if config.CONFIG.get("select_icon", True) else "off"))
    return out


def run(controller=None, translator=None, log=print):
    """Every page, then the report. Returns (passed, summary, path)."""
    if translator is None:
        from . import translator as translator
    target = config.CONFIG.get("target_lang", "en")
    pages, source = _pages(target)
    lines_out = ["Squint %s - run check, %s" % (
        config.build_id(), time.strftime("%Y-%m-%d %H:%M"))]
    for name, value in environment(controller):
        lines_out.append("  %-22s %s" % (name, value))
    lines_out.append("")
    # The engine is started first and not timed: a snip right after the
    # app starts loads the model once, and that is not the snip's speed.
    try:
        translator.translate_lines(["Hallo" if source == "de" else "Hello"],
                                   target=target, source="auto")
    except Exception:
        pass
    results = []
    for title, lines in pages:
        try:
            result = check_page(title, lines, source, target, translator,
                                log)
        except Exception as exc:
            result = {"page": title, "problems": [
                "failed: %s" % exc], "ms": (0, 0, 0), "read": (0, 0),
                "laid_out": (0, 0), "engine": "?", "reader": "?"}
            log("check      : %s" % traceback.format_exc()[-400:])
        results.append(result)
        read_ms, tr_ms, total = result["ms"]
        lines_out.append(
            "%-8s %s  read %d/%d lines in %d ms, translated in %d ms via "
            "%s, total %.1f s, drawn %d/%d"
            % (result["page"], "PASS" if not result["problems"] else "FAIL",
               result["read"][0], result["read"][1], read_ms, tr_ms,
               result.get("engine", "?"), total / 1000.0,
               result["laid_out"][0], result["laid_out"][1]))
        for problem in result["problems"]:
            lines_out.append("         - %s" % problem)
    passed = all(not r["problems"] for r in results)
    lines_out.append("")
    lines_out.append("RESULT: %s" % ("PASS" if passed else "FAIL"))
    text = "\n".join(lines_out) + "\n"
    path = os.path.join(config.data_dir(), "selfcheck.txt")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    except Exception:
        path = ""
    for line in lines_out:
        log("check      : %s" % line)
    failed = [r for r in results if r["problems"]]
    if passed:
        summary = ("All %d test pages passed: read, translated and drawn "
                   "within %.0f seconds." % (len(results),
                                             budget.DONE_MS / 1000.0))
    else:
        summary = "%d of %d test pages failed:\n%s" % (
            len(failed), len(results),
            "\n".join("%s: %s" % (r["page"], "; ".join(r["problems"][:3]))
                      for r in failed))
    return passed, summary, path
