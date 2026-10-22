"""The typefaces the app's own chrome is set in, carried with the app.

Why carry them at all. A design drawn in one face and shipped in
whatever the machine happens to have is not the same design: the rail
is a different width, the headline wraps a line earlier, and the
carefully chosen difference between a label and the word under it —
which was two steps of weight — is nothing, because the system face
has one weight and its bold. Windows' Segoe and macOS' SF are both
good faces and neither is this one, so the two platforms drift apart
in exactly the places a screenshot gets compared.

Why it is safe to. These are registered **for this process only** —
FR_PRIVATE on Windows, the process scope on macOS. Nothing is
installed, nothing is left behind when the app quits, and no other
program's font list changes. Both faces are under the SIL Open Font
License, which permits exactly this; the licences travel beside them.

**This is chrome only.** The one thing these fonts must never be asked
to draw is a translation. Plus Jakarta Sans covers Latin, its
extensions and Vietnamese — and not one character of Korean, Chinese,
Japanese, Arabic, Thai, Devanagari or Cyrillic. A face that has no
glyph does not fail; it draws a box. `overlay` already picks a face per
script for translated text and `theme.body_family` is what the
translation pane asks for: neither goes through here, and neither
should.

The same trap is set one step further in. The app can be run in a
language other than English, and the picker that offers that lists each
one in its own script — 한국어, 中文, Русский. Only English is offered
today, so nothing is wrong; a test holds the tripwire for the day
another is, because that list is chrome by every other measure and is
not chrome by this one.

Tk knows two weights, `normal` and `bold`, so five weights cannot be
one family. They are not: each weight past the regular carries its own
family name in its own name table — "Plus Jakarta Sans SemiBold" — which
is how every application that sets type in more than two weights
addresses them. The regular and the bold do share a family, so
`weight="bold"` on the base name lands on the 700 the way it should.

Whether the system agrees is another matter, and it does not always:
see the note beside `BASE_FAMILY`.
"""
import os
import sys

from . import config

#: Every weight the design uses, as (file, the family the system will
#: know it by). The family names are read off each font's own name
#: table — they are not ours to choose, and renaming them would be a
#: licence question as well as a lie.
FACES = (
    ("plus-jakarta-sans-400.ttf", "Plus Jakarta Sans"),
    ("plus-jakarta-sans-500.ttf", "Plus Jakarta Sans Medium"),
    ("plus-jakarta-sans-600.ttf", "Plus Jakarta Sans SemiBold"),
    ("plus-jakarta-sans-700.ttf", "Plus Jakarta Sans"),      # the bold of it
    ("plus-jakarta-sans-800.ttf", "Plus Jakarta Sans ExtraBold"),
    ("caveat-600.ttf", "Caveat SemiBold"),
)

#: A numeric weight, as a designer writes it, to the family and the Tk
#: weight that draw it. 700 is the one that is a style rather than a
#: family of its own.
BY_WEIGHT = {
    400: ("Plus Jakarta Sans", "normal"),
    500: ("Plus Jakarta Sans Medium", "normal"),
    600: ("Plus Jakarta Sans SemiBold", "normal"),
    700: ("Plus Jakarta Sans", "bold"),
    800: ("Plus Jakarta Sans ExtraBold", "normal"),
}

#: The family every weight of the interface face shares, and the one
#: name that is always there when any of them registered.
#:
#: Whether the other four exist is a question about the machine, not
#: about the files. Windows and macOS register a font under the family
#: in its own name table, so "Plus Jakarta Sans SemiBold" is a family
#: there. Fontconfig does not: it reads the same name table, decides the
#: weight is a *style* of one family, and reports four faces all called
#: "Plus Jakarta Sans". Ask it for the SemiBold by name and it has never
#: heard of it.
#:
#: Which is why `theme.ui_family` falls back to this and not to the
#: system stack. Losing a weight is a smaller loss than losing the
#: typeface, and the fallback that was there first lost the typeface —
#: the headline came out in the machine's default face while the word
#: beside it, one weight lighter, came out in the right one.
BASE_FAMILY = "Plus Jakarta Sans"

#: The handwritten face, most specific first, for the same reason.
SCRIPT_FAMILY = "Caveat SemiBold"
SCRIPT_FAMILIES = ("Caveat SemiBold", "Caveat")

_registered = None


def folder():
    """Where the files are, packaged or not."""
    for base in (config.resource_dir(), config.app_dir()):
        here = os.path.join(base, "assets", "fonts")
        if os.path.isdir(here):
            return here
    return os.path.join(config.app_dir(), "assets", "fonts")


def files():
    """The font files that are actually present, in FACES order."""
    where = folder()
    found = []
    for name, _family in FACES:
        path = os.path.join(where, name)
        if os.path.isfile(path):
            found.append(path)
    return found


def _register_windows(paths):
    """FR_PRIVATE: this process sees them, nothing else does, and
    nothing survives the process."""
    import ctypes
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    gdi.AddFontResourceExW.argtypes = (ctypes.c_wchar_p, ctypes.c_uint,
                                       ctypes.c_void_p)
    gdi.AddFontResourceExW.restype = ctypes.c_int
    FR_PRIVATE = 0x10
    done = []
    for path in paths:
        try:
            if gdi.AddFontResourceExW(path, FR_PRIVATE, None):
                done.append(path)
        except Exception:
            pass
    return done


def _register_mac(paths):
    """CoreText, process scope.

    Reached through ctypes rather than pyobjc on purpose: the CoreText
    bindings are a separate wheel from the AppKit ones the app already
    needs, and a machine that has one does not necessarily have the
    other. Every restype here is set explicitly — a CFURLRef returned
    into ctypes' default `int` is a pointer cut in half, which on a
    64-bit build is a crash rather than a failure to register.
    """
    import ctypes
    frameworks = "/System/Library/Frameworks"
    core = ctypes.cdll.LoadLibrary(
        frameworks + "/CoreFoundation.framework/CoreFoundation")
    text = ctypes.cdll.LoadLibrary(
        frameworks + "/ApplicationServices.framework/ApplicationServices")

    core.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
    core.CFURLCreateFromFileSystemRepresentation.argtypes = (
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool)
    core.CFRelease.argtypes = (ctypes.c_void_p,)
    core.CFRelease.restype = None
    text.CTFontManagerRegisterFontsForURL.restype = ctypes.c_bool
    text.CTFontManagerRegisterFontsForURL.argtypes = (
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p)
    SCOPE_PROCESS = 1

    done = []
    for path in paths:
        url = None
        try:
            raw = path.encode("utf-8")
            url = core.CFURLCreateFromFileSystemRepresentation(
                None, raw, len(raw), False)
            if not url:
                continue
            if text.CTFontManagerRegisterFontsForURL(url, SCOPE_PROCESS, None):
                done.append(path)
        except Exception:
            pass
        finally:
            if url:
                try:
                    core.CFRelease(url)
                except Exception:
                    pass
    return done


def register():
    """Make the bundled faces available to this process. Idempotent.

    Must run before the first Tk widget: Tk asks the system for the
    font list once and remembers the answer, so a face registered
    afterwards is one Tk will tell you it does not have.

    Never raises and never blocks the app. A machine where this does
    nothing — Linux, an old Windows, a locked-down Mac — gets the
    system face it would have had anyway, which is why every caller
    goes through `theme.ui_font` rather than naming a family.
    """
    global _registered
    if _registered is not None:
        return _registered
    _registered = set()
    paths = files()
    if not paths:
        return _registered
    try:
        if sys.platform == "win32":
            done = _register_windows(paths)
        elif sys.platform == "darwin":
            done = _register_mac(paths)
        else:
            done = []                      # X11 wants fontconfig, not us
    except Exception:
        done = []
    by_file = dict(FACES)
    for path in done:
        family = by_file.get(os.path.basename(path))
        if family:
            _registered.add(family)
    return _registered


def registered():
    """The families that took, without registering if nothing has yet."""
    return set(_registered or ())


def have(family, widget=None):
    """Whether Tk can actually draw with this family.

    Asked of Tk rather than of our own bookkeeping, because the two can
    disagree: registration reports success and the face still does not
    appear, and on a machine where the files were never shipped the
    system may have the face installed anyway.
    """
    if not family:
        return False
    try:
        import tkinter.font as tkfont
        return family.lower() in {name.lower()
                                  for name in tkfont.families(widget)}
    except Exception:
        return False
