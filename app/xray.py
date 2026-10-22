"""Hold-to-see: the whole screen, translated in place, while a key is held.

Press Ctrl+Alt+X and keep holding (Ctrl+Alt is enough once X is pressed):
the monitor the pointer is on freezes and fills with translations where
the text was, in reading order - top to bottom, column by column. Let go
and it is gone. Press X a second time while still holding Ctrl+Alt
(Ctrl+Alt+X X) and it stays after letting go, until Esc, a click or
Ctrl+Alt+X again.

What happens on a press:

1. The monitor under the pointer is captured at once, before anything of
   Squint's is drawn over it.
2. A borderless window shows that capture, so the screen looks frozen and
   nothing underneath can scroll away from the translation.
3. The capture is read in one pass, its paragraphs put in reading order,
   and sent to the engine a few at a time. The first batch is small, so the
   top of the screen appears quickly. Batches run side by side but are
   shown strictly in order, so the screen fills the way it is read.
4. Every batch is remembered by its text. Looking again at the same screen,
   or at a page that has only scrolled a little, redraws what is known at
   once and translates only what is new. A batch still being translated
   when the key is let go is finished anyway and kept for the next look.
"""
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

import tkinter as tk
from PIL import Image

from . import (config, content_area, keystate, ocr, overlay,
               platform_util, translator)
from .translator import Cancelled, memory_tag, set_background, set_stop

CFG = config.CONFIG

POLL_MS = 40            # how often the held key is checked
FIRST_BATCH = 2         # paragraphs in the first batch: fast first paint
REST_BATCHES = 3        # the rest of the page in at most this many
MIN_BATCH = 6           # paragraphs, so a short page is not cut up
WORKERS = 4             # every batch at once (there are at most 4)
CACHE_SIZE = 400        # batches remembered

_cache = {}
_cache_order = []
_cache_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=WORKERS)


def _log(message):
    try:
        from .main import log
        log("xray       : %s" % message)
    except Exception:
        pass


# -- reading order and batches -------------------------------------------

def reading_order(lines, groups, page_width):
    """Paragraph groups sorted as a page is read: column by column, left
    to right, and top to bottom within each column."""
    if not groups:
        return []
    try:
        cols = overlay.columns(lines, page_width)
    except Exception:
        cols = []
    column_of = {}
    for number, column in enumerate(cols):
        for index in column["indexes"]:
            column_of[index] = number

    def key(group):
        first = min(group, key=lambda i: (lines[i]["box"][1],
                                          lines[i]["box"][0]))
        return (column_of.get(first, 0), lines[first]["box"][1],
                lines[first]["box"][0])
    return sorted(groups, key=key)


def batches(ordered, first=FIRST_BATCH, most=REST_BATCHES):
    """A small first batch, so the top of the page appears quickly, and
    the rest in at most `most` batches. Every batch costs a full layout of
    the screen; nineteen small ones on a busy page took nine seconds where
    the translation itself took one."""
    if not ordered:
        return []
    out = [ordered[:first]]
    rest = ordered[first:]
    if rest:
        size = max(MIN_BATCH, -(-len(rest) // most))
        for start in range(0, len(rest), size):
            out.append(rest[start:start + size])
    return [b for b in out if b]


def _cache_key(target, source, sub, groups=None):
    return (target, source, tuple(str(line.get("text", "")) for line in sub),
            tuple(tuple(g) for g in (groups or ())))


def _cache_get(key):
    with _cache_lock:
        return _cache.get(key)


def _cache_put(key, value):
    with _cache_lock:
        if key not in _cache:
            _cache_order.append(key)
        _cache[key] = value
        while len(_cache_order) > CACHE_SIZE:
            _cache.pop(_cache_order.pop(0), None)


def translate_batch(sub, target, source, groups=None):
    """Translate one batch of lines. Returns (texts, paras, para_texts),
    one entry per line, from the cache when this text was seen before.

    `groups` is the paragraph grouping found on the whole screen, as
    indexes into `sub`. Grouping the batch again on its own would lose
    what told a table cell from a line of prose."""
    key = _cache_key(target, source, sub, groups)
    known = _cache_get(key)
    if known is not None:
        return known
    texts = overlay.translate_grouped(sub, translator, target,
                                      source=source or "auto",
                                      groups=groups)
    result = (list(texts), [line.get("para") for line in sub],
              [line.get("para_text") for line in sub])
    _cache_put(key, result)
    return result


def inside(lines, rect):
    """The lines whose centre lies in `rect` (x, y, w, h in image pixels);
    all of them when there is no rect."""
    if rect is None:
        return list(lines)
    x0, y0, w, h = rect
    out = []
    for line in lines:
        x, y, lw, lh = line["box"]
        cx, cy = x + lw / 2.0, y + lh / 2.0
        if x0 <= cx < x0 + w and y0 <= cy < y0 + h:
            out.append(line)
    return out


_ENGLISH = set("""the a an and or of to in on at for with from by is are was
were be been it this that these those you your we our they their he she his
her not no yes can will would should may more most all any about as if than
then so do does did have has had which who what when where how""".split())


def already_in(target, text):
    """Is this line already in the language being translated into? Only
    answered for English, from its commonest words: cheap enough to ask of
    every line, and English is where it matters - menus, buttons and
    headings on foreign pages are often English already, and sending them
    to the engine costs time for nothing."""
    if not str(target or "").lower().startswith("en"):
        return False
    words = [w.strip(".,:;!?()[]\"'’").lower()
             for w in str(text or "").split()]
    words = [w for w in words if w]
    if len(words) < 3:
        return False
    if any(not ch.isascii() for w in words for ch in w if ch.isalpha()):
        return False
    common = sum(1 for w in words if w in _ENGLISH)
    return common >= max(2, len(words) * 0.25)


def arrange(lines, content, window, monitor, edge=0):
    """(first, later): what the window in front shows, in its page or
    document, and then the rest of the monitor.

    The frame of the window in front - tabs, address bar, bookmarks, its
    toolbar - is left out: it is the same on every page. The menu bar,
    the Dock and the taskbar are left out. Other windows' text comes after
    the window in front's, so the thing being read is translated first."""
    def centre_in(line, rect):
        if rect is None:
            return False
        x, y, w, h = line["box"]
        cx, cy = x + w / 2.0, y + h / 2.0
        return rect[0] <= cx < rect[0] + rect[2] and \
            rect[1] <= cy < rect[1] + rect[3]
    if content is None and window is None:
        if monitor is None:
            return list(lines), []
        return [ln for ln in lines if centre_in(ln, monitor)], []
    def cut_by(line, rect):
        # A line the top or bottom of the page cuts through is half a
        # line: read as nonsense ("Dienctradlaacina ict ain") and
        # translated as nonsense. Left as it is.
        top, bottom = line["box"][1], line["box"][1] + line["box"][3]
        return top <= rect[1] + edge or bottom >= rect[1] + rect[3] - edge

    first, later = [], []
    for line in lines:
        if centre_in(line, content):
            if not cut_by(line, content):
                first.append(line)
        elif centre_in(line, window):
            continue                      # the window's own frame
        elif monitor is None or centre_in(line, monitor):
            later.append(line)
    return first, later


def snip_area(shot, size):
    """The area a person would have snipped: the page or document of the
    window in front; else that window; else the monitor less its bars."""
    width, height = size
    for key in ("area", "window", "monitor"):
        rect = shot.get(key)
        if not rect:
            continue
        x0, y0 = max(0, int(rect[0])), max(0, int(rect[1]))
        x1 = min(width, int(rect[0] + rect[2]))
        y1 = min(height, int(rect[1] + rect[3]))
        if x1 - x0 >= 40 and y1 - y0 >= 40:
            return (x0, y0, x1, y1)
    return (0, 0, width, height)


def forget():
    """Drop every remembered page (a setting changed)."""
    with _cache_lock:
        _cache.clear()
        _cache_order.clear()


# Pages being prepared ahead (XRay.prepare): key -> Event set when done.
_preparing = {}
_preparing_lock = threading.Lock()
PREPARED_WAIT = 30.0


def _wait_prepared(key, wait=PREPARED_WAIT):
    """The blocks of a page being prepared ahead, once it is done - or None
    at once when this page is not being prepared."""
    with _preparing_lock:
        done = _preparing.get(key)
    if done is None:
        return None
    done.wait(wait)
    return _cache_get(key)


def preparing_any():
    with _preparing_lock:
        return list(_preparing.values())


# After X is let go with Ctrl and Alt still held, how long a second tap of
# X has to keep the view before it closes.
LOCK_GRACE = 0.45


def _fingerprint(image):
    import hashlib
    small = image.reduce(4) if image.width > 400 else image
    return hashlib.md5(small.tobytes()).hexdigest()


def _moved(block, dx, dy, size):
    """A block laid out on a crop, in the coordinates of the whole capture,
    clipped to the crop as a snip's window clips it."""
    b = dict(block)
    x0, y0, x1, y1 = b["cover"]
    b["cover"] = (x0 + dx, y0 + dy, min(x1, size[0]) + dx,
                  min(y1, size[1]) + dy)
    b["x"] = b["x"] + dx
    b["y"] = b["y"] + dy
    if b.get("right"):
        b["right"] = b["right"] + dx
    return b


def mark_cells(lines):
    """Mark table cells found on the whole screen, so a layout of part of
    it treats them as cells too."""
    held = overlay.held_back(lines)
    keep = [i for i in range(len(lines)) if i not in held]
    for j in overlay.cells_in([lines[i] for i in keep]):
        lines[keep[j]]["is_cell"] = True


def text_region(lines, bounds, pad=12):
    """The part of the page the text is in: from the leftmost line to the
    rightmost, the top line to the bottom of the content.

    A snip is laid out inside the area that was dragged; the space beside
    its text is the edge of the capture. Hold-to-see captured the whole
    window, and a page whose text column ends two thirds of the way across
    had the rest as empty room - so every paragraph spread into it, one
    line running the full width of the screen, the next at a different
    size. Laying out inside the text's own extent gives the page the same
    room a snip of it gets."""
    bx0, by0, bx1, by1 = bounds
    if not lines:
        return bounds
    x0 = min(ln["box"][0] for ln in lines) - pad
    y0 = min(ln["box"][1] for ln in lines) - pad
    x1 = max(ln["box"][0] + ln["box"][2] for ln in lines) + pad
    return (max(bx0, x0), max(by0, y0), min(bx1, x1), by1)


def layout_region(page, region, lines, texts, target, floor):
    """Lay out `lines` inside `region` of `page`, at the page's own
    resolution. Returns the blocks, in page coordinates."""
    rx0, ry0, rx1, ry1 = region
    if rx1 - rx0 < 20 or ry1 - ry0 < 20:
        rx0, ry0, rx1, ry1 = 0, 0, page.width, page.height
    part = page.crop((rx0, ry0, rx1, ry1))
    moved = []
    for line in lines:
        x, y, w, h = line["box"]
        moved.append(dict(line, box=(x - rx0, y - ry0, w, h)))
    blocks, _tall = fitted_layout(part, moved, texts, target, floor,
                                  part.height)
    out = []
    for block in blocks:
        b = dict(block)
        x0, y0, x1, y1 = b["cover"]
        b["cover"] = (x0 + rx0, y0 + ry0,
                      min(x1, part.width) + rx0, min(y1, part.height) + ry0)
        b["x"] = b["x"] + rx0
        b["y"] = b["y"] + ry0
        if b.get("right"):
            b["right"] = b["right"] + rx0
        out.append(b)
    return out


def paint_region(page, region, lines, texts, target, floor):
    """The page with the translation painted in, as a picture (tests and
    anything that wants a bitmap; the screen draws the blocks instead)."""
    blocks = layout_region(page, region, lines, texts, target, floor)
    if not blocks:
        return page
    return overlay.paint(page, blocks, page.height)


def fitted_layout(image, lines, texts, target, floor, bottom):
    """overlay.layout, stepping the smallest size down when the text would
    run past `bottom` - on screen there is nothing below the window to
    grow into, and text drawn over the Dock is worse than smaller text."""
    size = floor
    least = max(6, int(floor * 0.6))
    while True:
        blocks, tall = overlay.layout(image, lines, texts, target,
                                      min_size=size, reach=False)
        lowest = max((b["cover"][3] for b in blocks), default=0)
        if lowest <= bottom or size <= least:
            return blocks, min(tall or 0, image.height)
        size = max(least, int(size * 0.85))


def _apply(sub, result, number):
    """Write a batch's paragraph numbers back onto its lines, made unique
    across batches so two batches' paragraph 0 are not laid out as one."""
    texts, paras, para_texts = result
    for line, para, para_text in zip(sub, paras, para_texts):
        if para is not None:
            line["para"] = number * 100000 + int(para)
            line["para_text"] = para_text or ""
    return texts


# -- focus -------------------------------------------------------------------

def _frontmost():
    """Whatever had the keyboard before Squint came forward."""
    try:
        if platform_util.IS_MAC:
            from AppKit import NSWorkspace
            return NSWorkspace.sharedWorkspace().frontmostApplication()
        if platform_util.IS_WINDOWS:
            import ctypes
            return ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        pass
    return None


def _give_back(previous):
    """Put the app that was in front back in front, so the browser under a
    translation is still the active app when it is gone."""
    if not previous:
        return
    try:
        if platform_util.IS_MAC:
            import os
            if int(previous.processIdentifier()) != os.getpid():
                previous.activateWithOptions_(2)   # ignoring other apps
        elif platform_util.IS_WINDOWS:
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(previous)
    except Exception:
        pass


# -- the window ----------------------------------------------------------

class XRay:
    """One per app. `press()` is called on the Tk thread for every press of
    the shortcut; frames come back through the controller's queue."""

    def __init__(self, controller):
        self.controller = controller
        self.root = controller.root
        self.session = 0
        self.win = None
        self.canvas = None
        self.photo = None
        self.item = None
        self.pill = None
        self.pill_bg = None
        self.sticky = False
        self.key_released = False
        self.spec = ""
        self.geometry = None
        self.pending = None
        self.opening = False
        self.previous = None
        self.main_alpha = None
        self.opened_at = 0.0
        self.closed_at = 0.0

    # Tk thread -----------------------------------------------------------
    def press(self, spec):
        if self.win is not None or self.opening:
            if self.sticky:
                # Pressed again after freezing: close.
                self.close()
            elif self.key_released:
                # X pressed a second time with Ctrl+Alt still held: freeze.
                self._make_sticky()
            # Otherwise the key's own auto-repeat: ignored.
            return
        busy = getattr(self.controller, "busy", None)
        if busy is not None and busy.locked():
            return                      # a snip is being picked
        self.spec = spec
        self.sticky = False
        self.key_released = False
        try:
            shot = self._capture()
        except Exception:
            _log("capture failed\n%s" % traceback.format_exc())
            return
        if shot is None:
            return
        self.session += 1
        session = self.session
        try:
            from . import offline_model, profile
            if profile.current() in (profile.AUTO, profile.LOCAL):
                offline_model.warm()
        except Exception:
            pass
        self.pending = None
        self.opening = True
        self.previous = _frontmost()
        self.opened_at = time.monotonic()
        if platform_util.IS_MAC:
            # Asking macOS to bring the app forward is a request, not
            # something done by the next line; a window built before it
            # lands is built behind everything. See Controller.trigger_snip.
            # The app that was in front is given its place back on close.
            self._hide_main()
            platform_util.become_foreground_app()
            self.root.after(80, lambda: self._open_if(session, shot))
        else:
            self._open_if(session, shot)
        self.root.after(POLL_MS, lambda: self._watch_key(session))
        threading.Thread(target=self._work, args=(session, shot),
                         daemon=True).start()

    def _capture(self):
        """The monitor under the pointer, as (image, left, top, w, h, scale)
        with left/top/w/h in the coordinates Tk places windows in."""
        import mss
        px, py = self.root.winfo_pointerxy()
        # Asked before Squint shows anything or comes forward, so the
        # window found is the one being read.
        found = None
        with mss.mss() as sct:
            monitors = list(sct.monitors[1:]) or [sct.monitors[0]]
            chosen = monitors[0]
            for mon in monitors:
                if (mon["left"] <= px < mon["left"] + mon["width"]
                        and mon["top"] <= py < mon["top"] + mon["height"]):
                    chosen = mon
                    break
            raw = sct.grab(chosen)
        image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        scale = 1.0
        if platform_util.IS_MAC and chosen["width"]:
            scale = max(1.0, round(image.width / float(chosen["width"]), 2))
        # The page area as found when this page was read ahead, if the
        # screen is unchanged: finding it again can take half a second.
        try:
            from . import preread
            page = preread.READER.page if preread.READER is not None \
                else None
            if page is not None and page.layers and \
                    int(page.monitor["left"]) == int(chosen["left"]) and \
                    int(page.monitor["top"]) == int(chosen["top"]) and \
                    page.image.size == image.size and \
                    preread._difference(page.thumb,
                                        preread._thumb(image)) <= \
                    preread.SAME:
                found = page.layers
        except Exception:
            found = None
        if found is None:
            found = content_area.layers(px, py)
        how = found.get("how")

        def px_rect(rect):
            if rect is None:
                return None
            return (int((rect[0] - chosen["left"]) * scale),
                    int((rect[1] - chosen["top"]) * scale),
                    int(rect[2] * scale), int(rect[3] * scale))
        return {"image": image, "left": int(chosen["left"]),
                "top": int(chosen["top"]), "width": int(chosen["width"]),
                "height": int(chosen["height"]), "scale": scale,
                "area": px_rect(found.get("content")),
                "window": px_rect(found.get("window")),
                "monitor": px_rect(found.get("monitor")),
                "area_how": how}

    def _open_if(self, session, shot):
        self.opening = False
        if session != self.session:
            return
        self._open_window(shot)
        pending, self.pending = self.pending, None
        if pending is not None:
            self.frame(pending)

    def _open_window(self, shot):
        from .snip import _geometry_string
        w, h = shot["width"], shot["height"]
        win = tk.Toplevel(self.root)
        # Kept off screen until it is the right size, in the right place,
        # showing the capture: otherwise it can be seen for a frame as an
        # empty window somewhere else.
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry(_geometry_string(w, h, shot["left"], shot["top"]))
        win.configure(bg="black")
        canvas = tk.Canvas(win, width=w, height=h, highlightthickness=0,
                           bd=0, bg="black")
        canvas.pack(fill="both", expand=True)
        self.win, self.canvas, self.geometry = win, canvas, (w, h)
        self._show_image(shot["image"], shot["scale"])
        self._status("Reading…")
        for widget in (win, canvas):
            widget.bind("<Escape>", lambda _e: self.close())
            widget.bind("<Button-1>", lambda _e: self._click())
        try:
            win.update_idletasks()
            win.deiconify()
            win.lift()
        except Exception:
            pass

    def _hide_main(self):
        """Squint's own window, made invisible while hold-to-see is up.

        Bringing Squint forward brings every window it has forward, and
        its main window - open in the background - flashed over the page
        for a frame on every press. Made fully transparent first, it is
        brought forward without being seen; on close it is put back
        behind and made visible again."""
        window = getattr(self.controller, "window", None)
        try:
            if window is None or not window.winfo_viewable():
                return
            if self.main_alpha is None:
                self.main_alpha = float(window.attributes("-alpha") or 1.0)
            window.attributes("-alpha", 0.0)
        except Exception:
            self.main_alpha = None

    def _show_main(self):
        alpha, self.main_alpha = self.main_alpha, None
        if alpha is None:
            return
        window = getattr(self.controller, "window", None)

        def restore():
            try:
                window.lower()
                window.attributes("-alpha", alpha)
            except Exception:
                pass
        # After the app underneath is in front again, so it comes back
        # behind that app rather than over it.
        try:
            self.root.after(300, restore)
        except Exception:
            restore()

    def _show_image(self, image, scale):
        from PIL import ImageTk
        w, h = self.geometry
        if image.height > int(h * scale):
            image = image.crop((0, 0, image.width, int(h * scale)))
        if scale != 1.0 or image.size != (w, h):
            image = image.resize((w, h), Image.LANCZOS)
        photo = ImageTk.PhotoImage(image, master=self.win)
        if self.item is None:
            self.item = self.canvas.create_image(0, 0, anchor="nw",
                                                 image=photo)
        else:
            self.canvas.itemconfigure(self.item, image=photo)
        self.photo = photo
        if self.pill is not None:
            self.canvas.tag_raise(self.pill_bg)
            self.canvas.tag_raise(self.pill)

    def _status(self, text):
        if self.canvas is None:
            return
        if not text:
            for item in (self.pill, self.pill_bg):
                if item is not None:
                    self.canvas.delete(item)
            self.pill = self.pill_bg = None
            return
        w, _h = self.geometry
        if self.pill is None:
            self.pill = self.canvas.create_text(
                w // 2, 18, anchor="n", text=text, fill="#f5f5f7",
                font=("Helvetica", 12))
            self.pill_bg = self.canvas.create_rectangle(
                0, 0, 0, 0, fill="#1c1c1e", outline="")
        else:
            self.canvas.itemconfigure(self.pill, text=text)
        box = self.canvas.bbox(self.pill)
        if box:
            self.canvas.coords(self.pill_bg, box[0] - 14, box[1] - 6,
                               box[2] + 14, box[3] + 6)
        self.canvas.tag_raise(self.pill_bg)
        self.canvas.tag_raise(self.pill)

    def _watch_key(self, session):
        """Stays up while any key of the shortcut is held; notes when X
        itself has come up, so a second X is told from auto-repeat."""
        if session != self.session or self.sticky:
            return
        if self.win is None and not self.opening:
            return
        key = keystate.is_down(self.spec)
        mods = keystate.modifiers_down(self.spec)
        if key is None or mods is None:
            # Cannot tell when the keys come up: leave it up until Esc,
            # a click or the shortcut again.
            self._make_sticky()
            return
        # Let go of X: it closes - at once if Ctrl and Alt are let go too,
        # otherwise after LOCK_GRACE, the time allowed to tap X again with
        # them still held, which keeps the view (press -> _make_sticky).
        if not key:
            if not self.key_released:
                self.key_released = True
                self.released_at = time.monotonic()
            if not mods or time.monotonic() - self.released_at >= LOCK_GRACE:
                self.close()
                return
        self.root.after(POLL_MS, lambda: self._watch_key(session))

    def _make_sticky(self):
        self.sticky = True
        try:
            self.win.focus_force()
        except Exception:
            pass

    def _click(self):
        if self.sticky:
            self.close()

    def close(self):
        self.session += 1
        self.opening = False
        self.pending = None
        self.closed_at = time.monotonic()
        previous, self.previous = self.previous, None
        win, self.win = self.win, None
        self.canvas = self.photo = self.item = None
        self.pill = self.pill_bg = None
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass
            _give_back(previous)
        self._show_main()

    def recently_active(self, seconds=1.5):
        """Open now, or closed a moment ago. macOS can take bringing Squint
        forward for a click on its Dock icon and ask for the main window;
        while hold-to-see is up, or just after, that request is not one."""
        if self.win is not None or self.opening:
            return True
        return time.monotonic() - self.closed_at < seconds

    def frame(self, payload):
        """A newer picture from the worker, on the Tk thread."""
        session, image, scale, status = payload
        if session != self.session:
            return
        if self.win is None:
            if self.opening:
                # Arrived before the window: keep the newest picture, and
                # the newest status with it.
                old = self.pending
                if image is None and old is not None:
                    payload = (session, old[1], scale, status)
                self.pending = payload
            return
        if isinstance(image, list):
            self._draw_blocks(image, scale)
        elif image is not None:
            self._show_image(image, scale)
        self._status(status)

    def _draw_blocks(self, blocks, scale):
        """The translation as canvas items over the frozen screen, as the
        snip's overlay draws it: the system draws canvas text at the
        display's real resolution, where a picture of text is one image
        pixel to a point and arrives soft on a Retina screen."""
        canvas = self.canvas
        canvas.delete("tx")
        scale = scale or 1.0
        self._patches = []

        def at(value):
            return int(round(value / scale))

        def hexed(rgb):
            return "#%02x%02x%02x" % tuple(int(c) for c in rgb[:3])
        for block in blocks:
            turned = overlay.turned_parts(block)
            if turned is not None:
                # Text at an angle: a cover the shape of the line.
                canvas.create_polygon(
                    *[at(v) for point in turned[0] for v in point],
                    fill=hexed(block["bg"]), outline="", tags="tx")
                continue
            x0, y0, x1, y1 = block["cover"]
            patch = block.get("patch")
            if patch is not None:
                photo = overlay.patch_photo(patch, scale, canvas)
                if photo is not None:
                    self._patches.append(photo)
                    canvas.create_image(at(max(0, x0)), at(max(0, y0)),
                                        anchor="nw", image=photo, tags="tx")
                    continue
            canvas.create_rectangle(at(x0), at(y0), at(x1), at(y1),
                                    fill=hexed(block["bg"]), outline="",
                                    tags="tx")
        family = overlay.tk_family(
            blocks[0].get("kind", "default") if blocks else "default",
            canvas)
        for block in blocks:
            size = max(1, int(round(block["size"] / scale)))
            font = (family, -size) if family else ("", -size)
            colour = hexed(block["fg"])
            turned = overlay.turned_parts(block)
            if turned is not None:
                try:
                    canvas.create_text(at(turned[1][0]), at(turned[1][1]),
                                       text=turned[3], angle=turned[2],
                                       anchor="center", font=font,
                                       fill=colour, tags="tx")
                except Exception:
                    pass
                continue
            ty = block["y"]
            right = block.get("rtl") and block.get("right")
            for row in block["rows"]:
                canvas.create_text(at(right if right else block["x"]),
                                   at(ty), text=row,
                                   anchor="ne" if right else "nw",
                                   fill=colour, font=font, tags="tx")
                ty += block["leading"]
        if self.pill is not None:
            canvas.tag_raise(self.pill_bg)
            canvas.tag_raise(self.pill)

    # Worker thread --------------------------------------------------------
    def _post(self, session, image, scale, status):
        self.controller.queue.put(("xray_frame",
                                   (session, image, scale, status)))

    def _work(self, session, shot):
        """Exactly a snip of the page in front, done for you.

        The snip is the part that reads, translates and lays out well, so
        hold-to-see does not have its own way of doing any of it. It
        chooses the area a person would have dragged - the page or
        document of the window in front, not its tabs or toolbars - and
        then does precisely what a snip of that area does: one read, one
        translation of the whole area with its paragraphs grouped the same
        way, the same layout at the same sizes. Everything that tried to be
        cleverer than that (batches, reading only part, its own sizing)
        made it worse than the snip."""
        image, scale = shot["image"], shot["scale"]
        target = CFG["target_lang"]
        source = ""
        try:
            from .langs import code_for_name
            chosen = str(CFG.get("source_lang_name", "") or "")
            if chosen and not chosen.lower().startswith("detect"):
                source = code_for_name(chosen) or ""
        except Exception:
            source = ""
        try:
            started = time.time()
            box = snip_area(shot, image.size)
            crop = image.crop(box)
            key = ("page", target, source, memory_tag()[0],
                   _fingerprint(crop))
            blocks = _cache_get(key)
            if blocks is None:
                blocks = _wait_prepared(key)
                if blocks is not None:
                    _log("used the page prepared ahead")
            read_ms = 0.0
            lines = []
            if blocks is None:
                # Carried on to the end even if the key is let go first:
                # the page is then ready the next time (see _cache_put).
                blocks, lines, read_ms = self._compute(
                    shot, crop, box, target, source,
                    lambda text: self._post(session, None, scale, text),
                    partial=lambda part: self._post(
                        session, part, scale, "Translating…"))
                if blocks is None:
                    return
            if session != self.session:
                _log("let go before it was ready: %d lines, read %.0fms, "
                     "ready after %.0fms, via %s - kept for next time"
                     % (len(lines), read_ms, 1000 * (time.time() - started),
                        CFG.get("last_backend", "") or "?"))
                return
            self._post(session, blocks, scale, "")
            _log("%s, read %.0fms, total %.0fms, via %s, area %s, "
                 "content: %s"
                 % ("%d lines" % len(lines) if lines else
                    "unchanged page, shown again", read_ms,
                    1000 * (time.time() - started),
                    CFG.get("last_backend", "") or "?", box,
                    shot.get("area_how")))
            try:
                from . import budget
                _log("budget: " + budget.line(
                    read_ms if lines else None, None,
                    1000 * (time.time() - started)))
            except Exception:
                pass
        except Cancelled:
            _log("stopped translating")
        except Exception:
            _log(traceback.format_exc())
            self._post(session, None, scale, "Could not translate this screen")

    def _compute(self, shot, crop, box, target, source, status,
                 partial=None):
        """Read, translate and lay out `crop` exactly as a snip of it would
        be; the blocks are kept (_cache_put) for the page as it is now.
        (blocks, lines, read_ms); blocks None when there is no text."""
        scale = shot["scale"]
        started = time.time()
        reused = None
        try:
            from . import preread
            if preread.READER is not None:
                reused = preread.READER.lines_for(
                    crop, box, shot["left"], shot["top"],
                    wait=preread.EARLY_WAIT, strict=False)
        except Exception:
            reused = None
        if reused is not None:
            lines = reused[0]
            _log("used %d lines already read" % len(lines))
        else:
            lines, _lang = ocr.image_to_lines(crop, source=source)
            if ocr.skipped_slow():
                # Preparing in the background (ocr.quick_only): not with a
                # reading that needed the slow reader - nothing is
                # translated from it.
                raise Cancelled("the page needs the slow reader")
        read_ms = 1000 * (time.time() - started)
        if not lines:
            status("No text here")
            return None, [], read_ms
        status("Translating…")
        floor = self._floor_for(crop.width / (scale or 1.0), shot)

        def shown(part, _tall):
            if partial is not None:
                partial([_moved(b, box[0], box[1], crop.size) for b in part])
        _texts, laid, _tall = overlay.progressive(
            crop, lines, translator, target, source or "auto",
            int(round(floor * scale)),
            shown=shown if partial is not None else None)
        blocks = [_moved(b, box[0], box[1], crop.size) for b in laid]
        _cache_put(("page", target, source, memory_tag()[0],
                    _fingerprint(crop)), blocks)
        return blocks, lines, read_ms

    def prepare(self):
        """Read and translate the page in front now, with nothing shown and
        on this computer only, so that holding the key for it - or snipping
        part of it - is quick. Called when a snip is dismissed without a
        box being drawn: the key press already began reading this page."""
        try:
            from . import offline_model
            if not offline_model.ready():
                return False
            shot = self._capture()
        except Exception:
            _log("prepare: %s" % traceback.format_exc()[-300:])
            return False
        if shot is None:
            return False
        prep = getattr(self, "prep_state", None)
        if prep is not None and not prep["done"].is_set():
            return False                 # one at a time
        self.prep_state = {
            "area": (shot["left"], shot["top"], shot["width"],
                     shot["height"]),
            "done": threading.Event(),
            "stop": threading.Event()}
        threading.Thread(target=self._prepare,
                         args=(shot, self.prep_state["done"]),
                         daemon=True).start()
        return True

    def _prepare(self, shot, finished=None):
        try:
            self._prepare_page(shot)
        finally:
            if finished is not None:
                finished.set()

    def _prepare_page(self, shot):
        target = CFG["target_lang"]
        source = ""
        try:
            from .langs import code_for_name
            chosen = str(CFG.get("source_lang_name", "") or "")
            if chosen and not chosen.lower().startswith("detect"):
                source = code_for_name(chosen) or ""
        except Exception:
            source = ""
        set_background(True)
        stop = getattr(self, "prep_state", {}).get("stop")
        set_stop(stop)
        key = None
        try:
            started = time.time()
            box = snip_area(shot, shot["image"].size)
            crop = shot["image"].crop(box)
            key = ("page", target, source, memory_tag()[0],
                   _fingerprint(crop))
            if _cache_get(key) is not None:
                return
            with _preparing_lock:
                if key in _preparing:
                    return
                _preparing[key] = threading.Event()
            # Windows' reader only, as the read-ahead: a page that needs
            # the slow one is not prepared (it took 86 s once, and the
            # translating after it 33 s of the graphics chip).
            with ocr.quick_only():
                blocks, lines, read_ms = self._compute(
                    shot, crop, box, target, source, lambda _text: None)
            _log("prepared ahead: %d lines, read %.0fms, total %.0fms"
                 % (len(lines), read_ms, 1000 * (time.time() - started)))
        except Cancelled as exc:
            _log("prepare stopped: %s" % exc)
        except Exception:
            _log("prepare: %s" % traceback.format_exc()[-400:])
        finally:
            set_background(False)
            set_stop(None)
            if key is not None:
                with _preparing_lock:
                    done = _preparing.pop(key, None)
                if done is not None:
                    done.set()

    def _floor_for(self, width_points, shot):
        """The snip's own rule for the smallest text size, from how much of
        the screen the area covers (Controller._do_snip)."""
        points = max(1, width_points)
        try:
            percent = platform_util.monitor_scaling(shot["left"], shot["top"])
            if percent:
                points = max(1, points * 100.0 / percent)
        except Exception:
            pass
        _floor_px, floor = overlay.size_policy(points)
        return floor

    def _floor(self, shot):
        points = max(1, shot["width"])
        try:
            percent = platform_util.monitor_scaling(shot["left"], shot["top"])
            if percent:
                points = max(1, points * 100.0 / percent)
        except Exception:
            pass
        _floor_px, floor = overlay.size_policy(points)
        return int(floor)
