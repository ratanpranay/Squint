"""Pictures into Tk without Pillow's Tk bridge, when that bridge fails.

Pillow hands a picture to Tk through a small helper (_imagingtk) that finds
Tcl and Tk's functions inside the running program. The Mac app's Tk 8.6 is
built into Python's _tkinter module rather than shipped as its own library,
and the helper cannot find the functions there: every picture failed with
"bad argument type for built-in operation" and Squint could not start.

This keeps Pillow's fast path wherever it works and, the first time it
fails, switches for good to giving Tk the picture as PPM or PNG data, which
any Tk reads by itself. Slower for large pictures, but only where the fast path
does not exist.
"""
import base64
import io

_state = {"installed": False, "fallback": False}


def _encode(im):
    """(data, format). PPM, which costs nothing to write, for pictures
    without transparency (screenshots); PNG for the rest."""
    if im.mode in ("RGB", "L"):
        fmt, kind = "PPM", "ppm"
    else:
        if im.mode not in ("RGBA", "LA"):
            im = im.convert("RGBA")
        fmt, kind = "PNG", "png"
    buf = io.BytesIO()
    if fmt == "PNG":
        im.save(buf, format=fmt, compress_level=1)
        return base64.b64encode(buf.getvalue()).decode("ascii"), kind
    # Tk 8.6 reads PPM data only as raw bytes, not base64.
    im.save(buf, format=fmt)
    return buf.getvalue(), kind


def install():
    """Wrap ImageTk.PhotoImage.paste once. Safe to call more than once."""
    if _state["installed"]:
        return
    try:
        from PIL import ImageTk
    except Exception:
        return
    original = ImageTk.PhotoImage.paste

    def paste(self, im, *args, **kwargs):
        if not _state["fallback"]:
            try:
                return original(self, im, *args, **kwargs)
            except Exception as exc:
                _state["fallback"] = True
                try:
                    from .main import log
                    log("images     : Tk bridge unavailable (%s); using PPM/PNG"
                        % (str(exc)[:80] or type(exc).__name__))
                except Exception:
                    pass
        photo = getattr(self, "_PhotoImage__photo")
        data, kind = _encode(im)
        photo.configure(data=data, format=kind)

    ImageTk.PhotoImage.paste = paste
    _state["installed"] = True
