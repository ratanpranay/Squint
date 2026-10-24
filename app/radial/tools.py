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


def calculator(ctrl, menu=None, **_):
    if menu is None:
        return

    def build(frame):
        s = menu.s
        menu.header(frame, "Calculator", close=True)
        var = tk.StringVar()
        entry = tk.Entry(frame, textvariable=var, bg=common.ROW,
                         fg=common.TITLE, relief="flat", highlightthickness=0,
                         insertbackground=common.TEXT, justify="right",
                         font=menu.f(20))
        entry.pack(fill="x", ipady=int(8 * s))
        result = tk.Label(frame, text=" ", bg=common.PANEL, fg=common.MUTED,
                          font=menu.f(15, True), anchor="e")
        result.pack(fill="x", pady=(int(4 * s), int(8 * s)))

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
        pad.pack(fill="x")
        keys = (("C", "Del", "%", "÷"),
                ("7", "8", "9", "×"),
                ("4", "5", "6", "−"),
                ("1", "2", "3", "+"),
                ("(", ")", "0", "."))
        colour = menu.tools[menu.selected].get("colour", common.ACCENT) \
            if menu.selected is not None else common.ACCENT
        for r, row in enumerate(keys):
            for c, key in enumerate(row):
                pad.columnconfigure(c, weight=1, uniform="key")
                op = key in ("÷", "×", "−", "+", "%", "C", "Del")
                eq = False
                b = common.PillButton(
                    pad, text=key, command=lambda k=key: press(k),
                    bg=colour if eq else (common.LINE if op else common.ROW),
                    fg="#FFFFFF" if eq else common.TEXT,
                    font=menu.f(15, eq), padx=int(4 * s), pady=int(8 * s))
                b.grid(row=r, column=c, sticky="nsew", padx=int(3 * s),
                       pady=int(3 * s))
        common.PillButton(pad, text="=", command=equals, bg=colour,
                          fg="#FFFFFF", font=menu.f(15, True),
                          padx=int(4 * s), pady=int(8 * s)).grid(
            row=len(keys), column=0, columnspan=4, sticky="nsew",
            padx=int(3 * s), pady=int(3 * s))

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
        entry.focus_set()

    menu.show_view(build, pinned=True, name="calculator")
