"""Translate a PDF by reading its text, rather than photographing it.

A PDF that some system generated — a bill, a statement, a contract — already
contains its words, with the exact box, size and colour of every one of
them. Rendering that page to a picture and running a recogniser over it
throws all of that away and guesses at a worse copy: "E.ON Energie
Deutschland GmbH · Postfach" comes back as "EON Enroe DeutscHand GiH -
PastSuch", and the translation engine then does a perfectly good job of
translating nonsense. No amount of care in the layout afterwards recovers
a word that was destroyed before anything was translated.

So when the text is there, it is read. The output is a real PDF whose text
can be selected, searched and copied, not a photograph of one.

The recogniser is still right for a scanned page or a photo, where there
genuinely is nothing to read — `has_text` decides, and file_translate falls
back. The worst case for any document is therefore what the app did before.
"""
import re

# A page carrying less than this is not worth reading — a scan with a
# stray page number on it, or a cover sheet that is entirely picture.
MIN_CHARS = 40

# Extracted text that is mostly not letters is the signature of a PDF whose
# character map is broken: the glyphs on screen are fine and what comes out
# of the file is mojibake. Rendering and recognising that page is genuinely
# the better answer, so it has to be detected rather than trusted.
MIN_LETTER_SHARE = 0.55

# Below this the text has stopped being readable and the box should simply
# overflow instead. Same reasoning as the overlay's own floor.
MIN_SIZE = 5.0

_WORD = re.compile(r"[^\W\d_]", re.UNICODE)


def looks_like_language(text):
    """Is this extracted text, or is it a broken character map?"""
    stripped = "".join(str(text or "").split())
    if len(stripped) < 8:
        return False
    letters = sum(1 for ch in stripped if _WORD.match(ch))
    return letters / float(len(stripped)) >= MIN_LETTER_SHARE


def has_text(page):
    """Is there text on this page worth reading instead of recognising?"""
    try:
        text = page.get_text().strip()
    except Exception:
        return False
    return len(text) >= MIN_CHARS and looks_like_language(text)


def _colour(value):
    """PyMuPDF gives one packed integer; insert_textbox wants three floats."""
    try:
        value = int(value)
    except Exception:
        return (0.0, 0.0, 0.0)
    return (((value >> 16) & 255) / 255.0,
            ((value >> 8) & 255) / 255.0,
            (value & 255) / 255.0)


def lines_on(page):
    """Every line of text, with the box and style it was drawn in.

    One entry per line rather than per span, because a line is the unit
    that has a position on the page. Spans inside a line are runs of one
    style — a bold word inside a sentence — and are merged, taking the
    style of the longest of them. Keeping them separate would mean
    translating half a sentence at a time.
    """
    out = []
    try:
        blocks = page.get_text("dict")["blocks"]
    except Exception:
        return out
    for block in blocks:
        if block.get("type") != 0:
            continue                    # an image, not words
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", [])
                     if str(s.get("text", "")).strip()]
            if not spans:
                continue
            text = "".join(s["text"] for s in spans)
            if not text.strip():
                continue
            # Sideways text is left alone. The vertical print run down the
            # margin of a bill is a reference code, not prose, and the
            # typesetter writes left to right — replacing it in place turns
            # a neat rotated strip into a pile of overlapping fragments,
            # which is a worse outcome than leaving it in the original
            # language where it was perfectly readable.
            direction = line.get("dir", (1.0, 0.0))
            if abs(float(direction[0]) - 1.0) > 0.01 \
                    or abs(float(direction[1])) > 0.01:
                continue
            lead = max(spans, key=lambda s: len(s.get("text", "")))
            x0, y0, x1, y1 = line["bbox"]
            out.append({
                "text": text,
                "rect": (x0, y0, x1, y1),
                "box": (x0, y0, max(1.0, x1 - x0), max(1.0, y1 - y0)),
                "size": float(lead.get("size", 10.0)) or 10.0,
                "colour": _colour(lead.get("color", 0)),
                "bold": bool(int(lead.get("flags", 0)) & 16),
                "block": block.get("number", 0),
            })
    return out


def _within_blocks(lines, group_fn):
    """Group inside each of the document's own blocks, never across them.

    The grouping rules came from the screen overlay, where all there is to
    go on is where the recogniser found each line — so lines that look
    adjacent get merged, and sometimes that is wrong. A PDF does not need
    guessing at: it says where one block of text ends and the next begins,
    and that boundary is the author's, not an inference. Ignoring it merged
    a red heading into the end of the paragraph above it and ran a column
    of labels into the column of values beside them.
    """
    order = {}
    for index, line in enumerate(lines):
        order.setdefault(line.get("block", 0), []).append(index)
    out = []
    for indexes in order.values():
        subset = [lines[i] for i in indexes]
        for group in group_fn(subset):
            out.append([indexes[i] for i in group])
    return out


def paragraphs(lines, group_fn):
    """Lines gathered into the units that get translated together.

    A paragraph is translated as one piece and typeset back into the space
    all of its lines occupied, which is what lets the translation rewrap
    instead of being forced to break where the original happened to. A
    label beside its value is not a paragraph and must not be merged with
    the next row, or a table turns into a sentence — that judgement is the
    same one the screen overlay makes, so it is the same code.
    """
    units = []
    for group in _within_blocks(lines, group_fn):
        members = [lines[i] for i in group]
        if not members:
            continue
        x0 = min(m["rect"][0] for m in members)
        y0 = min(m["rect"][1] for m in members)
        x1 = max(m["rect"][2] for m in members)
        y1 = max(m["rect"][3] for m in members)
        text = " ".join(m["text"].strip() for m in members if m["text"].strip())
        lead = max(members, key=lambda m: len(m["text"]))
        units.append({
            "text": re.sub(r"\s+", " ", text).strip(),
            "rect": (x0, y0, x1, y1),
            "size": lead["size"],
            "colour": lead["colour"],
            "bold": lead["bold"],
            "lines": len(members),
        })
    return units


def font_for(target_lang, bold=False):
    """(name, file) for a font that certainly has the glyphs.

    Deliberately not the document's own face. An embedded font is usually
    subsetted to the glyphs the document actually used, so a translation
    reaching for a letter the original never contained gets a blank. A
    slightly wrong typeface that renders every word beats the right one
    with holes in it.

    A real font file first, and the built-ins only as a fallback, because
    the base-14 fonts are Latin-1 and Latin-1 has no euro sign. On a bill.
    Every amount came out as "9,92 ?", which on a document about money is
    not a cosmetic problem.
    """
    from . import overlay
    kind = overlay._font_family_for(target_lang)
    path = overlay._find_font_file(kind)
    if path:
        return ("squint-%s%s" % (kind, "-b" if bold else ""), path)
    # No file on this machine that can draw the script. The built-in CJK
    # fonts are the right answer then and are always present, so a machine
    # with no Chinese font installed still produces Chinese rather than a
    # page of empty boxes.
    builtin = {"chinese": "china-s", "japanese": "japan", "korean": "korea",
               "cjk": "china-s"}.get(kind)
    if builtin:
        return (builtin, None)
    return ("hebo" if bold else "helv", None)


def place(page, unit, text, target_lang="en", grow=1.0):
    """Typeset one translation where its original was. True if it landed.

    The translation is longer than the original more often than not, so
    the size comes down until it fits — never below the floor, past which
    the box is allowed to overflow rather than the words being made
    unreadable. This is the same trade the screen overlay makes, and it is
    easier here: the metrics are exact rather than recognised, and the
    typesetter reports whether the text fitted instead of being asked to
    guess.
    """
    import pymupdf
    x0, y0, x1, y1 = unit["rect"]
    # A little room below and to the right. Text set at the same nominal
    # size as the original needs marginally more space than the original
    # occupied, and a box measured to the pixel rejects it.
    rect = pymupdf.Rect(x0 - 1, y0 - 1, x1 + 2, y1 + 2 + (grow - 1.0) * 40)
    font, path = font_for(target_lang, unit.get("bold"))
    size = float(unit.get("size", 10.0))
    while size >= MIN_SIZE:
        try:
            left = page.insert_textbox(
                rect, text, fontsize=size, fontname=font, fontfile=path,
                color=unit.get("colour", (0, 0, 0)), align=0)
        except Exception:
            return False
        if left >= 0:
            return True
        size -= 0.5
    # It did not fit at any legible size. Draw it at the floor and let it
    # run past the box: the alternative is a document with words missing
    # and nothing on the page to say which.
    try:
        page.insert_textbox(
            pymupdf.Rect(rect.x0, rect.y0, rect.x1, page.rect.y1),
            text, fontsize=MIN_SIZE, fontname=font, fontfile=path,
            color=unit.get("colour", (0, 0, 0)), align=0)
        return True
    except Exception:
        return False


def erase(page, units):
    """Remove the original words, leaving everything else on the page.

    Redaction is the only thing that truly takes text out of a PDF rather
    than covering it — text merely painted over is still selectable, still
    searchable, and still there for anyone who copies the page. Images and
    vector graphics are kept explicitly, because the logo and the shaded
    panels are not what is being replaced.
    """
    import pymupdf
    for unit in units:
        x0, y0, x1, y1 = unit["rect"]
        try:
            page.add_redact_annot(pymupdf.Rect(x0 - 1, y0 - 1, x1 + 1, y1 + 1))
        except Exception:
            pass
    try:
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    except TypeError:
        # Older builds take neither keyword; the defaults keep images.
        try:
            page.apply_redactions()
        except Exception:
            pass
    except Exception:
        pass
