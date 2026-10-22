"""Palette and type scale.

Colours follow Apple's system palette rather than Windows' — SF-style greys,
the iOS accent blues, and the same separator weights. Both schemes are defined
in full so switching is a swap, never a patch.
"""
import tkinter.font as tkfont

DARK = {
    "name": "dark",
    "window": "#1C1C1E",        # systemBackground
    "surface": "#2C2C2E",       # secondarySystemBackground (cards)
    "surface_hi": "#3A3A3C",    # raised / hover
    "field": "#2C2C2E",
    "field_on_card": "#3A3A3C",   # inputs sitting on a card need contrast
    "track": "#39393D",         # segmented + switch tracks
    "text": "#F5F5F7",
    "text_dim": "#98989D",      # secondaryLabel
    "text_faint": "#6E6E73",
    "separator": "#38383A",
    "accent": "#0A84FF",        # systemBlue (dark)
    "accent_hi": "#3D9BFF",
    "accent_text": "#FFFFFF",
    "on_accent_dim": "#D8E9FF",
    "success": "#30D158",
    "warning": "#FF9F0A",
    "danger": "#FF453A",
    "shadow": "#000000",
    "alpha": 0.94,
}

LIGHT = {
    "name": "light",
    "window": "#F2F2F7",        # systemGroupedBackground
    "surface": "#FFFFFF",
    "surface_hi": "#F5F5F7",
    "field": "#FFFFFF",
    "field_on_card": "#F2F2F7",
    "track": "#E4E4E9",
    "text": "#1D1D1F",
    "text_dim": "#6E6E73",
    "text_faint": "#8E8E93",
    "separator": "#D8D8DD",
    "accent": "#007AFF",        # systemBlue (light)
    "accent_hi": "#3395FF",
    "accent_text": "#FFFFFF",
    "on_accent_dim": "#E8F1FF",
    "success": "#28A745",
    "warning": "#B26B00",
    "danger": "#D70015",
    "shadow": "#9A9AA0",
    "alpha": 0.94,
}

# The real thing on macOS; Windows 11's Segoe UI Variable is its closest
# analogue and is used there so both platforms read as one design.
import sys as _sys

if _sys.platform == "darwin":
    _FAMILIES = ("SF Pro Text", "SF Pro", ".AppleSystemUIFont",
                 "Helvetica Neue", "Inter", "DejaVu Sans", "TkDefaultFont")
    _DISPLAY = ("SF Pro Display", "SF Pro", ".AppleSystemUIFont",
                "Helvetica Neue", "Inter", "DejaVu Sans", "TkDefaultFont")
else:
    _FAMILIES = ("Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI",
                 "Inter", "Helvetica Neue", "DejaVu Sans", "TkDefaultFont")
    _DISPLAY = ("Segoe UI Variable Display", "Segoe UI Variable", "Segoe UI",
                "Inter", "Helvetica Neue", "DejaVu Sans", "TkDefaultFont")

_cache = {}


def _pick(candidates, root=None):
    key = tuple(candidates)
    if key in _cache:
        return _cache[key]
    try:
        available = set(tkfont.families(root))
    except Exception:
        available = set()
    chosen = next((f for f in candidates if f in available), candidates[-1])
    _cache[key] = chosen
    return chosen


def body_family(root=None):
    return _pick(_FAMILIES, root)


def display_family(root=None):
    return _pick(_DISPLAY, root)


# Every text size in the app goes through font(), so one number here makes
# the whole interface bigger. It is set above 1 because the sizes were
# chosen against a normal display and read as small type on a Retina Mac,
# where the window is physically smaller than the pixel count suggests.
#: The kit's own type, against the design's. The design draws its body
#: text at fifteen of its own pixels; the kit asks for "size 10", and
#: this is what turns one into the other.
TEXT_SCALE = 1.45

#: The page's own scale, set by the window when it works out how big to
#: be — see MainWindow._fit_to_screen and ui_home.SCALE.
#:
#: The front page asks for exact sizes and bypasses all of this. Every
#: other part of the app — Settings, Support, the first-run pages — is
#: built out of the kit, and the kit sizes its own type. Left alone,
#: that type is the same number of pixels whatever size the window is,
#: which on a small window is a settings page in headline type and on a
#: large one is a settings page in fine print. One knob moves them
#: together.
PAGE_SCALE = 1.0


def scaled(size):
    """A size after the app-wide scale and the page's.

    A plain number of pixels. `text_size` below is what a font is
    actually given, and it is this negated — see the note there.
    """
    wanted = float(size) * TEXT_SCALE * PAGE_SCALE
    return max(10, int(round(wanted)))


def text_size(size):
    """The same size, as Tk wants to hear it for a font.

    Negative, and the sign is the whole point. A positive size in a Tk
    font is a size in *points*, which Tk multiplies by the display's
    DPI: ask for 15 on a 96-dpi display and you get twenty pixels of
    type. Negative is pixels, which is what every number in this app
    means and what the design is drawn in.

    The front page has always said so — it bypasses this and passes its
    own negative sizes. The kit did not, so everything built out of it
    came out a third larger on Windows than on a Mac, where a point and
    a pixel are the same thing. Settings in headline type, on one
    platform only, for that reason.
    """
    return -scaled(size)


def font(root=None, size=10, weight="normal", display=False):
    family = display_family(root) if display else body_family(root)
    return (family, text_size(size), weight)


# -- the app's own chrome -------------------------------------------------
#
# Everything above draws whatever the app was given, translations
# included, so it has to be a face the machine has for the script in
# hand. Everything below draws the app's own words — "Settings",
# "Snip & Translate", a version number — which are ours, are in English,
# and are the same on both platforms. That is the whole difference, and
# it is why the bundled faces are reachable only from here.
#
# Weight is a number rather than "normal" or "bold" because the design
# uses five of them and Tk knows two. `fonts` keeps the mapping; a
# machine where the faces did not register falls back to the system
# stack, where 600 and above become bold and the rest do not.
_ui_cache = {}


def _bundled(family, root):
    key = ("have", family)
    if key not in _ui_cache:
        try:
            from . import fonts as _fonts
            _ui_cache[key] = _fonts.have(family, root)
        except Exception:
            _ui_cache[key] = False
    return _ui_cache[key]


def ui_family(weight=400, root=None):
    """The family and Tk weight that draw this numeric weight.

    Three answers, in order, and the middle one is the one that matters.
    The exact face if this machine knows it by name; failing that the
    base family at the nearest of Tk's two weights, which is still the
    right typeface; and only if the typeface is not here at all, the
    system stack. See the note beside `fonts.BASE_FAMILY` for why the
    middle step exists.
    """
    try:
        from . import fonts as _fonts
        family, tk_weight = _fonts.BY_WEIGHT.get(
            int(weight), _fonts.BY_WEIGHT[400])
        base = _fonts.BASE_FAMILY
    except Exception:
        family, tk_weight, base = None, "normal", None
    heavy = "bold" if int(weight) >= 600 else "normal"
    if family and _bundled(family, root):
        return family, tk_weight
    if base and _bundled(base, root):
        return base, heavy
    return display_family(root), heavy


def _exact(size):
    """A size that means pixels, whatever the display's DPI.

    Tk reads a positive font size as POINTS and converts it with the
    screen's resolution — 44 becomes 59 pixels at the usual 96 dpi.
    Negative means pixels, exactly, which is what a design drawn in
    pixels is asking for. The whole front page came out a third too
    large for want of this minus sign, and uniformly so, which is why it
    looked like a scale I had chosen rather than a unit I had confused.
    """
    size = int(round(float(size)))
    if size == 0:
        return -6
    return -abs(size) if abs(size) >= 6 else -6


def ui_font(root=None, size=10, weight=400, scale=True):
    """A font for the app's own interface. Never for translated text.

    `scale=False` means the size given is already the size wanted. The
    app-wide scale above exists because the *old* sizes were chosen too
    small and read as fine print on a Retina Mac; the front page is
    drawn to a design whose sizes are generous to begin with, and
    putting a second multiplier on top of those makes a 44-point
    headline into a 55-point one that runs off the page.
    """
    family, tk_weight = ui_family(weight, root)
    return (family, text_size(size) if scale else _exact(size), tk_weight)


#: Cap height as a share of the ascent, for this interface face. The one
#: number in the next function that had to be measured rather than asked
#: for: Tk reports a font's ascent and descent and has no idea where the
#: capitals stop, and that is the line the eye centres on.
#:
#: Measured off the app's own pills at the app's own sizes — 12 pixels of
#: capital to 18 of ascent. Two-thirds is the usual figure for a humanist
#: sans and a little more for a grotesque; this face sits between them.
CAP_RATIO = 0.68


def middle(height, font):
    """Where to put centred type inside something `height` tall.

    Tk centres a line *box* — ascent plus descent — and a line box is not
    what anybody looks at. The descent is empty space under every word
    that has no descender in it, so centring the box puts the letters
    low: measured on the Settings pill, two pixels low with the icon
    beside it sitting dead centre, and three and a half on a word with a
    g in it. It is the kind of wrong that is easier to see than to name.

    What the eye centres is the band from the top of the capitals to the
    baseline. This returns the y that puts *that* band in the middle,
    which is the same rule the drawn marks beside the type already
    follow.
    """
    try:
        ascent = float(font.metrics("ascent"))
        descent = float(font.metrics("descent"))
    except Exception:
        return height / 2.0
    cap = ascent * CAP_RATIO
    return height / 2.0 + cap / 2.0 - (ascent - descent) / 2.0


def script_font(root=None, size=12, scale=True):
    """The handwritten aside. Falls back to the interface face, which is
    not the same effect — but a missing face draws boxes, and a plainer
    note reads."""
    points = text_size(size) if scale else _exact(size)
    try:
        from . import fonts as _fonts
        names = _fonts.SCRIPT_FAMILIES
    except Exception:
        names = ()
    for name in names:
        if _bundled(name, root):
            return (name, points, "normal")
    family, tk_weight = ui_family(500, root)
    return (family, points, tk_weight)


# -- the front page's own palette -----------------------------------------
#
# A second scheme, not a replacement for the one above. The palettes at
# the top of this file are the app's system colours: they dress the
# overlay, the toasts, the small windows, and they are Apple's, chosen so
# that a translation sitting on top of somebody's document looks like it
# belongs to the machine rather than to this app.
#
# The front page is the one screen that is allowed to look like Squint.
# It is drawn to a design with its own blue and its own greys, and
# pushing those into the system scheme would drag the overlay along with
# them — the same accent, on every translation, on top of every document.
# So the design's colours live here, are used by the front page, and
# reach nothing else.
PAGE_LIGHT = {
    "name": "light",
    "bg_a": "#F7FAFF",          # the wash, top
    "bg_b": "#EDF3FD",          # the wash, bottom
    "rail": "#FFFFFF",
    "card": "#FFFFFF",
    "field": "#F4F7FC",
    "field_line": "#E4EBF6",
    "line": "#E6ECF6",
    "ink": "#10172A",
    "ink_2": "#3C4762",
    "dim": "#6B7793",
    "faint": "#98A2B8",
    "accent": "#1D63F3",
    "accent_hi": "#2F74FF",
    "accent_soft": "#E7EFFE",
    "on_accent": "#FFFFFF",
    # The one warm colour on the page, and it is one mark: the bolt in
    # "Works anywhere". Three grey icons under the headline is a row of
    # bullet points; one of them being gold is what makes it a row of
    # claims.
    "gold": "#E9A020",
    "key": "#FFFFFF",
    "key_line": "#DDE5F2",
    # Sampled off the design rather than invented: it runs from a light
    # sky blue at the top left to indigo at the bottom right, and the
    # indigo is what stops it reading as a plain blue tile.
    "mark_a": "#7DBDF9",
    "mark_b": "#3975F6",
    "mark_c": "#535BF4",
}

PAGE_DARK = {
    "name": "dark",
    "bg_a": "#14161D",
    "bg_b": "#101218",
    "rail": "#1A1D25",
    "card": "#1E212A",
    "field": "#171A22",
    "field_line": "#2A2F3B",
    "line": "#282D38",
    "ink": "#F2F5FA",
    "ink_2": "#C3CBDA",
    "dim": "#939CB0",
    "faint": "#6F7889",
    "accent": "#4A8CFF",
    "accent_hi": "#6AA2FF",
    "accent_soft": "#1C2740",
    "on_accent": "#FFFFFF",
    "gold": "#F0B040",
    "key": "#262B36",
    "key_line": "#343A48",
    "mark_a": "#8AC6FA",
    "mark_b": "#4A85F8",
    "mark_c": "#6169F6",
}


def page(setting="auto"):
    """'auto' | 'light' | 'dark' -> the front page's palette."""
    name = setting if setting in ("light", "dark") else detect_system()
    return PAGE_DARK if name == "dark" else PAGE_LIGHT


def bridge(page_palette):
    """The page's colours, under the names the rest of the kit asks for.

    The window is not built only out of the new pieces. It still holds
    every dropdown, text pane, switch and pill the app already had, and
    all of those take a palette with the keys at the top of this file.
    Handed the system palette they come out in Apple's greys and Apple's
    blue, sitting inside a page drawn in neither — two designs in one
    window, which is worse than either.

    So rather than a second set of widgets, one translation: the same
    colours the page is drawn in, answering to the old names. The three
    that have no equivalent — success, warning, danger — stay as they
    were, because a warning is not part of anyone's brand.
    """
    base = DARK if page_palette.get("name") == "dark" else LIGHT
    merged = dict(base)
    merged.update({
        "name": page_palette["name"],
        "window": page_palette["bg_a"],
        "surface": page_palette["card"],
        "surface_hi": page_palette["field"],
        "field": page_palette["field"],
        "field_on_card": page_palette["field"],
        "track": page_palette["field_line"],
        "text": page_palette["ink"],
        "text_dim": page_palette["dim"],
        "text_faint": page_palette["faint"],
        "separator": page_palette["line"],
        "accent": page_palette["accent"],
        "accent_hi": page_palette["accent_hi"],
        "accent_text": page_palette["on_accent"],
        "on_accent_dim": page_palette["accent_soft"],
    })
    return merged


def for_name(name):
    return LIGHT if name == "light" else DARK


def detect_system():
    """Follow the OS appearance setting; falls back to dark."""
    if _sys.platform == "darwin":
        try:
            import subprocess
            out = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, timeout=5)
            # The key only exists in dark mode; absent means light.
            return "dark" if b"dark" in out.stdout.lower() else "light"
        except Exception:
            return "light"
    try:
        import winreg
        path = (r"Software\Microsoft\Windows\CurrentVersion\Themes"
                r"\Personalize")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if value else "dark"
    except Exception:
        return "dark"


def resolve(setting):
    """'auto' | 'light' | 'dark' -> a palette dict."""
    if setting in ("light", "dark"):
        return for_name(setting)
    return for_name(detect_system())
