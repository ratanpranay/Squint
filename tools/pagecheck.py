"""Score a translated page against the layout it replaced.

Four releases of layout work were judged by looking at a screenshot and
saying whether it seemed better. That is how three faults in a row shipped:
a screenshot shows the page you happen to have, and it shows it to a person
who already knows what the fix was supposed to do.

This turns the same question into numbers, over a corpus rather than one
page. It runs the real reading and layout code — whatever recogniser this
machine has — and reports the things that were actually wrong on real
documents:

  cells      a table row read as one box instead of its cells. The root
             cause of a bill coming back as scattered words: if the row is
             one box, every column position is gone before layout starts.
  merged     cells of a table gathered into a "paragraph" and drawn as one
             block. A column of amounts is not a sentence.
  lost       words the translator returned that are not on the page.
  showing    lines that were translated and are still visible underneath.
  kept       identifiers — meter numbers, dates, prices, addresses — that
             came through unchanged.
  overlap    pairs of blocks drawn on top of each other. Text over text
             is unreadable however well placed each half of it is, and it
             is the one fault a person notices before any other.
  offpage    blocks reaching past the edge of the capture. Words there are
             not merely misplaced, they are gone.
  sizes      the ratio between the largest and smallest text drawn. A page
             of body text with one heading is about 2; a page where a box
             was misread is 5 or more.

Nothing here needs the network: the translator is a stand-in that marks
every word so it can be traced from the engine to the page. What is being
measured is where words end up, not how well they were translated.

usage:
    python tools/pagecheck.py <page.png> [more.png ...]
    python tools/pagecheck.py --width 900 <page.png>
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PIL import Image                                        # noqa: E402

from app import ocr, overlay, selection                      # noqa: E402


def words_in(text):
    """Roughly how many words a translation of this will run to.

    `len(text.split())` was standing in for this, and on the pages that
    matter it is not an approximation but a different number entirely.
    Chinese and Japanese are written without spaces, so a forty-character
    paragraph splits into *one* word — the stand-in then returned one
    token, the layout had a whole paragraph's worth of room for it, and the
    harness reported a page with no crowding on it at all. The same page,
    translated for real, produced thirty English words in that space and
    was drawn over its neighbours.

    So the harness measured the one case that never happens. A character of
    Chinese carries about two thirds of an English word; Korean and every
    spaced script carry about one word per word, and English out of them
    runs a little longer than in.
    """
    text = str(text or "")
    dense = sum(1 for ch in text if selection.unspaced(ch))
    spaced = len([w for w in text.split()
                  if any(not selection.unspaced(ch) for ch in w)])
    return max(1, int(round(dense / 1.5 + spaced * 1.2)))


class Marked:
    """A translator whose every word can be traced back to its paragraph."""

    SPEED = "speed"

    def __init__(self, grow=1.0):
        self.blocks = []
        self.grow = float(grow or 1.0)

    def count(self, block):
        return max(1, int(round(words_in(block) * self.grow)))

    def translate_lines(self, blocks, target=None, job=None):
        self.blocks = list(blocks)
        out = []
        for number, block in enumerate(blocks):
            count = self.count(block)
            out.append(" ".join("p%dw%d" % (number, i) for i in range(count)))
        return out


# What a person would be upset to see altered: a meter number, an amount, a
# date, an address. Deliberately narrow — this counts what survived, it does
# not decide anything.
_IDENT = re.compile(r"""
    (?:[\w.+-]+@[\w-]+\.[\w.-]+)                 # an email address
  | (?:\b\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?\b)    # 1.284,00
  | (?:\b\d{2}[./]\d{2}[./]\d{2,4}\b)            # 01.01.26
  | (?:\b[A-Z]{2}\d{2}[\s\d]{10,}\b)             # an IBAN
  | (?:\b[A-Z0-9]{8,}\b)                         # a meter or contract number
""", re.VERBOSE)


def identifiers(text):
    return set(_IDENT.findall(str(text or "")))


def words_on(blocks):
    out = []
    for block in blocks:
        for row in block["rows"]:
            out.extend(row.split())
    return out


def inside(box, cover):
    x, y, w, h = box
    left, top, right, bottom = cover
    return (x >= left - 1 and y >= top - 1
            and x + w <= right + 1 and y + h <= bottom + 1)


def drawn_box(block):
    """Where a block's text actually lands, which is not its cover.

    The cover is painted over the original and may be larger; what a
    reader sees written is the rows, at the size they were set, from the
    top the block was placed at.
    """
    rows = block.get("rows") or []
    leading = int(block.get("leading") or block.get("size", 10))
    height = max(1, len(rows) * leading)
    width = max(1, block["cover"][2] - block["cover"][0])
    return (block["x"], block["y"], width, height)


def overlapping(blocks, slack=2):
    """Pairs of blocks whose drawn text lands on top of other drawn text."""
    boxes = [drawn_box(b) for b in blocks]
    hits = 0
    for i in range(len(boxes)):
        ax, ay, aw, ah = boxes[i]
        for j in range(i + 1, len(boxes)):
            bx, by, bw, bh = boxes[j]
            across = min(ax + aw, bx + bw) - max(ax, bx)
            down = min(ay + ah, by + bh) - max(ay, by)
            if across > slack and down > slack:
                hits += 1
    return hits


def off_page(blocks, width, height, slack=2):
    """Blocks whose text reaches past the edge of the capture."""
    out = 0
    for block in blocks:
        x, y, w, h = drawn_box(block)
        if x < -slack or y < -slack or x + w > width + slack:
            out += 1
    return out


def row_bands(lines, tolerance=0.5):
    """Group lines that share a horizontal band — one row of a table.

    Two lines are in the same row when they overlap vertically by more than
    half the shorter of them. A row holding several lines is a row of cells;
    a row holding one is a line of prose.
    """
    order = sorted(range(len(lines)), key=lambda i: lines[i]["box"][1])
    rows, current = [], []
    for index in order:
        _x, y, _w, h = lines[index]["box"]
        if not current:
            current = [index]
            continue
        top = min(lines[i]["box"][1] for i in current)
        bottom = max(lines[i]["box"][1] + lines[i]["box"][3] for i in current)
        overlap = min(y + h, bottom) - max(y, top)
        if overlap > tolerance * min(h, bottom - top):
            current.append(index)
        else:
            rows.append(current)
            current = [index]
    if current:
        rows.append(current)
    return rows


def unsplit_rows(lines, page_width, share=0.55, gap_factor=2.5):
    """Lines that are one box but hold several cells.

    A line wider than half the page whose words are separated by at least
    one gap far larger than the rest is a table row that was never split.
    Counted from the line's own text, so it needs no ground truth.
    """
    found = []
    for line in lines:
        x, _y, w, h = line["box"]
        if w < page_width * share:
            continue
        text = str(line.get("text", ""))
        if len(text.split()) < 3:
            continue
        # A row of cells has runs of two or more spaces, or — after a
        # recogniser has normalised them away — a width per character far
        # above what the text needs.
        density = w / max(1, len(text))
        if density > h * 0.75:
            found.append(line)
    return found


def check(path, width=900, target="en", grow=1.0):
    image = Image.open(path).convert("RGB")
    if width and image.width != width:
        image = image.resize(
            (width, int(image.height * width / image.width)), Image.LANCZOS)

    lines, _lang = ocr.image_to_lines(image)
    if not lines:
        return {"page": os.path.basename(path), "read": 0}

    source_ids = set()
    for line in lines:
        source_ids |= identifiers(line.get("text"))

    engine = Marked(grow)
    texts = overlay.translate_grouped(lines, engine, target)
    blocks, _height = overlay.layout(image, lines, texts, target, min_size=7)

    drawn = words_on(blocks)
    lost = 0
    for number, block in enumerate(engine.blocks):
        expected = ["p%dw%d" % (number, i)
                    for i in range(engine.count(block))]
        if not any(w in drawn for w in expected):
            continue                       # the whole paragraph was held back
        lost += sum(1 for w in expected if w not in drawn)

    # Against the ink, not against the box the recogniser drew. A box is
    # routinely taller than the writing in it, and a cover that hides every
    # pixel of the writing has done its job even when it does not reach the
    # corners of a box that was never touching the text.
    showing = 0
    for line, text in zip(lines, texts):
        if not str(text).strip():
            continue
        bg, _fg = overlay.sample_colours(image, line["box"])
        tight = overlay.ink_box(image, line["box"], bg) or line["box"]
        if not any(inside(tight, b["cover"]) for b in blocks):
            showing += 1

    # An identifier survives when the line carrying it was held back, so it
    # is still on the page in its original form.
    held = overlay.held_back(lines)
    kept = set()
    for index in held:
        kept |= identifiers(lines[index].get("text"))

    rows = row_bands(lines)
    cells = sum(1 for row in rows if len(row) > 1)
    sizes = sorted(b["size"] for b in blocks)

    merged = 0
    for block in blocks:
        if int(block.get("lines", 1)) > 1:
            merged += 1
    over = overlapping(blocks)
    outside = off_page(blocks, image.width, _height or image.height)

    return {
        "page": os.path.basename(path),
        "read": len(lines),
        "unsplit": len(unsplit_rows(lines, image.width)),
        "rows_of_cells": cells,
        "paragraphs": len(engine.blocks),
        "blocks": len(blocks),
        "merged": merged,
        "lost": lost,
        "showing": showing,
        "ids": len(source_ids),
        "ids_kept": len(kept & source_ids),
        "overlap": over,
        "offpage": outside,
        "size_ratio": (sizes[-1] / sizes[0]) if sizes and sizes[0] else 0,
    }


HEAD = ("page          read unsplit  paras blocks  lost showing overlap "
        "offpage kept/ids  size")


def line_for(r):
    if not r.get("read"):
        return "%-13s   (nothing read)" % r["page"]
    return ("%-13s %4d %7d %6d %6d %5d %7d %7d %7d  %3d/%-3d %5.1f"
            % (r["page"], r["read"], r["unsplit"],
               r["paragraphs"], r["blocks"], r["lost"], r["showing"],
               r["overlap"], r["offpage"], r["ids_kept"], r["ids"],
               r["size_ratio"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pages", nargs="+")
    ap.add_argument("--width", type=int, default=900,
                    help="capture width in pixels (0 = leave alone)")
    ap.add_argument("--target", default="en")
    ap.add_argument("--grow", type=float, default=1.0,
                    help="how much longer the translation runs than the "
                         "estimate (1.3 models a wordy target language)")
    args = ap.parse_args()

    print(HEAD)
    totals = {"lost": 0, "showing": 0, "unsplit": 0, "ids": 0, "ids_kept": 0,
              "overlap": 0, "offpage": 0}
    for path in args.pages:
        r = check(path, args.width, args.target, args.grow)
        print(line_for(r))
        for key in totals:
            totals[key] += r.get(key, 0)
    print("-" * len(HEAD))
    print("totals: %d words lost, %d lines showing, %d overlapping pairs, "
          "%d off the page, %d rows unsplit, %d/%d identifiers kept"
          % (totals["lost"], totals["showing"], totals["overlap"],
             totals["offpage"], totals["unsplit"],
             totals["ids_kept"], totals["ids"]))


if __name__ == "__main__":
    main()
