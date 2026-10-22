"""Read ahead: read the page you have stopped on before you ask.

Reading a page (text recognition) is about half of what a snip or a hold
takes. The page is on screen the whole time you look at it, so Squint can
read it while you do: once a second a small, cheap look at the monitor the
pointer is on; when what is on it has changed and then stayed still for a
second, the whole monitor is read in the background and kept, with the
picture it was read from.

When you then snip or hold, and the screen still shows what was read, the
lines already read for that part of the screen are used and the reading is
skipped. If anything differs, it is read as it always was - the result is
never from a page that is not the one on screen.

Nothing is translated ahead, nothing leaves the computer, and only the one
most recent page is kept. Off unless switched on in Settings ("Read ahead").
"""
import sys
import threading
import time
import traceback

from PIL import Image, ImageChops, ImageStat

from . import config

CFG = config.CONFIG

LOOK_EVERY = 1.0          # seconds between the cheap looks
SETTLE = 1.0              # unchanged this long before it is read
THUMB = 8                 # the cheap look is the monitor / 8
CHANGED = 2.0             # mean pixel difference that counts as a change
SAME = 1.5                # at most this difference to reuse a reading
WAIT_FOR_READING = 1.5    # how long a snip waits for a reading under way
EARLY_WAIT = 6.0          # hold-to-see waits this long for the reading it
                          # started at the key press: it is the same work

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"


def _log(message):
    try:
        from .main import log
        log("read-ahead : %s" % message)
    except Exception:
        pass


class _NoScreen(Exception):
    pass


_failures = {}
FAILURE_EVERY = 600.0       # seconds before the same failure is logged again


def _log_failure():
    """The exception being handled, logged - once, not every second. A
    reading that fails the same way on every look (no screen to grab while
    the display sleeps; no reader for a blank page) filled one log with
    three thousand copies of the same traceback, 8 MB of it."""
    try:
        text = traceback.format_exc()
        last = text.strip().splitlines()[-1] if text.strip() else "?"
        now = time.monotonic()
        seen = _failures.get(last)
        if seen is not None and now - seen[0] < FAILURE_EVERY:
            _failures[last] = (seen[0], seen[1] + 1)
            return
        repeats = seen[1] if seen else 0
        _failures[last] = (now, 0)
        _log(text[-400:] + (" (and %d more like it)" % repeats
                            if repeats else ""))
    except Exception:
        pass


def enabled():
    # Retired: see main.py. Off whatever an old setting says.
    return False


def pointer():
    """Where the pointer is, in the coordinates windows are placed in,
    from any thread (Tk may only be asked from its own)."""
    try:
        if IS_MAC:
            import Quartz
            loc = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
            return float(loc.x), float(loc.y)
        if IS_WINDOWS:
            import ctypes
            from ctypes import wintypes
            point = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            return float(point.x), float(point.y)
    except Exception:
        pass
    return None


def _difference(a, b):
    if a is None or b is None or a.size != b.size:
        return 255.0
    stat = ImageStat.Stat(ImageChops.difference(a, b))
    return sum(stat.mean) / len(stat.mean)


def _thumb(image, factor=THUMB):
    try:
        return image.reduce(factor)
    except Exception:
        return image.resize((max(1, image.width // factor),
                             max(1, image.height // factor)))



# A page that keeps moving - a rotating banner, an advert - was read whole
# again every few seconds: a car portal, 260 lines, 6 seconds of the
# computer each time, 1,940 times in one log, and never once usable for a
# snip because the banner had moved on by then. Now only the rows that
# changed are read again, and the rest of the reading is kept.
BAND_LIMIT = 0.5          # rows changed above this share: read it all again
BAND_LEVEL = 24           # pixel difference that counts as changed
BAND_FACTOR = 4           # compared at a quarter of the size
BAND_GAP = 24             # changed rows closer than this are one band
BAND_PAD = 6              # pixels added around a band


def changed_bands(old, new, factor=BAND_FACTOR):
    """The rows where two pictures of the same size differ, as a list of
    (top, bottom) in pixels - [] when nothing changed, None when they
    cannot be compared."""
    if old is None or new is None or old.size != new.size:
        return None
    a = _thumb(old.convert("L"), factor)
    b = _thumb(new.convert("L"), factor)
    diff = ImageChops.difference(a, b).point(
        lambda v: 255 if v > BAND_LEVEL else 0)
    _cols, rows = diff.getprojection()
    bands, start, last = [], None, None
    gap = max(1, BAND_GAP // factor)
    for r, v in enumerate(rows):
        if not v:
            continue
        if start is None:
            start = r
        elif r - last > gap:
            bands.append((start, last))
            start = r
        last = r
    if start is not None:
        bands.append((start, last))
    return [(s * factor, min(new.height, (e + 1) * factor))
            for s, e in bands]


def widen_bands(bands, lines, height, pad=BAND_PAD):
    """Each band grown to take in whole every line it touches, and bands
    that then meet made one. Lines are dicts with "box" (x, y, w, h)."""
    out = []
    for top, bottom in bands:
        top, bottom = max(0, top - pad), min(height, bottom + pad)
        grew = True
        while grew:
            grew = False
            for line in lines:
                _x, y, _w, h = line["box"]
                if y < bottom and y + h > top and \
                        (y < top or y + h > bottom):
                    top, bottom = min(top, y), max(bottom, y + h)
                    grew = True
        out.append([max(0, top), min(height, bottom)])
    out.sort()
    merged = []
    for band in out:
        if merged and band[0] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], band[1])
        else:
            merged.append(band)
    return [tuple(b) for b in merged]


def reread_bands(image, lines, bands, read):
    """`lines` read from an earlier picture, brought up to date with
    `image`: lines in the changed bands are dropped and those bands read
    again with `read(picture) -> lines`. Returns (lines, count read)."""
    kept = [ln for ln in lines if not any(
        ln["box"][1] < bottom and ln["box"][1] + ln["box"][3] > top
        for top, bottom in bands)]
    fresh = []
    for top, bottom in bands:
        if bottom - top < 4:
            continue
        found = read(image.crop((0, top, image.width, bottom))) or []
        for line in found:
            x, y, w, h = line["box"]
            moved = dict(line)
            moved["box"] = (x, y + top, w, h)
            fresh.append(moved)
    # New lines go where their rows are in the reading order of the rest.
    out = list(kept)
    for line in fresh:
        y = line["box"][1]
        at = len(out)
        for i, other in enumerate(out):
            if other["box"][1] > y:
                at = i
                break
        out.insert(at, line)
    return out, len(fresh)


class Page:
    """One page read: the picture, where its monitor is, and its lines."""

    def __init__(self, image, monitor, scale, lines, lang, layers, took,
                 box=None, early=False):
        self.image = image
        # The part of `image` that was read, (x0, y0, x1, y1); lines exist
        # only for this part. The whole monitor for a background reading.
        self.box = box or (0, 0, image.width, image.height)
        self.early = early                # read at a key press, see below
        self.monitor = monitor            # {"left", "top", "width", "height"}
        self.scale = scale
        self.lines = lines                # boxes in pixels of `image`
        # Read in the background without a reader it needed (see
        # ocr.quick_only): not to be used for a snip.
        self.doubtful = False
        self.lang = lang
        self.layers = layers              # content_area.layers() at the time
        self.took = took
        self.thumb = _thumb(image)
        self.at = time.monotonic()


class Reader(threading.Thread):
    """The background loop. One per app."""

    def __init__(self):
        super().__init__(daemon=True, name="read-ahead")
        self.page = None
        self.reading = threading.Event()   # set while a reading is under way
        self.done = threading.Condition()
        self.paused = 0                    # >0 while Squint shows something
        self._stop = threading.Event()
        self._last = None
        self._changed_at = 0.0
        self._read_thumb = None
        self.read_started = 0.0

    def stop(self):
        self._stop.set()

    # The loop -------------------------------------------------------------
    def hold_off(self, seconds):
        """No new background reading for this long: you are snipping or
        holding, and the reading you asked for should have the computer
        to itself."""
        self.quiet_until = max(getattr(self, "quiet_until", 0.0),
                               time.monotonic() + seconds)

    def run(self):
        while not self._stop.wait(LOOK_EVERY):
            if not enabled() or self.paused > 0 or \
                    time.monotonic() < getattr(self, "quiet_until", 0.0):
                continue
            try:
                self._look()
            except _NoScreen:
                continue
            except Exception:
                _log_failure()

    def _grab(self):
        import mss
        where = pointer()
        with mss.mss() as sct:
            monitors = list(sct.monitors[1:]) or [sct.monitors[0]]
            chosen = monitors[0]
            if where:
                for mon in monitors:
                    if (mon["left"] <= where[0] < mon["left"] + mon["width"]
                            and mon["top"] <= where[1]
                            < mon["top"] + mon["height"]):
                        chosen = mon
                        break
            if int(chosen.get("width", 0)) <= 0 or \
                    int(chosen.get("height", 0)) <= 0:
                # No screen to read: the display is asleep or locked.
                raise _NoScreen()
            raw = sct.grab(chosen)
        image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        return image, dict(chosen), where

    def _look(self):
        if _squint_in_front() or _squint_busy():
            return            # its own windows are not a page to read
        image, monitor, where = self._grab()
        thumb = _thumb(image)
        now = time.monotonic()
        if _difference(thumb, self._last) > CHANGED:
            self._last = thumb
            self._changed_at = now
            return
        if now - self._changed_at < SETTLE:
            return
        if self._read_thumb is not None and \
                _difference(thumb, self._read_thumb) <= SAME:
            return                          # this page is already read
        if self.reading.is_set():
            return                          # a key-press reading under way
        if self._patch(image, monitor, thumb):
            return
        self._read(image, monitor, where, thumb)

    def _patch(self, image, monitor, thumb):
        """The page read last, brought up to date by reading again only
        the rows that changed - True if that was enough (or nothing inside
        the page changed), False when it must be read whole."""
        page = self.page
        if page is None or any(
                int(page.monitor.get(k, 0)) != int(monitor.get(k, 0))
                for k in ("left", "top", "width", "height")):
            return False
        if page.image.size != image.size:
            return False
        x0, y0, x1, y1 = page.box
        now = image.crop(page.box)
        bands = changed_bands(page.image.crop(page.box), now)
        if bands is None:
            return False
        if not bands:
            self._read_thumb = thumb   # only something outside the page
            return True
        if sum(b - t for t, b in bands) > BAND_LIMIT * max(1, y1 - y0):
            return False
        from . import ocr
        source = _source()
        near = []
        for line in page.lines:
            x, y, w, h = line["box"]
            moved = dict(line)
            moved["box"] = (x - x0, y - y0, w, h)
            near.append(moved)
        bands = widen_bands(bands, near, y1 - y0)
        started = time.monotonic()
        self.read_started = started
        self.reading.set()
        try:
            with ocr.local_only(), ocr.quick_only():
                lines, count = reread_bands(
                    now, near, bands,
                    lambda pic: ocr.image_to_lines(pic, source=source)[0])
                slow_skipped = ocr.skipped_slow()
            for line in lines:
                x, y, w, h = line["box"]
                line["box"] = (x + x0, y + y0, w, h)
            took = time.monotonic() - started
            with self.done:
                self.page = Page(image, page.monitor, page.scale, lines,
                                 page.lang, page.layers, page.took,
                                 box=page.box, early=page.early)
                self.page.doubtful = slow_skipped or getattr(
                    page, "doubtful", False)
                self._read_thumb = thumb
                self.done.notify_all()
            _log("read again only what changed: %d rows, %d lines in %.0fms"
                 % (sum(b - t for t, b in bands), count, 1000 * took))
        finally:
            self.reading.clear()
            with self.done:
                self.done.notify_all()
        return True

    def _read(self, image, monitor, where, thumb, early=False):
        from . import content_area, ocr
        scale = 1.0
        if IS_MAC and monitor.get("width"):
            scale = max(1.0, round(image.width / float(monitor["width"]), 2))
        started = time.monotonic()
        self.read_started = started
        self.reading.set()
        try:
            layers = content_area.layers(*where) if where else None
            source = _source()
            # Only the page in front, as hold-to-see would read it: on a 4K
            # screen the whole monitor took Windows' reader 3-5 seconds,
            # and every one of them was taken from the snip it overlapped.
            box = content_box(layers, monitor, scale, image.size)
            part = image if box == (0, 0, image.width, image.height) \
                else image.crop(box)
            # This computer's readers only. The background reading happens
            # to every page you stop on, whether you ever ask about it or
            # not; none of it may be sent anywhere. (1.48.39 fell through
            # to the cloud reader where Windows' own read doubtfully.)
            # In the background, Windows' reader only (ocr.quick_only):
            # a page that needs the slow one is left for the snip.
            slow_skipped = False
            # The key-press reading too: it reads the whole screen, and on
            # a friend's PC with three 4K screens the slow reader took
            # 15-28 s of it, which every snip then waited on. A snip that
            # needs the slow reader runs it on just the area it took.
            with ocr.local_only(), ocr.quick_only():
                lines, lang = ocr.image_to_lines(part, source=source)
                slow_skipped = ocr.skipped_slow()
            lines = lines or []
            if box[0] or box[1]:
                for line in lines:
                    x, y, w, h = line["box"]
                    line["box"] = (x + box[0], y + box[1], w, h)
            took = time.monotonic() - started
            with self.done:
                self.page = Page(image, monitor, scale, lines, lang,
                                 layers, took, box=box, early=early)
                self.page.doubtful = slow_skipped
                if not early:
                    self._read_thumb = thumb
                self.done.notify_all()
            _log("%s %d lines in %.0fms (%s)"
                 % ("read at the key press:" if early else "read",
                    len(lines), 1000 * took, lang or "?"))
        finally:
            self.reading.clear()
            with self.done:
                self.done.notify_all()

    def read_now(self):
        """Begin reading the page in front at once - called the moment the
        snip shortcut goes down, before it is known whether it will be a
        tap (snip) or a hold (hold-to-see). Either way the page is about
        to be read; starting now takes that time off the wait. The picture
        is taken here, before anything of Squint's is on screen; the
        reading runs in the background, on this computer only. For a tap
        the snip uses whatever of it lies inside the box you drag."""
        if self.reading.is_set():
            return False
        self.reading.set()               # at once, so nothing waits in vain
        self.read_started = time.monotonic()
        # The picture is taken on the reading's own thread. Taken here, on
        # the thread that watches the key, a 4K grab held up the first look
        # at whether the key was still down.
        threading.Thread(target=self._read_safely, daemon=True).start()
        return True

    def _read_safely(self):
        try:
            image, monitor, where = self._grab()
            self._read(image, monitor, where, None, early=True)
        except Exception:
            self.reading.clear()
            with self.done:
                self.done.notify_all()
            _log_failure()

    # Using it -------------------------------------------------------------
    def current(self, wait=WAIT_FOR_READING):
        """The latest page, waiting briefly if one being read now will be
        done within `wait`. A reading that has only just begun - on a 4K
        screen they take seconds - is not waited for: reading the snip
        itself is quicker than that."""
        if self.reading.is_set():
            last = self.page.took if self.page is not None else 1.0
            left = last - (time.monotonic() - self.read_started)
            if left > wait and wait < EARLY_WAIT:
                return self.page
            with self.done:
                self.done.wait_for(lambda: not self.reading.is_set(),
                                   timeout=wait)
        return self.page

    def lines_for(self, crop, box, monitor_left, monitor_top, wait=True,
                  strict=True, page=None):
        """Lines already read for `crop`, which is the part `box`
        (x0, y0, x1, y1, in pixels of the monitor at monitor_left/top)
        of the screen - or None when they cannot be trusted to be the same
        as reading `crop` now.

        None when: nothing is read; it was another monitor; the screen has
        changed there since; or a line was cut by the edge of the box (a
        snip reads the part of a line inside its box; the whole line was
        read here, so it is read afresh instead)."""
        if wait is True:
            wait = WAIT_FOR_READING
        if page is None:
            page = self.current(wait or 0)

        def no(why):
            # Why the reading was not used, so a log can say whether read
            # ahead helped and, when it did not, what stood in the way.
            _log("not used: %s" % why)
            return None
        if page is None:
            return no("nothing read yet" if not self.reading.is_set()
                      else "still reading")
        if not page.early and not enabled():
            return None               # read ahead was switched off since
        if getattr(page, "doubtful", False):
            return no("Windows could not read it well; read again")
        if time.monotonic() - page.at > 120:
            return no("read too long ago")
        if int(page.monitor.get("left", 0)) != int(monitor_left) or \
                int(page.monitor.get("top", 0)) != int(monitor_top):
            return no("another monitor")
        x0, y0, x1, y1 = [int(v) for v in box]
        rx0, ry0, rx1, ry1 = page.box
        if x0 < rx0 - 2 or y0 < ry0 - 2 or x1 > rx1 + 2 or y1 > ry1 + 2:
            return no("outside what was read")
        then = page.image.crop((x0, y0, x1, y1))
        if then.size != crop.size:
            return no("size differs")
        bands = changed_bands(then, crop)
        if bands is None:
            return no("cannot compare")
        changed = sum(b - t for t, b in bands)
        if changed > BAND_LIMIT * max(1, crop.height):
            return no("the screen changed there (%d%% of rows)"
                      % (100 * changed // max(1, crop.height)))
        out, cut = [], []
        for line in page.lines:
            x, y, w, h = line["box"]
            ix0, iy0 = max(x, x0), max(y, y0)
            ix1, iy1 = min(x + w, x1), min(y + h, y1)
            if ix1 <= ix0 or iy1 <= iy0:
                continue                         # outside the box
            inside = (ix1 - ix0) * (iy1 - iy0) / float(max(1, w * h))
            if inside < 0.9:
                if strict:
                    # A snip reads the part of a line inside its box: that
                    # line's rows are read again from the snip itself.
                    top = max(0, y - y0)
                    cut.append((top, min(crop.height, y - y0 + h)))
                continue          # hold-to-see: a line cut by the page's
                                  # edge is left as it is, as when it reads
            moved = dict(line)
            moved["box"] = (x - x0, y - y0, w, h)
            out.append(moved)
        # Text the earlier reading has no line on. Read ahead reads the
        # whole window, and at that size the reader can pass over a
        # paragraph or two; a snip that took that reading as it was left
        # them in the original, between translated paragraphs.
        missing = _unread_bands(crop, out)
        if missing:
            _log("rows of text not in the earlier reading: %d"
                 % sum(b - t for t, b in missing))
            bands = sorted(bands + missing)
        if cut:
            bands = sorted(bands + cut)
            changed = sum(b - t for t, b in bands)
            if changed > BAND_LIMIT * max(1, crop.height):
                return no("the box cuts too many lines")
        if bands:
            # Part of it moved on since (a banner, an advert), or the box
            # cuts a few lines: only those rows are read now, the rest is
            # as it was read.
            from . import ocr
            source = _source()
            started = time.monotonic()
            bands = widen_bands(bands, out, crop.height)
            out, count = reread_bands(
                crop, out, bands,
                lambda pic: ocr.image_to_lines(pic, source=source)[0])
            _log("read again only what changed: %d rows, %d lines in %.0fms"
                 % (sum(b - t for t, b in bands), count,
                    1000 * (time.monotonic() - started)))
        return out, page


def _unread_bands(crop, lines, least=6):
    """(top, bottom) runs of rows of `crop` with writing in them - sharp
    edges along the row - that no line in `lines` covers."""
    try:
        from PIL import ImageChops
        gray = crop.convert("L")
        edges = ImageChops.difference(gray, ImageChops.offset(gray, 1, 0)) \
            .point(lambda v: 255 if v > 60 else 0)
        per_row = list(edges.resize((1, gray.height), Image.BOX).tobytes())
        covered = [False] * gray.height
        for line in lines:
            _x, y, _w, h = line["box"]
            for row in range(max(0, int(y) - 2),
                             min(gray.height, int(y + h) + 3)):
                covered[row] = True
        out, start = [], None
        for row, value in enumerate(per_row + [0]):
            texty = row < gray.height and value > 0.015 * 255 and \
                not covered[row]
            if texty and start is None:
                start = row
            elif not texty and start is not None:
                if row - start >= least:
                    out.append((start, row))
                start = None
        return out
    except Exception:
        return []


# Set by the app: true while Squint has something of its own on screen - a
# translation drawn over the page, a card, the snip picker, hold-to-see.
# On Windows those do not always take the foreground, and read ahead then
# read Squint's own translation as if it were a new page.
BUSY = None


def _squint_busy():
    try:
        return bool(BUSY and BUSY())
    except Exception:
        return False


def _squint_in_front():
    import os
    try:
        if IS_MAC:
            from AppKit import NSWorkspace
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            return app is not None and \
                int(app.processIdentifier()) == os.getpid()
        if IS_WINDOWS:
            import ctypes
            from ctypes import wintypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            pid = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(
                hwnd, ctypes.byref(pid))
            return pid.value == os.getpid()
    except Exception:
        pass
    return False


def lines_at(crop, origin, scale):
    """Lines already read for a snip of `crop`, taken at `origin` (the
    coordinates windows are placed in) - or None. See Reader.lines_for.

    Two readings are tried: the page read ahead (or at the key press), and
    the last snip's own reading (remember_snip) - so snipping again round
    much the same text, after cancelling or not, does not read it again."""
    if READER is None:
        return None
    # The reading begun at the key press is waited for, not skipped: a snip
    # and hold-to-see of the same page must start from the same reading, or
    # the same word read two ways is translated two ways.
    for page in (READER.current(EARLY_WAIT),
                 getattr(READER, "snipped", None)):
        got = _lines_on(page, crop, origin, scale)
        if got is not None:
            return got
    return None


def _lines_on(page, crop, origin, scale):
    if page is None:
        return None
    try:
        mon = page.monitor
        ox, oy = float(origin[0]), float(origin[1])
        if not (mon["left"] <= ox < mon["left"] + mon["width"]
                and mon["top"] <= oy < mon["top"] + mon["height"]):
            return None
        if abs(float(scale or 1.0) - page.scale) > 0.05:
            return None
        x0 = int(round((ox - mon["left"]) * page.scale))
        y0 = int(round((oy - mon["top"]) * page.scale))
        box = (x0, y0, x0 + crop.width, y0 + crop.height)
        return READER.lines_for(crop, box, mon["left"], mon["top"],
                                wait=False, page=page)
    except Exception:
        _log_failure()
        return None


def remember_snip(image, origin, scale, lines, lang):
    """Keep a snip's own reading, as a page of just that area, for the
    next snip there (lines_at). Only the latest is kept."""
    if READER is None or not lines:
        return
    try:
        s = float(scale or 1.0)
        area = {"left": float(origin[0]), "top": float(origin[1]),
                "width": image.width / s, "height": image.height / s}
        READER.snipped = Page(image, area, s, [dict(l) for l in lines],
                              lang, None, 0.0, early=True)
    except Exception:
        _log_failure()


def content_box(layers, monitor, scale, size):
    """The page in front, in pixels of the monitor's picture - the area
    hold-to-see translates (xray.snip_area)."""
    width, height = size
    for key in ("content", "window", "monitor"):
        rect = (layers or {}).get(key)
        if not rect:
            continue
        x0 = int((rect[0] - monitor["left"]) * scale)
        y0 = int((rect[1] - monitor["top"]) * scale)
        x1 = x0 + int(rect[2] * scale)
        y1 = y0 + int(rect[3] * scale)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(width, x1), min(height, y1)
        if x1 - x0 >= 40 and y1 - y0 >= 40:
            return (x0, y0, x1, y1)
    return (0, 0, width, height)


def read_now():
    if READER is not None:
        try:
            return READER.read_now()
        except Exception:
            _log_failure()
    return False


def _source():
    try:
        from .langs import code_for_name
        chosen = str(CFG.get("source_lang_name", "") or "")
        if chosen and not chosen.lower().startswith("detect"):
            return code_for_name(chosen) or ""
    except Exception:
        pass
    return ""


READER = None


def start():
    global READER
    if READER is None:
        READER = Reader()
        READER.start()
    return READER


class paused:
    """`with preread.paused():` while Squint puts something on screen, so
    its own windows are never taken for a page that changed."""

    def __enter__(self):
        if READER is not None:
            READER.paused += 1

    def __exit__(self, *exc):
        if READER is not None:
            READER.paused = max(0, READER.paused - 1)
        return False


def hold_off(seconds=8.0):
    if READER is not None:
        READER.hold_off(seconds)


def lines_for(crop, box, monitor_left, monitor_top):
    """Module-level convenience; None when read-ahead is off or unusable."""
    if READER is None or not enabled():
        return None
    try:
        return READER.lines_for(crop, box, monitor_left, monitor_top)
    except Exception:
        _log_failure()
        return None
