"""A watermark stamped across a page in a grid, taken out before reading.

Documents shared inside companies are often stamped all over with a
reader's name, a number and a date, set at an angle and repeated in rows
and columns. The reader took the stamp for text: lines that crossed it
came back broken ("Current car" and a piece of Chinese, "A. Good data"),
and pieces of the stamp itself were translated and drawn over the page as
"2.2", "2026. Guang-" or "6 years, 0 months, 2 days".

What gives a stamp away is that it is exactly the same in every cell of
its grid, and nothing else on a page is. So:

  find_grid   the two steps the page repeats by (from where the picture
              looks most like itself moved along), kept only when a good
              share of one cell is the same in nearly every other cell -
              and not just straight lines, which look the same moved
              along themselves (a table's rules);
  cleaned     a copy of the page for reading only, where whatever is the
              same in every cell is painted over with the background
              around it - unless it stands out from the background more
              than the stamp does (the page's own text, in white or in
              colour, crossing it) or is in a colour the stamp is not.

The page shown and drawn on is the original: only the reader sees the
copy. Nothing here runs unless a grid is found.
"""
import time

import numpy as np
from PIL import Image, ImageFilter

ROUGH = 900          # longest side the grid is looked for at
FINE = 1600          # and checked at
EDGE = 18            # brightness step that counts as an edge
SAME = 0.5           # share of the copies a cell must be an edge in
SHARP = 0.2          # and how much more often than the cells around it
LOOSE_SAME = 0.3     # the same two, once a stamp is known to be there
LOOSE_SHARP = 0.12
ENOUGH = 0.003       # share of the page that is stamp
STEPS = 6            # steps tried in pairs
ONLY_HERE = 3.0      # how much more it is the same at its steps than near them
FEWEST = 6           # copies a cell needs to be judged
LEAST_STEP = 200     # shortest repeat, in screen pixels, that a stamp has
STAMP_TOP = 1.6      # the stamp at its strongest, against the middle of it
STANDS_OUT = 1.15    # how much more than the stamp the page's text stands out
COLOUR = 60          # how much more colourful than the background it is

last = {}            # what the last look found, for the log

# The screens snips were cut from, by a number kept in the snip's
# `info` (an Image there would go wherever the snip is copied or saved).
_wholes = {}
_grids = {}
_count = [0]


def remember_whole(img):
    """Keep the screen a snip is about to be cut from; the number to put
    in the snip's info as "stamp_whole"."""
    _count[0] += 1
    token = _count[0]
    _wholes[token] = img
    for old in [k for k in _wholes if k <= token - 2]:
        _wholes.pop(old, None)
        _grids.pop(old, None)
    return token


def grid_for(img):
    """(grid or None, whole, box) for a picture about to be read: looked
    for on the screen it was cut from when that is known."""
    token = img.info.get("stamp_whole") if hasattr(img, "info") else None
    whole = _wholes.get(token)
    box = img.info.get("stamp_box") if whole is not None else None
    if whole is None or box is None:
        return find_grid(img), None, None
    if token not in _grids:
        _grids[token] = find_grid(whole)
    return _grids[token], whole, box


def _gray(img):
    return np.asarray(img.convert("L")).astype(np.int16)


def _edges(g, step=EDGE):
    e = np.zeros(g.shape, bool)
    across = np.abs(np.diff(g, axis=1)) > step
    down = np.abs(np.diff(g, axis=0)) > step
    e[:, 1:] |= across
    e[1:, :] |= down
    return e


def _candidates(e, least, many=12):
    """Steps (dy, dx) the edges look most like themselves moved by."""
    h, w = e.shape
    s = e.astype(np.float32)
    s -= s.mean()
    F = np.fft.rfft2(s, s=(2 * h, 2 * w))
    ac = np.fft.fftshift(np.fft.irfft2(F * np.conj(F), s=(2 * h, 2 * w)))
    yy, xx = np.mgrid[-h:h, -w:w]
    over = ((h - np.abs(yy)).clip(1) * (w - np.abs(xx)).clip(1)).astype(
        np.float32)
    score = ac / over
    # A peak, not a hill: a stamp repeats to the pixel, so the page moved
    # by exactly its step matches and moved a few pixels more does not.
    # A page of text is alike moved by a line or two, give or take - a
    # broad rise, taken away here.
    k = 4
    pad = np.pad(score, k, mode="edge")
    c = pad.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    n = 2 * k + 1
    box = (c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n]) / (n * n)
    score = score - box
    # Seen at least twice more along each direction it steps.
    score[(np.abs(yy) > h // 2) | (np.abs(xx) > w // 2)] = 0
    score[(np.abs(yy) < least) & (np.abs(xx) < least)] = 0
    score[:h] = 0                       # one of each +/- pair
    score[h, :w] = 0
    # The best step in each direction, so the rows of a page of text -
    # alike moved sideways by a few characters - cannot crowd out the
    # step down to the next row of the stamp.
    angle = np.degrees(np.arctan2(yy, xx)) % 180.0
    sector = (angle // (180.0 / many)).astype(np.int32)
    found = []
    for k in range(many):
        here = np.where(sector == k, score, 0)
        i = int(np.argmax(here))
        y, x = divmod(i, here.shape[1])
        if here[y, x] > 0:
            found.append((here[y, x], (y - h, x - w)))
    found.sort(reverse=True)
    found = [step for _v, step in found]
    return found


def _cells(shape, P, Q, origin=(0, 0)):
    """For every pixel, which cell of the grid (P, Q) it falls in, and
    how many cells the grid has. `origin`: where this picture's top left
    is on the page the grid was found on."""
    H, W = shape
    M = np.array([[P[0], Q[0]], [P[1], Q[1]]], np.float64)
    inv = np.linalg.inv(M)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    yy += origin[0]
    xx += origin[1]
    a = inv[0, 0] * yy + inv[0, 1] * xx
    b = inv[1, 0] * yy + inv[1, 1] * xx
    a -= np.floor(a)
    b -= np.floor(b)
    n0 = max(1, int(round(np.hypot(*P))))
    n1 = max(1, int(round(np.hypot(*Q))))
    k0 = np.minimum((a * n0).astype(np.int32), n0 - 1)
    k1 = np.minimum((b * n1).astype(np.int32), n1 - 1)
    return k0 * n1 + k1, n0 * n1, (n0, n1)


def _same_everywhere(e, P, Q, same_at=None, sharp=None):
    """(share of the cell that is the same in nearly every copy, which
    cells, the cell index of every pixel)."""
    key, n, size = _cells(e.shape, P, Q)
    hit = np.bincount(key.ravel(), weights=e.ravel(), minlength=n)
    count = np.bincount(key.ravel(), minlength=n)
    judged = count >= FEWEST
    if judged.sum() < 0.5 * n:
        return 0.0, None, key
    frac = (hit / np.maximum(count, 1)).reshape(size)
    # The stamp is a thin line drawn in the same place in every copy: an
    # edge there nearly every time, and next to it hardly ever. A page of
    # text has edges somewhere near every point of a line of type, so a
    # point of it is "an edge in most copies" by chance - and so is the
    # point beside it.
    near = np.zeros_like(frac)
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            near += np.roll(np.roll(frac, dy, 0), dx, 1)
    near /= 25.0
    same = (judged.reshape(size) & (frac >= (same_at or SAME)) &
            (frac - near >= (sharp or SHARP))).ravel()
    # And drawn in strokes: a point of the stamp has others of it beside
    # it. Points of a page of text that happen to line up are scattered
    # dots (a sixth of them have two such neighbours, against half of a
    # stamp's).
    grid = same.reshape(size)
    beside = sum(np.roll(np.roll(grid, dy, 0), dx, 1)
                 for dy in (-1, 0, 1) for dx in (-1, 0, 1)) - grid
    same = (grid & (beside >= 2)).ravel()
    # Straight lines are the same moved along themselves: a table's rules
    # repeat with any step along the rule. A row or column of the cell
    # that is mostly "the same" is a rule, not a stamp.
    grid = same.reshape(size)
    rows = grid.mean(axis=1) > 0.5
    cols = grid.mean(axis=0) > 0.5
    grid = grid & ~rows[:, None] & ~cols[None, :]
    same = grid.ravel()
    return float(same.sum()) / max(1, judged.sum()), same, key


def _runs(mask, axis):
    """How long the straight run of `mask` through each pixel is."""
    m = mask if axis == 1 else mask.T
    h, w = m.shape
    idx = np.broadcast_to(np.arange(w), (h, w))
    left = idx - np.maximum.accumulate(np.where(~m, idx, -1), axis=1)
    ridx = idx[:, ::-1]
    right = (ridx - np.maximum.accumulate(np.where(~m[:, ::-1], ridx, -1),
                                          axis=1))[:, ::-1]
    out = np.where(m, left + right - 1, 0)
    return out if axis == 1 else out.T


def _scaled(img, longest, gray=False):
    w, h = img.size
    f = max(1.0, max(w, h) / float(longest))
    g = img.convert("L")
    if f > 1:
        g = g.resize((max(1, int(w / f)), max(1, int(h / f))),
                     Image.BILINEAR)
    g = _gray(g)
    if gray:
        return _edges(g), f, g
    return _edges(g), f


def _not_flat(g):
    """Points on an edge that is not lying flat. Every line of type has a
    flat edge along its foot and its top, the same all the way along, so
    a step sideways along a line of text finds them "the same" - lines a
    page wide, by the hundred. A stamp's letters have edges every way."""
    gx = np.zeros(g.shape, np.int16)
    gy = np.zeros(g.shape, np.int16)
    gx[:, 1:] = np.abs(np.diff(g, axis=1))
    gy[1:, :] = np.abs(np.diff(g, axis=0))
    gx = _grow(gx, 1)
    gy = _grow(gy, 1)
    return 2 * gx >= gy


def stamp_mask(e, P, Q, loose=False, part=None):
    """The points of the stamp, on the picture `e` was taken from - or on
    `part`, (its edges, top, left), a piece of it: the cells the same in
    nearly every copy, less straight streaks - the baselines of a page of
    text and the rules of a table repeat too, and are long and straight
    where a stamp's strokes are short."""
    # Once a stamp is known to be there, all of it is wanted: where it
    # crosses a picture or a line of text its edges are not seen in every
    # copy, and a piece left behind is read as a letter.
    if loose:
        share, same, key = _same_everywhere(e, P, Q, LOOSE_SAME, LOOSE_SHARP)
    else:
        share, same, key = _same_everywhere(e, P, Q)
    if same is None:
        return None
    if part is not None:
        e, top, left = part
        key, _n, _size = _cells(e.shape, P, Q, (top, left))
    m = same[key] if loose else same[key] & e
    long_ = max(12, int(0.04 * max(e.shape)))
    m &= (_runs(m, 1) < long_) & (_runs(m, 0) < long_)
    return m


def _refine(e, step, reach, sample=60000):
    """The step to the pixel, near `step` (found on a smaller copy of the
    page): where the edges line up with themselves best."""
    ys, xs = np.nonzero(e)
    if len(ys) > sample:
        pick = np.random.default_rng(0).choice(len(ys), sample,
                                               replace=False)
        ys, xs = ys[pick], xs[pick]
    h, w = e.shape
    y0, x0 = int(round(step[0])), int(round(step[1]))
    best, found = -1.0, (y0, x0)
    for dy in range(y0 - reach, y0 + reach + 1):
        for dx in range(x0 - reach, x0 + reach + 1):
            ty, tx = ys + dy, xs + dx
            ok = (ty >= 0) & (ty < h) & (tx >= 0) & (tx < w)
            if not ok.any():
                continue
            score = e[ty[ok], tx[ok]].mean()
            if score > best:
                best, found = score, (dy, dx)
    return found


def find_grid(img):
    """((dy, dx), (dy, dx)) in the picture's pixels, or None."""
    started = time.monotonic()
    last.clear()
    e, f = _scaled(img, ROUGH)
    sh, sw = e.shape
    least = max(20, int(LEAST_STEP / f))
    if sh < 2 * least or sw < 2 * least:
        return None
    steps = _candidates(e, least)[:STEPS]
    tried = []
    for i in range(len(steps)):
        for j in range(i + 1, len(steps)):
            P, Q = steps[i], steps[j]
            area = abs(P[0] * Q[1] - P[1] * Q[0])
            if area < 0.5 * np.hypot(*P) * np.hypot(*Q):
                continue                       # nearly the same direction
            share, _same, _key = _same_everywhere(e, P, Q)
            tried.append((share, area, P, Q))
    if not tried:
        last["ms"] = int(1000 * (time.monotonic() - started))
        return None
    top = max(t[0] for t in tried)
    # The smallest cell that explains it: twice the step is "the same"
    # too, and fewer copies make any cell look more alike.
    near = [t for t in tried if t[0] >= 0.8 * top and t[0] > 0]
    if not near:
        last["ms"] = int(1000 * (time.monotonic() - started))
        return None
    _share, _area, P, Q = min(near, key=lambda t: t[1])
    # Checked closer up: a stamp's strokes are thin, and only seen at
    # nearly the screen's own size.
    fine, g, fine_gray = _scaled(img, FINE, gray=True)
    k = f / g
    P2 = _refine(fine, (P[0] * k, P[1] * k), int(np.ceil(k / 2)) + 1)
    Q2 = _refine(fine, (Q[0] * k, Q[1] * k), int(np.ceil(k / 2)) + 1)
    upright = _not_flat(fine_gray)

    def share_for(a, b):
        m = stamp_mask(fine, a, b)
        return float((m & upright).mean()) if m is not None else 0.0
    share = share_for(P2, Q2)
    last["share"] = round(share, 4)
    if share < ENOUGH:
        last["ms"] = int(1000 * (time.monotonic() - started))
        return None
    # And only at these steps. Anything the same moved along by any
    # distance - the foot of every letter on a line of type, a rule - is
    # as much "the same" at a step a quarter longer; a stamp is not.
    other = max(share_for((int(P2[0] * 1.27), int(P2[1] * 1.27)), Q2),
                share_for(P2, (int(Q2[0] * 1.27), int(Q2[1] * 1.27))))
    last["other"] = round(other, 4)
    last["ms"] = int(1000 * (time.monotonic() - started))
    if share < ONLY_HERE * other:
        return None
    grid = ((int(round(P2[0] * g)), int(round(P2[1] * g))),
            (int(round(Q2[0] * g)), int(round(Q2[1] * g))))
    last["grid"] = grid
    return grid


def _background(img, keep, radius=7):
    """Every pixel's surroundings, from the pixels in `keep` only."""
    rgb = np.asarray(img.convert("RGB")).astype(np.float32)
    weight = keep.astype(np.float32)
    total = Image.fromarray((weight * 255).astype(np.uint8)).filter(
        ImageFilter.BoxBlur(radius))
    total = np.asarray(total).astype(np.float32) / 255.0
    out = np.empty_like(rgb)
    for c in range(3):
        layer = rgb[..., c] * weight
        top = max(1.0, float(layer.max()))
        blurred = Image.fromarray((layer / top * 255).astype(np.uint8)).filter(
            ImageFilter.BoxBlur(radius))
        out[..., c] = np.asarray(blurred).astype(np.float32) / 255.0 * top
    return out / np.maximum(total, 1e-3)[..., None], total


def _grow(a, r):
    """Each point the largest value within `r` of it (a square)."""
    out = a.copy()
    for axis in (0, 1):
        src = out.copy()
        for d in range(1, r + 1):
            if axis == 0:
                np.maximum(out[d:], src[:-d], out=out[d:])
                np.maximum(out[:-d], src[d:], out=out[:-d])
            else:
                np.maximum(out[:, d:], src[:, :-d], out=out[:, d:])
                np.maximum(out[:, :-d], src[:, d:], out=out[:, :-d])
    return out


def _to_size(a, size, resample=Image.NEAREST):
    if (a.shape[1], a.shape[0]) == size:
        return a
    if a.dtype == bool:
        return np.asarray(Image.fromarray(a.astype(np.uint8) * 255).resize(
            size, resample)) > 0
    return np.asarray(Image.fromarray(a).resize(size, resample))


def cleaned(img, grid=None, whole=None, box=None):
    """A copy of `img` for reading, with the stamp taken out; `img` itself
    when there is none.

    `whole` and `box`: the screen `img` was cut from, and where. A snip
    may hold too little of the stamp's grid to see it repeat; the screen
    holds plenty, and the stamp is in the same place on both."""
    started = time.monotonic()
    try:
        source = whole if whole is not None and box is not None else img
        if grid is None:
            grid = find_grid(source)
        if grid is None:
            return img
        fine, g = _scaled(source, FINE)
        P = (int(round(grid[0][0] / g)), int(round(grid[0][1] / g)))
        Q = (int(round(grid[1][0] / g)), int(round(grid[1][1] / g)))
        part = None
        if source is not img:
            x0, y0, x1, y1 = box
            size = (max(1, int(round((x1 - x0) / g))),
                    max(1, int(round((y1 - y0) / g))))
            piece = img.convert("L").resize(size, Image.BILINEAR)
            part = (_edges(_gray(piece)), y0 / g, x0 / g)
        sure = stamp_mask(fine, P, Q, part=part)
        loose = stamp_mask(fine, P, Q, loose=True, part=part)
        if loose is None or sure is None or not sure.any():
            return img
        if part is not None:
            g = img.width / float(part[0].shape[1])   # img pixels per point
        grow = 1 + int(round(g))
        stamp = _grow(_to_size(loose | sure, img.size), grow)
        sure = _grow(_to_size(sure, img.size), grow)
        rgb = np.asarray(img.convert("RGB"))
        lum = np.asarray(img.convert("L")).astype(np.float32)
        around, seen = _background(img, ~stamp, int(round(7 * max(1.0, g))))
        ys, xs = np.nonzero(stamp)
        here = around[ys, xs]
        step = np.abs(lum[ys, xs] - here.mean(axis=-1))
        on_sure = sure[ys, xs]
        if not (on_sure & (step > 25)).any():
            return img
        # How far the stamp stands out from the page: from the middle of
        # it where it is surely the stamp - the middle, because where the
        # stamp crosses the page's own writing that writing is in the
        # count, and it can be a fair part of it on a full page. The
        # writing stands out further, or is in a colour - and is left,
        # with the soft edge of its letters round it.
        stamp_step = STAMP_TOP * float(np.median(step[on_sure & (step > 25)]))
        last["stamp_step"] = round(stamp_step, 1)
        px = rgb[ys, xs].astype(np.int16)
        colour = px.max(axis=-1) - px.min(axis=-1)
        colour_bg = here.max(axis=-1) - here.min(axis=-1)
        core = (step > STANDS_OUT * stamp_step) | \
            ((colour - colour_bg) > COLOUR)
        letters = np.zeros(lum.shape, bool)
        letters[ys[core], xs[core]] = True
        # Writing is strokes; the stamp's brightest points, which also get
        # past the line, are specks. A point of writing has others round
        # it.
        r = max(1, int(round(g)))
        crowd = np.zeros(lum.shape, np.int16)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                crowd += np.roll(np.roll(letters, dy, 0), dx, 1)
        letters &= crowd >= (2 * r + 1) ** 2 // 2
        letters = _grow(letters, 1 + int(round(g)) // 2)
        own = letters[ys, xs]
        paint = ~own & (seen[ys, xs] > 0.05)
        out = rgb.copy()
        out[ys[paint], xs[paint]] = np.clip(here[paint], 0, 255).astype(
            np.uint8)
        last["painted"] = round(float(paint.sum()) / lum.size, 4)
        last["clean_ms"] = int(1000 * (time.monotonic() - started))
        return Image.fromarray(out)
    except Exception:
        return img


def describe():
    """One line for the log about the last page, or ''."""
    if not last.get("grid"):
        return ""
    return ("stamp      : watermark in a grid %s, %.1f%% the same in every "
            "cell; %.1f%% of the page painted over for reading (%d ms)"
            % (last["grid"], 100 * last.get("share", 0),
               100 * last.get("painted", 0),
               last.get("ms", 0) + last.get("clean_ms", 0)))
