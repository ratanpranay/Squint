"""Tools: open the Downloads/Squint folder, a calculator, and Squint itself.

The calculator works out what is typed (or tapped) as it goes, with the
usual signs: + - × ÷ % ^ and brackets. Only arithmetic is ever worked
out - the text is parsed, never run as code."""
import ast
import math
import operator
import os
import subprocess
import sys
import tkinter as tk

from . import common


# -- open Downloads/Squint ----------------------------------------------

def open_downloads(ctrl, **_):
    """The folder every tool saves into, in Explorer or Finder."""
    folder = common.base_dir()
    try:
        if sys.platform == "win32":
            os.startfile(folder)                     # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
    except Exception as exc:                          # noqa: BLE001
        common.failed(ctrl, "Open Downloads", exc)


def open_squint(ctrl, **_):
    """Squint's own main window."""
    ctrl.show_window()


# -- calculator ----------------------------------------------------------

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Mod: operator.mod, ast.Pow: operator.pow,
        ast.FloorDiv: operator.floordiv}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _clean(text):
    text = (text or "").strip()
    for a, b in (("×", "*"), ("x", "*"), ("X", "*"), ("÷", "/"),
                 ("−", "-"), ("–", "-"), ("^", "**"), (" ", ""),
                 (" ", ""), (" ", "")):
        text = text.replace(a, b)
    # 12,5 is a decimal comma; 1,250.50 has a thousands comma.
    if "," in text:
        text = text.replace(",", "") if "." in text else \
            text.replace(",", ".")
    # 50% on its own is 0.5; "200*15%" is 200 * 0.15.
    out = []
    for i, ch in enumerate(text):
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if ch == "%" and (nxt == "" or nxt in "+-*/)"):
            out.append("/100")
        else:
            out.append(ch)
    return "".join(out)


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise ValueError("too big")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    raise ValueError("not arithmetic")


def calculate(text):
    """The value of `text`, or None when it is not (yet) a sum."""
    text = _clean(text)
    if not text:
        return None
    try:
        value = _eval(ast.parse(text, mode="eval"))
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError,
            OverflowError, RecursionError):
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def show(value):
    """12, 12.5, 0.333333333 - no 12.0, no float noise."""
    if value is None:
        return ""
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            value = int(value)
        else:
            text = ("%.10g" % value)
            return text
    if isinstance(value, int) and abs(value) >= 10000:
        return "{:,}".format(value).replace(",", " ")
    return str(value)


_history = []        # this session's sums, newest first

# macOS key codes (the top row, and a number pad if there is one):
# (without shift, with shift).
_MAC_KEYS = {
    0x12: ("1", ""), 0x13: ("2", ""), 0x14: ("3", ""), 0x15: ("4", ""),
    0x17: ("5", "%"), 0x16: ("6", "^"), 0x1A: ("7", ""), 0x1C: ("8", "×"),
    0x19: ("9", "("), 0x1D: ("0", ")"), 0x1B: ("−", ""), 0x18: ("=", "+"),
    0x2C: ("÷", ""), 0x2F: (".", ""), 0x2B: (".", ""),
    0x52: ("0", "0"), 0x53: ("1", "1"), 0x54: ("2", "2"), 0x55: ("3", "3"),
    0x56: ("4", "4"), 0x57: ("5", "5"), 0x58: ("6", "6"), 0x59: ("7", "7"),
    0x5B: ("8", "8"), 0x5C: ("9", "9"), 0x41: (".", "."), 0x43: ("×", "×"),
    0x45: ("+", "+"), 0x4E: ("−", "−"), 0x4B: ("÷", "÷"), 0x51: ("=", "="),
    0x24: ("=", "="), 0x4C: ("=", "="),
    0x33: ("Del", "Del"), 0x75: ("Del", "Del"), 0x47: ("C", "C"),
}
_SHIFT = (0x38, 0x3C)


def _mac_typing(menu, entry, press, equals):
    """Read the keyboard every 30 ms while the calculator is up: each key
    counts once per press, and a held key repeats after a short pause."""
    import time
    try:
        from .. import platform_util
        asker = platform_util._key_state()
    except Exception:
        asker = None
    if asker is None:
        return
    held = {}

    def tick():
        try:
            if menu.closed or menu.view != "calculator" or \
                    not entry.winfo_exists():
                return
        except tk.TclError:
            return
        shift = any(asker(k) for k in _SHIFT)
        now = time.time()
        for code, (plain, shifted) in _MAC_KEYS.items():
            if not asker(code):
                held.pop(code, None)
                continue
            first = code not in held
            if first:
                held[code] = now + 0.45
            elif now >= held[code]:
                held[code] = now + 0.07
            else:
                continue
            key = shifted if shift else plain
            if not key:
                continue
            if key == "=":
                if first:
                    equals()
            else:
                press(key)
        entry.after(30, tick)

    entry.after(200, tick)


def calculator(ctrl, menu=None, **_):
    if menu is None:
        return

    def build(frame):
        s = menu.s
        menu.header(frame, "Calculator", close=True)
        th = menu.th
        colour = menu.tools[menu.selected].get("colour", common.ACCENT) \
            if menu.selected is not None else common.ACCENT
        var = tk.StringVar()
        # The sum floats on the panel, like the time in the ring.
        entry = tk.Entry(frame, textvariable=var, bg=common.PANEL,
                         fg=common.TITLE, relief="flat", highlightthickness=0,
                         bd=0, insertbackground=colour, justify="right",
                         font=menu.f(26, True))
        entry.pack(fill="x", ipady=int(2 * s))
        result = tk.Label(frame, text=" ", bg=common.PANEL, fg=colour,
                          font=menu.f(15, True), anchor="e")
        result.pack(fill="x", pady=(0, int(8 * s)))

        def update(*_a):
            value = calculate(var.get())
            result.configure(text=("= " + show(value)) if value is not None
                             and _clean(var.get()) != show(value) else " ")

        var.trace_add("write", update)

        def press(key):
            text = var.get()
            if key == "C":
                var.set("")
            elif key == "Del":
                var.set(text[:-1])
            elif key == "=":
                equals()
                return
            else:
                var.set(text + key)
            entry.icursor("end")

        def equals(_e=None):
            value = calculate(var.get())
            if value is None:
                return "break"
            line = "%s = %s" % (var.get().strip(), show(value))
            if not _history or _history[0] != line:
                _history.insert(0, line)
                del _history[5:]
            var.set(show(value).replace(" ", ""))
            entry.icursor("end")
            draw_history()
            return "break"

        entry.bind("<Return>", equals)
        entry.bind("<KP_Enter>", equals)

        pad = tk.Frame(frame, bg=common.PANEL)
        pad.pack()
        keys = (("C", "Del", "%", "÷"),
                ("7", "8", "9", "×"),
                ("4", "5", "6", "−"),
                ("1", "2", "3", "+"),
                ("(", ")", "0", "."))
        size = int(56 * s)
        # Round keys, like the tools in the ring: digits in the ring's
        # text colour, signs in the tool's colour.
        for r, row in enumerate(keys):
            for c, key in enumerate(row):
                sign = key in ("÷", "×", "−", "+", "%")
                quiet = key in ("C", "Del")
                b = common.PillButton(
                    pad, text=key, command=lambda k=key: press(k),
                    bg=th["item"], outline=th["item_line"],
                    fg=colour if sign else (th["sub"] if quiet
                                            else th["label"]),
                    activebackground=colour, activeforeground="#FFFFFF",
                    font=menu.f(17 if sign else 15, sign),
                    width=size, height=size, padx=0, pady=0)
                b.grid(row=r, column=c, padx=int(4 * s), pady=int(4 * s))
        common.PillButton(pad, text="=", command=equals, bg=colour,
                          fg="#FFFFFF", activebackground=common._mix(
                              colour, "#000000", 0.12),
                          activeforeground="#FFFFFF",
                          font=menu.f(17, True), width=4 * size + 24 * s,
                          height=int(46 * s), padx=0, pady=0).grid(
            row=len(keys), column=0, columnspan=4, padx=int(4 * s),
            pady=(int(6 * s), int(4 * s)))

        lines = tk.Frame(frame, bg=common.PANEL)
        lines.pack(fill="x", pady=(int(6 * s), 0))

        def copy_value(text):
            try:
                frame.clipboard_clear()
                frame.clipboard_append(text)
            except tk.TclError:
                pass

        def draw_history():
            for child in lines.winfo_children():
                child.destroy()
            for line in _history:
                answer = line.rsplit("= ", 1)[-1].replace(" ", "")
                item = tk.Label(lines, text=line, bg=common.PANEL,
                                fg=common.MUTED, font=menu.f(11),
                                anchor="e", cursor="hand2")
                item.pack(fill="x")
                item.bind("<Button-1>", lambda _e, a=answer: (
                    var.set(a), copy_value(a)))
            if _history:
                tk.Label(lines, text="Click a line to use it again (it is "
                         "copied too).", bg=common.PANEL, fg=common.FAINT,
                         font=menu.f(11), anchor="e").pack(fill="x")
            menu.relayout()

        draw_history()
        # Typing, the number pad included, goes straight into the sum.
        if common.IS_MAC:
            # The ring's window never gets the keyboard on a Mac, so the
            # keys are read straight from it while the calculator is open
            # (as Escape already is). Squint is brought forward meanwhile,
            # so the keys do not also type into the app behind; the ring
            # hands the front back when it closes. The box is read-only
            # here so nothing arrives twice.
            try:
                from AppKit import NSApplication
                NSApplication.sharedApplication() \
                    .activateIgnoringOtherApps_(True)
            except Exception:
                pass
            entry.configure(state="readonly",
                            readonlybackground=common.PANEL)
            _mac_typing(menu, entry, press, equals)
            return
        try:
            menu.win.focus_force()
        except tk.TclError:
            pass
        entry.focus_set()
        entry.icursor("end")
        menu.win.after(150, entry.focus_set)

    menu.show_view(build, pinned=True, name="calculator")
