"""Windows window chrome: translucency, rounded corners, dark titlebar.

Not exposed by Tk, so it goes through DWM. Every call is optional and
guarded: on an older build, or a non-Windows machine, the window simply
stays opaque and square instead of failing.

*** Why there is no acrylic blur here ***

DWM can blur behind a window (SetWindowCompositionAttribute with
ACCENT_ENABLE_ACRYLICBLURBEHIND), and it is tempting, because that is the
real frosted-glass effect the Windows shell uses. It cannot be used with
this app.

Enabling it switches the window to per-pixel alpha compositing. Tk renders
through GDI, and GDI writes pixels without ever setting the alpha byte — it
stays at zero. DWM then reads every pixel Tk painted as fully transparent,
and the window renders completely empty: a titlebar (drawn by DWM) around a
hole. The same applies to the Mica/Acrylic system backdrop.

Toolkits that get acrylic right — WPF, WinUI, Electron — composite through
DirectComposition and control the alpha channel. A GDI toolkit cannot.

So translucency here is uniform window opacity, which is a layered-window
feature (LWA_ALPHA) that composites the finished GDI surface and is safe.
It is a softer effect than blur, and it is one that actually renders.
"""
import ctypes
import ctypes.wintypes as wt
import sys

IS_WINDOWS = sys.platform == "win32"

# DwmSetWindowAttribute
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_SYSTEMBACKDROP_TYPE = 38

DWMWCP_ROUND = 2

# Opacity floor. Anything lower makes text hard to read against a busy
# desktop, and a window that vanishes is worse than one that is merely solid.
MIN_ALPHA = 0.80


def hwnd_for(window):
    """Top-level HWND for a Tk widget (frame, not the child Tk window)."""
    try:
        window.update_idletasks()
        return ctypes.windll.user32.GetParent(window.winfo_id()) \
            or window.winfo_id()
    except Exception:
        return None


def _dwm_set(hwnd, attribute, value):
    try:
        data = ctypes.c_int(value)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wt.HWND(hwnd), ctypes.c_uint(attribute), ctypes.byref(data),
            ctypes.sizeof(data))
        return result == 0
    except Exception:
        return False


def dark_titlebar(window, dark=True):
    if not IS_WINDOWS:
        return False
    hwnd = hwnd_for(window)
    if not hwnd:
        return False
    # Attribute 20 on current builds; 19 on early Windows 10 20H1.
    return (_dwm_set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, int(dark))
            or _dwm_set(hwnd, 19, int(dark)))


def round_corners(window, radius="round"):
    """Windows 11 rounded window corners."""
    if not IS_WINDOWS:
        return False
    hwnd = hwnd_for(window)
    if not hwnd:
        return False
    return _dwm_set(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                    DWMWCP_ROUND if radius == "round" else 3)


def round_region(window, radius=16):
    """Clip the window itself to a rounded rectangle.

    Borderless popups get no titlebar, so DWM will not round them. Setting a
    window region does it properly: the corners are cut from the window
    shape, so whatever is behind shows through — no transparency colour, and
    none of the magenta fringing that comes with one.
    """
    if not IS_WINDOWS:
        return False
    hwnd = hwnd_for(window)
    if not hwnd:
        return False
    try:
        window.update_idletasks()
        w = window.winfo_width()
        h = window.winfo_height()
        if w < 2 or h < 2:
            return False
        gdi = ctypes.windll.gdi32
        region = gdi.CreateRoundRectRgn(0, 0, w + 1, h + 1,
                                        radius * 2, radius * 2)
        if not region:
            return False
        ctypes.windll.user32.SetWindowRgn(wt.HWND(hwnd), region, True)
        return True
    except Exception:
        return False


def set_opacity(window, value):
    """Uniform window opacity, clamped so the window can never disappear."""
    try:
        opacity = max(MIN_ALPHA, min(1.0, float(value)))
        window.attributes("-alpha", opacity)
        return opacity
    except Exception:
        return None


def apply_window_chrome(window, palette, translucent=True):
    """Everything a top-level window wants, best-effort.

    Returns a dict of what actually took effect.
    """
    applied = {"dark_titlebar": False, "rounded": False, "alpha": None}
    applied["dark_titlebar"] = dark_titlebar(window, palette["name"] == "dark")
    applied["rounded"] = round_corners(window)
    applied["alpha"] = set_opacity(window,
                                   palette["alpha"] if translucent else 1.0)
    return applied
