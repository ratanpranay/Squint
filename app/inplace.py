"""Where the selected text is on screen, so its translation can be drawn
over it - the way a snip is - instead of in a card beside it.

Translate-selection copies the text; it does not know where the text is.
The card it showed did not fit the text: a paragraph came back cut off at
three lines, a word in a box made for a paragraph. So the screen under the
pointer is read (this computer's reader only, the fast one), the lines
that make up the copied text are found among what was read, and the area
they cover is handed to the snip's own path - read, translated and laid out
exactly as if it had been snipped. Where the text cannot be found (in a
window not under the pointer, too little of it read), the card is shown as
before.
"""
import difflib
import re
import sys

IS_MAC = sys.platform == "darwin"

# How much of the copied text the lines found must account for.
MATCH_SHARE = 0.6
# The area first read around the pointer, in pixels of the screen: where
# text was just selected with the mouse. The page in front is read whole
# only if the text is not all in it.
NEAR_W, NEAR_H = 1800, 1100
PAD = 6


def _norm(text):
    return re.sub(r"[\W_]+", "", str(text or "").lower())


def _part_of(line, whole):
    """How much of `line` (normalised) is in `whole`: all of it, or the
    part at the start or end of a line the selection began or ended in."""
    if not line:
        return 0
    if line in whole:
        return len(line)
    match = difflib.SequenceMatcher(None, line, whole, autojunk=False) \
        .find_longest_match(0, len(line), 0, len(whole))
    return match.size if match.size >= max(4, 0.6 * len(line)) else 0


def find(lines, content):
    """The box (x0, y0, x1, y1) round the lines of `lines` that make up
    `content`, or None. The lines must be one block: one under another,
    overlapping sideways."""
    whole = _norm(content)
    if len(whole) < 2:
        return None
    hits = []
    for line in lines:
        text = _norm(line.get("text", ""))
        got = _part_of(text, whole) if len(text) >= 2 else 0
        if got and (got >= 3 or len(whole) <= 6):
            hits.append((line, got))
    if not hits:
        return None
    hits.sort(key=lambda h: (h[0]["box"][1], h[0]["box"][0]))
    # Runs of lines close under one another; the run that covers most of
    # the copied text is the selection.
    runs, run = [], [hits[0]]
    for hit in hits[1:]:
        x, y, w, h = hit[0]["box"]
        px, py, pw, ph = run[-1][0]["box"]
        near = y - (py + ph) <= 1.6 * max(h, ph)
        side = min(x + w, px + pw) - max(x, px) > -0.5 * max(h, ph)
        if near and side:
            run.append(hit)
        else:
            runs.append(run)
            run = [hit]
    runs.append(run)
    best = max(runs, key=lambda r: sum(g for _l, g in r))
    if sum(g for _l, g in best) < MATCH_SHARE * len(whole):
        return None
    x0 = min(l["box"][0] for l, _g in best)
    y0 = min(l["box"][1] for l, _g in best)
    x1 = max(l["box"][0] + l["box"][2] for l, _g in best)
    y1 = max(l["box"][1] + l["box"][3] for l, _g in best)
    return (x0 - PAD, y0 - PAD, x1 + PAD, y1 + PAD)


def grab():
    """The screen under the pointer, taken before anything of Squint's is
    on it - its own "Reading selection" card shows the copied text too, and
    would be found instead. (image, monitor, pointer), or None."""
    try:
        from PIL import Image
        import mss
        from . import preread
        where = preread.pointer()
        with mss.mss() as sct:
            monitors = list(sct.monitors[1:]) or [sct.monitors[0]]
            mon = monitors[0]
            if where:
                for m in monitors:
                    if (m["left"] <= where[0] < m["left"] + m["width"]
                            and m["top"] <= where[1]
                            < m["top"] + m["height"]):
                        mon = m
                        break
            raw = sct.grab(mon)
        image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        return image, dict(mon), where
    except Exception:
        return None


def locate(content, shot):
    """(crop, origin, scale) of the selected text in `shot` (see grab),
    ready to be handled as a snip - or None."""
    from . import ocr, preread
    if not shot:
        return None
    image, mon, where = shot
    scale = 1.0
    if IS_MAC and mon.get("width"):
        scale = max(1.0, round(image.width / float(mon["width"]), 2))
    areas = []
    if where:
        px = int((where[0] - mon["left"]) * scale)
        py = int((where[1] - mon["top"]) * scale)
        areas.append((max(0, px - NEAR_W // 2), max(0, py - NEAR_H // 2),
                      min(image.width, px + NEAR_W // 2),
                      min(image.height, py + NEAR_H // 2)))
    try:
        from . import content_area
        layers = content_area.layers(*where) if where else None
    except Exception:
        layers = None
    areas.append(preread.content_box(layers, mon, scale, image.size))
    seen = set()
    for area in areas:
        if area in seen or area[2] - area[0] < 20 or area[3] - area[1] < 10:
            continue
        seen.add(area)
        part = image.crop(area)
        with ocr.local_only(), ocr.quick_only():
            lines, _lang = ocr.image_to_lines(part)
        box = find(lines or [], content)
        if box is None:
            continue
        x0 = max(0, area[0] + box[0])
        y0 = max(0, area[1] + box[1])
        x1 = min(image.width, area[0] + box[2])
        y1 = min(image.height, area[1] + box[3])
        if x1 - x0 < 8 or y1 - y0 < 8:
            return None
        crop = image.crop((x0, y0, x1, y1))
        origin = (mon["left"] + x0 / scale, mon["top"] + y0 / scale)
        return crop, origin, scale
    return None
