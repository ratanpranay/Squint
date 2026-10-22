"""The small card an action opens next to the ring.

One card carries an action from start to finish, in place:

    settings  ->  Start  ->  progress bar  ->  Done · Open folder

so there is never a stack of separate pop-up windows. Actions with
nothing to set skip straight to the progress bar.

Work runs on a background thread and reports through `progress(fraction,
text)`, which only stores values; the card reads them on a Tk timer. Tk
is never touched from the worker.
"""
import queue
import sys
import threading
import tkinter as tk

from . import common

IS_WINDOWS = sys.platform == "win32"


class Card:
    open_cards = []

    def __init__(self, ctrl, title, anchor=None, subtitle=""):
        self.ctrl = ctrl
        self.title = title
        self.closed = False
        self._state = {"fraction": None, "text": ""}
        self._spin = 0
        self._job = None
        root = ctrl.root
        self.s = s = self._scale(root, anchor)
        self.w = int(300 * s)

        win = self.win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=common.LINE)
        self.frame = tk.Frame(win, bg=common.PANEL, padx=int(14 * s),
                              pady=int(12 * s))
        self.frame.pack(padx=1, pady=1)
        # Every card the same width, whatever is in it.
        tk.Frame(self.frame, bg=common.PANEL, width=self.w - int(28 * s),
                 height=1).pack()

        head = tk.Frame(self.frame, bg=common.PANEL)
        head.pack(fill="x")
        tk.Label(head, text=title, bg=common.PANEL, fg="#FFFFFF",
                 font=self._f(13, True), anchor="w").pack(side="left")
        close = tk.Label(head, text="✕", bg=common.PANEL, fg=common.MUTED,
                         font=self._f(12), cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda _e: self.cancel())
        self.subtitle = tk.Label(self.frame, text=subtitle, bg=common.PANEL,
                                 fg=common.MUTED, font=self._f(10),
                                 anchor="w", justify="left",
                                 wraplength=self.w - int(28 * s))
        if subtitle:
            self.subtitle.pack(fill="x", pady=(int(2 * s), 0))
        self.body = tk.Frame(self.frame, bg=common.PANEL, width=self.w)
        self.body.pack(fill="x", pady=(int(10 * s), 0))

        # Drag by the header, like any small window.
        for w in (head,) + tuple(head.winfo_children()[:1]):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag)
        win.bind("<Escape>", lambda _e: self.cancel())
        self._anchor = anchor
        Card.open_cards.append(self)

    # -- sizes ---------------------------------------------------------------

    @staticmethod
    def _scale(root, anchor):
        try:
            from .. import platform_util
            x, y = anchor or root.winfo_pointerxy()
            return max(1.0, (platform_util.monitor_scaling(x, y) or 100) / 100.0)
        except Exception:
            return 1.0

    def _f(self, size, bold=False):
        return (common.FONT, -int(round(size * self.s)),
                "bold" if bold else "normal")

    def _place(self):
        win = self.win
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        if self._anchor:
            x, y = self._anchor
        else:
            px, py = win.winfo_pointerxy()
            x, y = px + 20, py - h // 2
        try:
            from .. import platform_util
            for (mx, my, mw, mh) in platform_util.displays():
                if mx <= x < mx + mw and my <= y < my + mh:
                    x = min(max(x, mx + 8), mx + mw - w - 8)
                    y = min(max(y, my + 8), my + mh - h - 56)
                    break
        except Exception:
            pass
        win.geometry("+%d+%d" % (int(x), int(y)))
        win.lift()
        self._focus()

    def _focus(self):
        try:
            self.win.focus_force()
            if IS_WINDOWS:
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(
                    int(self.win.wm_frame(), 16))
        except Exception:
            pass

    def _drag_start(self, e):
        self._grab = (e.x_root - self.win.winfo_x(),
                      e.y_root - self.win.winfo_y())

    def _drag(self, e):
        dx, dy = self._grab
        self.win.geometry("+%d+%d" % (e.x_root - dx, e.y_root - dy))

    def _clear(self):
        for child in self.body.winfo_children():
            child.destroy()

    def _button(self, parent, text, command, primary=False):
        b = common._button(parent, text, command, primary)
        b.configure(font=self._f(11), padx=int(14 * self.s),
                    pady=int(6 * self.s))
        return b

    # -- settings ------------------------------------------------------------

    def form(self, fields, start_label, on_start):
        """Show settings. `on_start(values)` runs when Start is pressed and
        everything checks out.

        Fields (dicts):
          {"kind": "password", "key": "password", "optional": True,
           "label": "Lock with a password"}
          {"kind": "choice", "key": "fmt", "label": "Format",
           "options": [(key, text), ...], "default": key}
          {"kind": "check", "key": "x", "label": "...", "default": False}
          {"kind": "note", "text": "..."}
        """
        self._clear()
        s = self.s
        values = {}
        checks = []
        first_entry = []

        for field in fields:
            kind = field["kind"]
            if kind == "note":
                tk.Label(self.body, text=field["text"], bg=common.PANEL,
                         fg=common.MUTED, font=self._f(10), justify="left",
                         wraplength=self.w - int(28 * s), anchor="w").pack(
                    fill="x", pady=(0, int(8 * s)))
            elif kind == "choice":
                tk.Label(self.body, text=field["label"], bg=common.PANEL,
                         fg=common.MUTED, font=self._f(10), anchor="w").pack(
                    fill="x")
                var = tk.StringVar(value=field.get("default",
                                                   field["options"][0][0]))
                values[field["key"]] = var
                row = tk.Frame(self.body, bg=common.PANEL)
                row.pack(fill="x", pady=(int(3 * s), int(10 * s)))
                buttons = {}

                def paint(var=var, buttons=buttons):
                    for k, b in buttons.items():
                        on = var.get() == k
                        b.configure(bg=common.ACCENT if on else common.ROW,
                                    fg="#FFFFFF" if on else common.TEXT)

                for i, (key, text) in enumerate(field["options"]):
                    b = tk.Button(row, text=text, relief="flat", bd=0,
                                  highlightthickness=0, font=self._f(10),
                                  padx=int(8 * s), pady=int(5 * s),
                                  cursor="hand2",
                                  activebackground=common.ACCENT,
                                  activeforeground="#FFFFFF",
                                  command=lambda k=key, v=var, p=paint:
                                  (v.set(k), p()))
                    b.grid(row=i // 4, column=i % 4, padx=(0, int(4 * s)),
                           pady=(0, int(4 * s)), sticky="we")
                    buttons[key] = b
                paint()
            elif kind == "check":
                var = tk.BooleanVar(value=field.get("default", False))
                values[field["key"]] = var
                tk.Checkbutton(self.body, text=field["label"], variable=var,
                               bg=common.PANEL, fg=common.TEXT,
                               selectcolor=common.ROW,
                               activebackground=common.PANEL,
                               activeforeground=common.TEXT, highlightthickness=0,
                               font=self._f(10), anchor="w", justify="left",
                               wraplength=self.w - int(50 * s)).pack(
                    fill="x", pady=(0, int(6 * s)))
            elif kind == "password":
                optional = field.get("optional", True)
                on = tk.BooleanVar(value=not optional)
                pw1, pw2 = tk.StringVar(), tk.StringVar()
                values[field["key"]] = (on, pw1, pw2)
                box = tk.Frame(self.body, bg=common.PANEL)

                def entry(parent, var, label):
                    tk.Label(parent, text=label, bg=common.PANEL,
                             fg=common.MUTED, font=self._f(10),
                             anchor="w").pack(fill="x")
                    e = tk.Entry(parent, textvariable=var, show="•",
                                 bg=common.ROW, fg=common.TEXT,
                                 insertbackground=common.TEXT, relief="flat",
                                 highlightthickness=0, font=self._f(12))
                    e.pack(fill="x", ipady=int(4 * s), pady=(int(2 * s),
                                                            int(6 * s)))
                    return e

                e1 = entry(box, pw1, "Password")
                entry(box, pw2, "Again")
                first_entry.append(e1)

                def toggle(on=on, box=box, e1=e1):
                    if on.get():
                        box.pack(fill="x", after=toggler)
                        e1.focus_set()
                    else:
                        box.pack_forget()

                if optional:
                    toggler = tk.Checkbutton(
                        self.body, text=field.get("label",
                                                  "Lock with a password"),
                        variable=on, command=toggle, bg=common.PANEL,
                        fg=common.TEXT, selectcolor=common.ROW,
                        activebackground=common.PANEL,
                        activeforeground=common.TEXT, font=self._f(11),
                        highlightthickness=0, anchor="w")
                    toggler.pack(fill="x", pady=(0, int(4 * s)))
                else:
                    toggler = tk.Frame(self.body, bg=common.PANEL)
                    toggler.pack(fill="x")
                    box.pack(fill="x")
                checks.append((on, pw1, pw2))

        self.error = tk.Label(self.body, text="", bg=common.PANEL,
                              fg="#F28B82", font=self._f(10), anchor="w",
                              justify="left", wraplength=self.w - int(28 * s))
        self.error.pack(fill="x")
        row = tk.Frame(self.body, bg=common.PANEL)
        row.pack(fill="x", pady=(int(6 * s), 0))

        def start(_e=None):
            for on, pw1, pw2 in checks:
                if on.get():
                    if not pw1.get():
                        self.error.configure(text="Type a password.")
                        return
                    if pw1.get() != pw2.get():
                        self.error.configure(
                            text="The two passwords are not the same.")
                        return
            out = {}
            for key, var in values.items():
                if isinstance(var, tuple):
                    out[key] = var[1].get() if var[0].get() else ""
                else:
                    out[key] = var.get()
            on_start(out)

        self._button(row, start_label, start, primary=True).pack(side="right")
        self._button(row, "Cancel", self.cancel).pack(side="right",
                                                      padx=(0, int(6 * s)))
        self.win.bind("<Return>", start)
        self._place()
        if first_entry and not any(f.get("optional", True) for f in fields
                                   if f["kind"] == "password"):
            first_entry[0].focus_set()

    # -- progress ------------------------------------------------------------

    def progress(self, fraction=None, text=None):
        """Thread-safe. `fraction` None means "busy, amount unknown"."""
        self._state["fraction"] = fraction
        if text is not None:
            self._state["text"] = text

    def run(self, work, finish, what=None):
        """Show the bar and run `work(progress)` in the background.
        `finish(result)` returns (message, path_or_None) for the Done view."""
        self._clear()
        self.win.unbind("<Return>")
        s = self.s
        self.label = tk.Label(self.body, text=what or "Working…",
                              bg=common.PANEL, fg=common.TEXT,
                              font=self._f(11), anchor="w", justify="left",
                              wraplength=self.w - int(28 * s))
        self.label.pack(fill="x")
        self.bar_w = self.w - int(28 * s)
        self.canvas = tk.Canvas(self.body, width=self.bar_w,
                                height=int(8 * s), bg=common.ROW,
                                highlightthickness=0)
        self.canvas.pack(fill="x", pady=(int(8 * s), int(4 * s)))
        self.fill = self.canvas.create_rectangle(0, 0, 0, int(8 * s),
                                                 fill=common.ACCENT, width=0)
        self.detail = tk.Label(self.body, text="", bg=common.PANEL,
                               fg=common.MUTED, font=self._f(10), anchor="w")
        self.detail.pack(fill="x")
        row = tk.Frame(self.body, bg=common.PANEL)
        row.pack(fill="x", pady=(int(8 * s), 0))
        self._button(row, "Hide", self._hide).pack(side="right")
        self._state["text"] = what or ""
        self._place()

        box = queue.Queue()

        def runner():
            try:
                box.put((True, work(self.progress)))
            except Exception as exc:      # noqa: BLE001 - shown in the card
                import traceback
                common.log(traceback.format_exc())
                box.put((False, exc))

        threading.Thread(target=runner, daemon=True,
                         name="radial-card").start()

        def pump():
            if self.closed:
                return
            try:
                ok, value = box.get_nowait()
            except queue.Empty:
                self._draw_bar()
                self._job = self.win.after(100, pump)
                return
            if not ok:
                self.fail(str(value) or value.__class__.__name__)
                return
            try:
                result = finish(value)
            except Exception as exc:      # noqa: BLE001
                self.fail(str(exc))
                return
            if result is None:            # the caller carries on itself
                self._job = None
                self.close()
                return
            self.done(*result)

        pump()

    def _draw_bar(self):
        frac = self._state["fraction"]
        h = int(8 * self.s)
        try:
            if frac is None:
                self._spin = (self._spin + 1) % 40
                seg = self.bar_w * 0.3
                x = (self._spin / 40.0) * (self.bar_w + seg) - seg
                self.canvas.coords(self.fill, max(0, x), 0,
                                   min(self.bar_w, x + seg), h)
                self.detail.configure(text=self._state["text"])
            else:
                self.canvas.coords(self.fill, 0, 0, self.bar_w * frac, h)
                self.detail.configure(text="%s   %d%%" % (
                    self._state["text"], int(frac * 100)))
        except tk.TclError:
            pass

    def _hide(self):
        """Keep working out of the way; say so when it is done."""
        self._hidden = True
        try:
            self.win.withdraw()
        except tk.TclError:
            pass

    # -- the end -------------------------------------------------------------

    def done(self, message, path=None):
        self._job = None
        if getattr(self, "_hidden", False):
            self.close()
            common.tell(self.ctrl, message, path)
            return
        self._clear()
        s = self.s
        tk.Label(self.body, text="✓  " + message, bg=common.PANEL,
                 fg="#5FD38D", font=self._f(12, True), anchor="w",
                 justify="left", wraplength=self.w - int(28 * s)).pack(
            fill="x")
        if path and common.where(path):
            tk.Label(self.body, text=common.where(path), bg=common.PANEL,
                     fg=common.MUTED, font=self._f(10), anchor="w").pack(
                fill="x", pady=(int(4 * s), 0))
        row = tk.Frame(self.body, bg=common.PANEL)
        row.pack(fill="x", pady=(int(10 * s), 0))
        self._button(row, "Close", self.close).pack(side="right")
        if path:
            folder = path if not common.os.path.isfile(path) else \
                common.os.path.dirname(path)

            def open_it():
                try:
                    from .. import platform_util
                    if common.os.path.isfile(path):
                        platform_util.reveal(path)
                    else:
                        platform_util.open_path(folder)
                except Exception:
                    pass
                self.close()

            self._button(row, "Open folder", open_it, primary=True).pack(
                side="right", padx=(0, int(6 * s)))
            self.win.bind("<Return>", lambda _e: open_it())
        self._place()
        self.win.after(15000, self.close)

    def fail(self, message):
        self._job = None
        common.log("card %s failed: %s" % (self.title, message))
        if getattr(self, "_hidden", False):
            try:
                self.win.deiconify()
            except tk.TclError:
                pass
            self._hidden = False
        self._clear()
        s = self.s
        tk.Label(self.body, text="That did not work.", bg=common.PANEL,
                 fg="#F28B82", font=self._f(12, True), anchor="w").pack(
            fill="x")
        tk.Label(self.body, text=message[:400], bg=common.PANEL,
                 fg=common.TEXT, font=self._f(10), anchor="w",
                 justify="left", wraplength=self.w - int(28 * s)).pack(
            fill="x", pady=(int(4 * s), 0))
        row = tk.Frame(self.body, bg=common.PANEL)
        row.pack(fill="x", pady=(int(10 * s), 0))
        self._button(row, "Close", self.close, primary=True).pack(
            side="right")
        self._place()

    def cancel(self):
        """Closing while work runs only hides the card: the work finishes
        and the result is announced."""
        if self._job is not None and not self.closed:
            self._hide()
            return
        self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self in Card.open_cards:
            Card.open_cards.remove(self)
        try:
            self.win.destroy()
        except Exception:
            pass


def ensure_tool(card, getter):
    """Inside a card's work: the helper program, fetched with the card's
    own bar the first time. Returns its path."""
    finder = {"ffmpeg": common.ffmpeg_path, "7zip": common.sevenzip_path}
    have = finder[getter]()
    if have:
        return have

    class Bar:
        def set(self, fraction, text=None):
            card(fraction, text)

    label = {"ffmpeg": "Getting the video tools (once)",
             "7zip": "Getting 7-Zip (once)"}[getter]
    card(0.0, label)
    fetch = {"ffmpeg": common.get_ffmpeg, "7zip": common.get_7zip}[getter]
    return fetch(Bar())
