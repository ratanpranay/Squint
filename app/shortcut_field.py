"""A shortcut field you press keys into, instead of typing their names.

Typing "ctrl+cmd+t" into a text box and pressing Apply is how this app used
to work, and it is the reason several days went into shortcut problems: you
cannot tell whether the app understood what you typed, whether the
combination is legal, or whether something else already owns it, until long
afterwards. Pressing the keys removes all three questions at once.
"""
import sys
import tkinter as tk

from . import theme as theme_mod
from .ui_kit import plate_item, rounded, set_plate

IS_MAC = sys.platform == "darwin"

# Tk reports modifiers as bits in event.state, and the meaning of the bits
# differs by platform. On Aqua, Tk maps Command to Mod1 and Option to Mod2
# (tkMacOSXKeyEvent.c); on X11 and Windows, Mod1 is Alt.
if IS_MAC:
    _MODIFIERS = ((0x0004, "ctrl"), (0x0008, "cmd"),
                  (0x0010, "alt"), (0x0001, "shift"))
else:
    _MODIFIERS = ((0x0004, "ctrl"), (0x0008, "alt"),
                  (0x0001, "shift"), (0x40000, "win"))

_GLYPHS = {"ctrl": "⌃", "alt": "⌥", "shift": "⇧",
           "cmd": "⌘", "win": "Win+"}
_ORDER = ("ctrl", "alt", "shift", "cmd", "win")

# Keys that are only modifiers — pressing one is not yet a shortcut.
_MODIFIER_KEYSYMS = {
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
    "Meta_L", "Meta_R", "Super_L", "Super_R", "Caps_Lock", "Option_L",
    "Option_R", "Command_L", "Command_R", "ISO_Level3_Shift",
}

_NAMED_KEYS = {
    "space": "space", "Return": "return", "Tab": "tab", "Escape": "escape",
    "BackSpace": "backspace", "Delete": "delete", "Home": "home",
    "End": "end", "Prior": "pageup", "Next": "pagedown",
    "Left": "left", "Right": "right", "Up": "up", "Down": "down",
}


# The running hotkey manager, handed over by the app at startup. A module
# level hook rather than an argument threaded through every field, because
# the field is built in three places and none of them knows about hotkeys.
HOTKEYS = None


def _release_hotkeys(release):
    """Stop or restart the live global shortcuts. Never raises.

    Failing to let go means one combination cannot be recorded. Failing to
    take them back again means none of them work until the app restarts, so
    this is called on every way out of recording — the timeout included.
    """
    manager = HOTKEYS
    if manager is None:
        return
    try:
        (manager.pause if release else manager.resume)()
    except Exception:
        pass


def spec_from_event(event):
    """Turn a key press into 'ctrl+cmd+t', or None if it is not usable."""
    keysym = event.keysym
    if keysym in _MODIFIER_KEYSYMS:
        return None

    parts = [name for bit, name in _MODIFIERS if event.state & bit]
    if keysym in _NAMED_KEYS:
        key = _NAMED_KEYS[keysym]
    elif keysym.startswith("F") and keysym[1:].isdigit():
        key = keysym.lower()
    elif len(keysym) == 1 and (keysym.isalnum() or keysym in "-=[]\\;',./`"):
        key = keysym.lower()
    else:
        return None

    # A bare letter is not a shortcut; function keys can stand alone.
    if not parts and not key.startswith("f"):
        return None
    # And on a Mac, Command with nothing else is the system's own
    # vocabulary. ⌘C, ⌘V, ⌘W, ⌘Q: taking one of those globally means the
    # user cannot copy, paste, close or quit anywhere until they find
    # their way back into this panel — and the panel they would use to fix
    # it is one they can no longer copy a key into. ⌘ with ⌃ or ⌥ beside
    # it is fine and is what the defaults use.
    if IS_MAC and parts == ["cmd"] and not key.startswith("f"):
        return None
    parts.sort(key=lambda name: _ORDER.index(name)
               if name in _ORDER else len(_ORDER))
    return "+".join(parts + [key])


def pretty(spec):
    """'ctrl+cmd+t' -> '⌃⌘T' on macOS, 'Ctrl+Cmd+T' elsewhere."""
    if not spec:
        return ""
    parts = [p.strip().lower() for p in str(spec).split("+") if p.strip()]
    modifiers = [p for p in parts if p in _GLYPHS]
    keys = [p for p in parts if p not in _GLYPHS]
    modifiers.sort(key=lambda name: _ORDER.index(name)
                   if name in _ORDER else len(_ORDER))
    key = (keys[0] if keys else "").upper()
    if IS_MAC:
        return "".join(_GLYPHS[m] for m in modifiers) + key
    return "+".join([m.capitalize() for m in modifiers] + ([key] if key else []))


class ShortcutField(tk.Frame):
    """Click it, press the combination, done."""

    PROMPT = "Press keys…"

    def __init__(self, parent, palette, value="", on_change=None,
                 width=178, height=None, bg=None):
        # The same height as every other control in Settings; it used to be
        # its own size, in its own type size, next to popups that were three
        # more.
        from .ui_kit import Dropdown
        height = Dropdown.HEIGHT if height is None else height
        self.palette = palette
        self._bg = bg or palette["window"]
        self.on_change = on_change
        self._value = value or ""
        self._recording = False
        super().__init__(parent, bg=self._bg)

        self.canvas = tk.Canvas(self, width=width, height=height,
                                highlightthickness=0, bd=0, bg=self._bg,
                                cursor="arrow")
        self.canvas.pack()
        self._img = plate_item(self.canvas)
        self._photo = None
        self._text = self.canvas.create_text(
            width // 2 - 10, height // 2,
            font=theme_mod.font(parent, 10), fill=palette["text"])
        self._clear = self.canvas.create_text(
            width - 16, height // 2, text="✕",
            font=theme_mod.font(parent, 9), fill=palette["text_dim"])

        self._binding = None
        self._top = None
        self._timer = None
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.tag_bind(self._clear, "<Button-1>", self._on_clear)
        self._paint()

    # -- state ---------------------------------------------------------
    def get(self):
        return self._value

    def set(self, value):
        self._value = value or ""
        self._paint()

    # The field currently listening. Two of them recording at once is not
    # a state that means anything, and it was reachable: arming the second
    # never disarmed the first, so both sat there saying "Press keys…" and
    # neither of them was listening.
    _armed = None

    def _on_click(self, event):
        # The clear cross has its own binding; ignore clicks that land on it.
        if event.x > int(self.canvas["width"]) - 30:
            return
        other = ShortcutField._armed
        if other is not None and other is not self:
            other._stop()
        self._arm()

    def _arm(self):
        """Start listening — on the window, not on this widget.

        The old version called focus_set() on the canvas and bound
        <KeyPress> to it, which is the obvious way and does not work on a
        Mac. A Tk window there can take mouse clicks while not being the
        key window, so the click landed, the field lit up, focus_set()
        quietly did nothing, and no keystroke ever arrived. Nor did
        <FocusOut>, which is why the first field stayed armed when the
        second was clicked: it had never had focus to lose.

        So: force the window to the front, and listen at the window level
        where the keystrokes actually are.
        """
        # Let go of the live shortcuts first.
        #
        # A registered global shortcut consumes the keystroke — that is the
        # whole point of one. So while Squint holds Ctrl+Cmd+T, pressing
        # Ctrl+Cmd+T into this box never reaches the box: the registration
        # takes it and fires a snip. The combination somebody most wants to
        # retype is the one this could never record, and from outside that
        # is simply "the shortcut box does not work".
        _release_hotkeys(True)
        self._recording = True
        ShortcutField._armed = self
        top = self.winfo_toplevel()
        for step in (top.lift, top.focus_force, self.canvas.focus_set):
            try:
                step()
            except Exception:
                pass
        try:
            self._top = top
            self._binding = top.bind("<KeyPress>", self._on_key, "+")
        except Exception:
            self._top, self._binding = None, None
        # Armed and forgotten is now worse than a window that eats
        # keystrokes: the shortcuts are released while this is listening,
        # so a field left armed is a Squint with no shortcuts at all until
        # something disarms it. Fifteen seconds is longer than anybody
        # needs to press three keys, and short enough that forgetting is
        # a pause rather than a breakage.
        try:
            self._timer = self.after(15000, self._stop)
        except Exception:
            self._timer = None
        self._paint()

    @classmethod
    def disarm_any(cls):
        """Stop whatever field is listening, wherever it is.

        Closing the window while a field is armed used to be harmless.
        Now it would leave the shortcuts released — the app running with
        no shortcuts at all, and no window open to explain why.
        """
        armed = cls._armed
        if armed is not None:
            try:
                armed._stop()
            except Exception:
                _release_hotkeys(False)

    def _on_clear(self, _event=None):
        self._recording = False
        self._value = ""
        self._paint()
        if self.on_change:
            self.on_change("")
        return "break"

    def _stop(self):
        if not self._recording:
            return
        self._recording = False
        _release_hotkeys(False)
        if ShortcutField._armed is self:
            ShortcutField._armed = None
        if self._top is not None and self._binding:
            try:
                self._top.unbind("<KeyPress>", self._binding)
            except Exception:
                pass
        self._top, self._binding = None, None
        if self._timer is not None:
            try:
                self.after_cancel(self._timer)
            except Exception:
                pass
            self._timer = None
        self._paint()

    def _on_key(self, event):
        if not self._recording:
            return None
        if event.keysym == "Escape":
            self._stop()
            return "break"
        spec = spec_from_event(event)
        if spec is None:
            return "break"      # a modifier on its own: keep waiting
        self._value = spec
        self._stop()
        if self.on_change:
            self.on_change(spec)
        return "break"

    # -- appearance ----------------------------------------------------
    def _paint(self):
        width = int(self.canvas["width"])
        height = int(self.canvas["height"])
        palette = self.palette
        fill = palette["field"]
        outline = palette["accent"] if self._recording else (
            palette["separator"] if palette["name"] == "light" else None)
        self._photo = set_plate(self.canvas, self._img, 0, 0, width,
                                height, height // 2, fill, outline)

        if self._recording:
            text, colour = self.PROMPT, palette["accent"]
        elif self._value:
            text, colour = pretty(self._value), palette["text"]
        else:
            text, colour = "not set", palette["text_dim"]
        self.canvas.itemconfig(self._text, text=text, fill=colour)
        self.canvas.itemconfig(
            self._clear, state="normal" if self._value else "hidden")
        self.canvas.tag_raise(self._text)
        self.canvas.tag_raise(self._clear)
