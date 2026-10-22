"""Screenshots: a region, or a long page scrolled and stitched; and copying
the text out of a region.

The region picker is Squint's own snip overlay, so selecting looks and
behaves exactly like a snip does, on every monitor."""
import os
import time

from . import common

try:
    from PIL import Image
except Exception:                          # pragma: no cover
    Image = None


def pick_region(ctrl):
    """(image, (left, top, width, height) in screen pixels) or (None, None)."""
    from .. import snip
    picker = snip.SnipOverlay(ctrl.root)
    image = picker.select()
    if image is None:
        return None, None
    scale = getattr(picker, "scale_used", 1.0) or 1.0
    left = int(round(picker.origin[0] * scale))
    top = int(round(picker.origin[1] * scale))
    return image, (left, top, image.width, image.height)


def save_picture(ctrl, image, kind="Screenshot", note=""):
    path = common.unique(os.path.join(
        common.pictures_dir(), "%s %s.png" % (kind, common.stamp())))
    image.save(path)
    copied = False
    try:
        copied = common.image_to_clipboard(image)
    except Exception as exc:               # noqa: BLE001
        common.log("clipboard: %r" % exc)
    common.tell(ctrl, "%s saved%s.%s" % (kind, " and copied" if copied else "",
                                         ("\n" + note) if note else ""), path)
    return path


def region(ctrl, **_):
    image, _box = pick_region(ctrl)
    if image is not None:
        save_picture(ctrl, image)


def copy_text(ctrl, **_):
    image, _box = pick_region(ctrl)
    if image is None:
        return

    def work():
        from .. import ocr
        got = ocr.image_to_text(image)
        return got[0] if isinstance(got, tuple) else got

    def done(text):
        text = (text or "").strip()
        if not text:
            common.tell(ctrl, "No text found in that area.")
            return
        from .. import clipboard
        clipboard.set_text(ctrl.root, text)
        n = len(text.splitlines())
        common.tell(ctrl, "Copied %d line%s of text." % (n, "" if n == 1
                                                          else "s"))

    common.in_background(ctrl, work, done, "Copying the text")


# -- scrolling capture -------------------------------------------------

def _rows(image):
    """One small signature per row: enough to recognise the same line of a
    page when it has moved, cheap enough to compare thousands of them."""
    small = image.convert("L").resize((48, image.height))
    data = small.tobytes()
    return [bytes(b >> 4 for b in data[i * 48:(i + 1) * 48])
            for i in range(image.height)]


def _busy(sig):
    return max(sig) - min(sig) >= 2


def scroll_offset(prev, new):
    """How far the page moved up between two frames (rows), 0 for not at
    all, None when the frames do not overlap.

    Judged on rows with something in them: blank rows match anywhere and
    prove nothing. A header or toolbar that stays put while the page
    scrolls under it does not match at the right offset, so up to half of
    the overlap may disagree and the offset still counts."""
    h = len(new)
    if prev == new:
        return 0
    where = {}
    for i, sig in enumerate(prev):
        if _busy(sig):
            where.setdefault(sig, []).append(i)
    busy_new = [r for r in range(h) if _busy(new[r])]
    anchors = busy_new[:40]
    votes = {}
    for r in anchors:
        for p in where.get(new[r], ()):
            s = p - r
            if 0 < s < h - 8:
                votes[s] = votes.get(s, 0) + 1
    best = None
    for s, _v in sorted(votes.items(), key=lambda kv: -kv[1])[:8]:
        rows = [k for k in busy_new if k < h - s]
        if len(rows) < 6:
            continue
        same = sum(1 for k in rows if new[k] == prev[k + s])
        score = same / float(len(rows))
        if score >= 0.5 and (best is None or score > best[1]):
            best = (s, score)
    return best[0] if best else None


def stitch(frames, report=None):
    """One tall picture from frames of a page scrolled downwards.
    `report` (a list), when given, gets how many frames were used."""
    if not frames:
        return None
    pieces = [frames[0]]
    prev_sig = _rows(frames[0])
    for frame in frames[1:]:
        sig = _rows(frame)
        s = scroll_offset(prev_sig, sig)
        if not s:
            continue
        pieces.append(frame.crop((0, frame.height - s, frame.width,
                                  frame.height)))
        prev_sig = sig
    if report is not None:
        report.append(len(pieces))
    height = sum(p.height for p in pieces)
    out = Image.new("RGB", (frames[0].width, height), "white")
    y = 0
    for p in pieces:
        out.paste(p, (0, y))
        y += p.height
    return out


class Outline:
    """A thin frame around the area being captured, kept out of the
    capture itself."""

    def __init__(self, root, box, colour="#F05252"):
        import tkinter as tk
        left, top, w, h = box
        self.wins = []
        t = 2
        for x, y, ww, hh in ((left - t, top - t, w + 2 * t, t),
                             (left - t, top + h, w + 2 * t, t),
                             (left - t, top, t, h),
                             (left + w, top, t, h)):
            win = tk.Toplevel(root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg=colour)
            win.geometry("%dx%d+%d+%d" % (max(ww, 1), max(hh, 1), x, y))
            exclude_from_capture(win)
            self.wins.append(win)

    def close(self):
        for w in self.wins:
            try:
                w.destroy()
            except Exception:
                pass


def exclude_from_capture(win):
    """Windows 10 2004 and later can leave a window out of screenshots."""
    if not common.IS_WINDOWS:
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = int(win.wm_frame(), 16)
        ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11)
    except Exception:
        pass


def scrolling(ctrl, **_):
    image, box = pick_region(ctrl)
    if image is None:
        return
    import mss
    grabber = mss.mss()
    left, top, w, h = box
    area = {"left": left, "top": top, "width": w, "height": h}
    frames = [image]
    state = {"running": True, "last": time.time()}
    outline = Outline(ctrl.root, box)

    def grab():
        if not state["running"]:
            return
        try:
            raw = grabber.grab(area)
            frame = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            if frame.tobytes() != frames[-1].tobytes():
                frames.append(frame)
        except Exception as exc:           # noqa: BLE001
            common.log("scroll grab: %r" % exc)
        if len(frames) > 400:
            bar.stop()
            return
        ctrl.root.after(220, grab)

    used = []

    def finish():
        state["running"] = False
        outline.close()
        grab_last()
        common.in_background(ctrl, lambda: stitch(frames, used), done,
                             "Scrolling capture")

    def grab_last():
        try:
            raw = grabber.grab(area)
            frames.append(Image.frombytes("RGB", raw.size, raw.bgra, "raw",
                                          "BGRX"))
        except Exception:
            pass

    def done(picture):
        if picture is None:
            return
        note = ""
        if used and used[0] <= 1:
            note = ("The page did not seem to move, so only what was visible "
                    "is in it. Scroll with the mouse wheel inside the red "
                    "box before pressing Enter.")
        save_picture(ctrl, picture, "Scrolling capture", note)

    def cancel():
        state["running"] = False
        outline.close()

    bar = common.StopBar(ctrl, "Scroll down inside the red box, then "
                         "press Enter", finish, cancel, avoid=box)
    exclude_from_capture(bar.win)
    ctrl.radial_recording = bar
    ctrl.root.after(300, grab)
