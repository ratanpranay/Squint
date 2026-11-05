"""Selfie check: a small drop-down under the laptop's camera.

The ring closes and a white card slides down from the top centre of the
screen that has the camera in it - the laptop's own screen, never a second
monitor (a computer without one uses its main screen). Looking at the
preview there means looking at the lens, so it shows how you look on a
call. The camera stops the moment it closes.
"""
import os
import struct
import threading
import time
import tkinter as tk

from . import common, icons

KEY = "#010203"                         # see-through on Windows


# -- which screen has the camera ------------------------------------------

def _mac_screen():
    """(left, top, width, height, menu bar) of the Mac's built-in screen, in
    points with the origin top-left, or of the main screen without one."""
    from AppKit import NSScreen
    import Quartz
    screens = list(NSScreen.screens())
    main_h = screens[0].frame().size.height
    chosen = screens[0]
    for scr in screens:
        number = scr.deviceDescription().get("NSScreenNumber")
        try:
            if number is not None and Quartz.CGDisplayIsBuiltin(int(number)):
                chosen = scr
                break
        except Exception:
            pass
    f, v = chosen.frame(), chosen.visibleFrame()
    left, width, height = f.origin.x, f.size.width, f.size.height
    top = main_h - (f.origin.y + height)
    bar = (f.origin.y + height) - (v.origin.y + v.size.height)
    return int(left), int(top), int(width), int(height), int(max(0, bar))


# DISPLAYCONFIG_OUTPUT_TECHNOLOGY values meaning "the laptop's own panel".
_INTERNAL = (0x80000000, 6, 11, 13)     # internal, LVDS, eDP, embedded UDI


def _internal_panel(paths, n_paths, modes, n_modes):
    """From QueryDisplayConfig's raw arrays (72-byte paths, 64-byte
    modes): the built-in panel's (left, top, width, height, 0), or None."""
    for i in range(n_paths):
        p = paths[i * 72:(i + 1) * 72]
        source_mode = struct.unpack_from("<I", p, 12)[0]
        technology = struct.unpack_from("<I", p, 36)[0]
        if technology not in _INTERNAL or source_mode >= n_modes:
            continue
        m = modes[source_mode * 64:(source_mode + 1) * 64]
        if struct.unpack_from("<I", m, 0)[0] != 1:      # a SOURCE mode
            continue
        w, h = struct.unpack_from("<II", m, 16)
        x, y = struct.unpack_from("<ii", m, 28)
        return (x, y, w, h, 0)
    return None


def _windows_screen():
    """(left, top, width, height, 0) of the laptop's own panel, from
    QueryDisplayConfig; the main screen without one."""
    import ctypes
    user32 = ctypes.windll.user32
    flags = 2                            # QDC_ONLY_ACTIVE_PATHS
    n_paths, n_modes = ctypes.c_uint32(), ctypes.c_uint32()
    found = None
    if user32.GetDisplayConfigBufferSizes(flags, ctypes.byref(n_paths),
                                          ctypes.byref(n_modes)) == 0:
        paths = ctypes.create_string_buffer(72 * n_paths.value)
        modes = ctypes.create_string_buffer(64 * n_modes.value)
        if user32.QueryDisplayConfig(flags, ctypes.byref(n_paths), paths,
                                     ctypes.byref(n_modes), modes,
                                     None) == 0:
            found = _internal_panel(paths.raw, n_paths.value, modes.raw,
                                    n_modes.value)
    if found:
        return found
    raise LookupError("no built-in screen")


def camera_screen():
    """Where the drop-down goes: the screen with the camera."""
    try:
        if common.IS_MAC:
            return _mac_screen()
        if common.IS_WINDOWS:
            return _windows_screen()
    except Exception as exc:              # noqa: BLE001 - main screen then
        common.log("selfie screen: %r" % exc)
    try:
        from .. import platform_util
        for (x, y, w, h) in platform_util.displays():
            if x <= 0 < x + w and y <= 0 < y + h:
                return x, y, w, h, 0
    except Exception:
        pass
    return 0, 0, 1440, 900, 0


# -- the camera -----------------------------------------------------------

def _grab(cv2, state):
    cam = None
    try:
        if common.IS_WINDOWS:
            backend = cv2.CAP_DSHOW
        elif common.IS_MAC:
            backend = getattr(cv2, "CAP_AVFOUNDATION", 0)
        else:
            backend = 0
        cam = cv2.VideoCapture(0, backend)
        tries = 0
        # On a Mac the first try only asks for permission; keep trying.
        while not cam.isOpened() and common.IS_MAC and tries < 30 \
                and state["run"]:
            state["soft"] = ("Allow camera access when macOS asks, then "
                             "wait a moment.")
            time.sleep(0.5)
            cam.release()
            cam = cv2.VideoCapture(0, backend)
            tries += 1
        state["soft"] = None
        if not cam.isOpened():
            state["error"] = ("No camera found, or another app is using it."
                              + (" Allow Squint under System Settings › "
                                 "Privacy & Security › Camera."
                                 if common.IS_MAC else ""))
            return
        cam.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        while state["run"]:
            ok, frame = cam.read()
            if not ok:
                state["error"] = "The camera stopped sending pictures."
                return
            state["frame"] = cv2.cvtColor(cv2.flip(frame, 1),
                                          cv2.COLOR_BGR2RGB)
    except Exception as exc:              # noqa: BLE001
        state["error"] = str(exc)
    finally:
        if cam is not None:
            cam.release()


def _round(picture, size):
    """The middle of the (mirrored) frame as a smooth circle."""
    from PIL import Image, ImageDraw
    im = Image.fromarray(picture)
    w, h = im.size
    side = min(w, h)
    im = im.crop(((w - side) // 2, (h - side) // 2,
                  (w + side) // 2, (h + side) // 2)).resize((size, size))
    mask = Image.new("L", (size * 3, size * 3), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 3 - 1, size * 3 - 1),
                                 fill=255)
    out = im.convert("RGBA")
    out.putalpha(mask.resize((size, size), Image.LANCZOS))
    return out


# -- the drop-down --------------------------------------------------------

class SelfieDrop:
    current = None

    def __init__(self, ctrl, cv2):
        if SelfieDrop.current is not None:
            SelfieDrop.current.close()
        SelfieDrop.current = self
        self.ctrl = ctrl
        self.closed = False
        self.state = {"run": True, "frame": None, "error": None,
                      "soft": None}
        left, top, width, _height, bar = camera_screen()
        try:
            from .. import platform_util
            s = (platform_util.monitor_scaling(left + width // 2,
                                               top + 10) or 100) / 100.0
        except Exception:
            s = 1.0
        self.s = s = max(1.0, s) if not common.IS_MAC else 1.0
        common.apply_theme(True)
        self.fill = "#FBFBFD"
        self.size = int(210 * s)
        w = int(300 * s)
        pad = int(18 * s)
        h = int(bar + pad + self.size + 92 * s)
        self.w, self.h = w, h
        self.x = int(left + (width - w) / 2)
        self.top = int(top)

        win = self.win = tk.Toplevel(ctrl.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        bg = KEY
        if common.IS_WINDOWS:
            win.configure(bg=KEY)
            win.attributes("-transparentcolor", KEY)
        elif common.IS_MAC:
            try:
                win.attributes("-transparent", True)
                bg = "systemTransparent"
            except tk.TclError:
                bg = self.fill
            win.configure(bg=bg)
        else:
            bg = self.fill
        c = self.canvas = tk.Canvas(win, width=w, height=h, bg=bg,
                                    highlightthickness=0, bd=0)
        c.pack()
        self._card()
        cx = w / 2.0
        cy = bar + pad + self.size / 2.0
        r = self.size / 2.0
        # A thin ring around the picture, in the accent colour.
        c.create_oval(cx - r - 3 * s, cy - r - 3 * s, cx + r + 3 * s,
                      cy + r + 3 * s, outline=common.ACCENT,
                      width=max(1, int(2 * s)))
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#E9ECF1",
                      outline="")
        self.cam = c.create_image(cx, cy)
        self.status = c.create_text(cx, cy + r + 20 * s,
                                    text="Starting the camera…",
                                    fill=common.MUTED, font=self.f(12),
                                    width=w - 2 * pad, justify="center")
        y = cy + r + 52 * s
        save = self._button("Save photo", self.save, primary=True)
        close = self._button("Close", self.close)
        sw, cw = int(save.cget("width")), int(close.cget("width"))
        gap = 8 * s
        x0 = cx - (sw + gap + cw) / 2.0
        c.create_window(x0, y, window=save, anchor="w")
        c.create_window(x0 + sw + gap, y, window=close, anchor="w")

        win.geometry("%dx%d+%d+%d" % (w, h, self.x, self.top - h))
        threading.Thread(target=_grab, args=(cv2, self.state),
                         daemon=True, name="selfie").start()
        self._slide(0)
        win.after(40, self._show)
        win.after(400, self._watch)
        if common.IS_WINDOWS:
            win.bind("<Escape>", lambda _e: self.close())
            win.after(30, self._focus)

    def f(self, size, bold=False):
        return (common.FONT, -int(round(size * self.s)),
                "bold" if bold else "normal")

    def _card(self):
        """White, square at the top (against the screen's edge), round at
        the bottom, with a hairline edge."""
        from PIL import Image, ImageDraw
        w, h, s = self.w, self.h, self.s
        k = 3
        img = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        rad = int(26 * s * k)
        d.rounded_rectangle((0, -rad, w * k - 1, h * k - 1), rad,
                            fill=(220, 223, 229, 255))
        d.rounded_rectangle((k, -rad, w * k - 1 - k, h * k - 1 - k),
                            rad - k, fill=(251, 251, 253, 255))
        img = img.resize((w, h), Image.LANCZOS)
        self._card_img = icons.to_tk(img, self.canvas, hard=True)
        # Plain shape underneath, in case pictures do not show.
        self.canvas.create_rectangle(2, 0, w - 2, h - 26 * s,
                                     fill=self.fill, outline="")
        self.canvas.create_oval(2, h - 52 * s, 52 * s, h - 2,
                                fill=self.fill, outline="")
        self.canvas.create_oval(w - 52 * s, h - 52 * s, w - 2, h - 2,
                                fill=self.fill, outline="")
        self.canvas.create_rectangle(26 * s, h - 30 * s, w - 26 * s, h - 2,
                                     fill=self.fill, outline="")
        self.canvas.create_image(0, 0, image=self._card_img, anchor="nw")

    def _button(self, text, command, primary=False):
        b = common.PillButton(self.canvas, text=text, command=command,
                              bg=common.ACCENT if primary else "#ECEEF2",
                              fg="#FFFFFF" if primary else "#1E2129",
                              font=self.f(13), padx=int(16 * self.s),
                              pady=int(6 * self.s))
        tk.Canvas.configure(b, bg=self.fill)
        b._draw()
        return b

    def _slide(self, step, steps=9):
        if self.closed:
            return
        t = min(1.0, step / float(steps))
        ease = 1 - (1 - t) ** 3
        y = int(self.top - self.h + self.h * ease)
        try:
            self.win.geometry("+%d+%d" % (self.x, y))
        except tk.TclError:
            return
        if step < steps:
            self.win.after(16, lambda: self._slide(step + 1, steps))

    def _focus(self):
        try:
            self.win.focus_force()
        except tk.TclError:
            pass

    def _show(self):
        if self.closed:
            return
        st = self.state
        c = self.canvas
        try:
            if st["error"]:
                c.itemconfigure(self.status, text=st["error"],
                                fill=common.ERROR)
                return
            if st["soft"] and st["frame"] is None:
                c.itemconfigure(self.status, text=st["soft"])
            if st["frame"] is not None:
                self._photo = icons.to_tk(_round(st["frame"], self.size),
                                          c)
                c.itemconfigure(self.cam, image=self._photo)
                if not getattr(self, "_live", False):
                    self._live = True
                    c.itemconfigure(self.status, fill=common.TEXT,
                                    text="This is how you look right now.")
        except tk.TclError:
            return
        self.win.after(40, self._show)

    def _pointer_inside(self):
        px, py = self.win.winfo_pointerxy()
        x, y = self.win.winfo_rootx(), self.win.winfo_rooty()
        return x <= px <= x + self.w and y <= py <= y + self.h

    def _mouse_down(self):
        try:
            if common.IS_WINDOWS:
                import ctypes
                return bool(ctypes.windll.user32.GetAsyncKeyState(1)
                            & 0x8000)
            if common.IS_MAC:
                from AppKit import NSEvent
                return bool(NSEvent.pressedMouseButtons() & 1)
        except Exception:
            pass
        return False

    def _watch(self):
        """Esc, or a click anywhere else, closes it."""
        if self.closed:
            return
        try:
            if common.key_down("esc") or (self._mouse_down()
                                          and not self._pointer_inside()):
                self.close()
                return
        except Exception:
            pass
        self.win.after(50, self._watch)

    def save(self):
        picture = self.state.get("frame")
        if picture is None:
            return
        from PIL import Image
        path = common.unique(os.path.join(common.pictures_dir(),
                                          "Selfie %s.png" % common.stamp()))
        Image.fromarray(picture).save(path)
        where = "Downloads/Squint/Screenshots" if common.IS_MAC \
            else "Downloads\\Squint\\Screenshots"
        self.canvas.itemconfigure(self.status, fill=common.GOOD,
                                  text="✓ Saved in %s" % where)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.state["run"] = False         # the camera turns off
        if SelfieDrop.current is self:
            SelfieDrop.current = None
        try:
            self.win.destroy()
        except Exception:
            pass
