"""A month view with a simple agenda kept on this computer.

Click a day to see what is on it and add to it. Anything with a time
pops up as a reminder at that time while Squint is running."""
import calendar
import datetime as dt
import json
import os
import tkinter as tk

from . import common
from .. import config

_REMINDED = set()


def _path():
    return os.path.join(config.data_dir(), "agenda.json")


def load():
    try:
        with open(_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data):
    tmp = _path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, _path())


def add(day, text, time=""):
    data = load()
    items = data.setdefault(day.isoformat(), [])
    items.append({"time": time, "text": text})
    items.sort(key=lambda i: (i.get("time") or "99:99"))
    save(data)


def remove(day, index):
    data = load()
    items = data.get(day.isoformat(), [])
    if 0 <= index < len(items):
        items.pop(index)
    if not items:
        data.pop(day.isoformat(), None)
    save(data)


def parse_time(text):
    """'9', '9:30', '0930', '14.15' -> 'HH:MM'; '' for none; None if bad."""
    t = text.strip().replace(".", ":")
    if not t:
        return ""
    if ":" not in t:
        t = t[:-2] + ":" + t[-2:] if len(t) > 2 else t + ":00"
    try:
        h, m = (int(p) for p in t.split(":", 1))
    except ValueError:
        return None
    if 0 <= h < 24 and 0 <= m < 60:
        return "%02d:%02d" % (h, m)
    return None


def start_reminders(ctrl):
    """Check once a minute for an agenda item whose time has come."""
    def tick():
        try:
            now = dt.datetime.now()
            key = now.date().isoformat()
            for item in load().get(key, []):
                when = item.get("time")
                if not when:
                    continue
                tag = (key, when, item.get("text"))
                due = dt.datetime.combine(now.date(),
                                          dt.time(*map(int, when.split(":"))))
                if tag not in _REMINDED and \
                        0 <= (now - due).total_seconds() < 120:
                    _REMINDED.add(tag)
                    common.tell(ctrl, "%s  %s" % (when, item.get("text", "")))
        except Exception as exc:          # noqa: BLE001 - keep ticking
            common.log("reminders: %r" % exc)
        ctrl.root.after(30000, tick)

    ctrl.root.after(5000, tick)


class CalendarWindow:
    _open = None

    @classmethod
    def show(cls, ctrl, near=None):
        if cls._open is not None:
            try:
                cls._open.win.deiconify()
                cls._open.win.lift()
                cls._open.win.focus_force()
                return cls._open
            except tk.TclError:
                cls._open = None
        cls._open = cls(ctrl, near)
        return cls._open

    def __init__(self, ctrl, near=None):
        self.ctrl = ctrl
        today = dt.date.today()
        self.month = today.replace(day=1)
        self.day = today
        win = self.win = tk.Toplevel(ctrl.root)
        win.title("Calendar")
        win.configure(bg=common.BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", self.close)
        win.bind("<Escape>", lambda _e: self.close())
        outer = tk.Frame(win, bg=common.BG, padx=16, pady=14)
        outer.pack()
        head = tk.Frame(outer, bg=common.BG)
        head.pack(fill="x")
        self.title = tk.Label(head, text="", bg=common.BG, fg=common.TEXT,
                              font=(common.FONT, 14, "bold"))
        self.title.pack(side="left")
        for text, step in (("›", 1), ("Today", 0), ("‹", -1)):
            b = common._button(head, text, lambda s=step: self.go(s))
            b.configure(padx=10, pady=3)
            b.pack(side="right", padx=(4, 0))
        self.grid = tk.Frame(outer, bg=common.BG)
        self.grid.pack(pady=(10, 0))
        for i, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat",
                                  "Sun")):
            tk.Label(self.grid, text=name, bg=common.BG, fg=common.MUTED,
                     font=(common.FONT, 9, "bold"), width=5).grid(
                row=0, column=i, pady=(0, 4))
        self.cells = []
        for r in range(6):
            for c in range(7):
                b = tk.Button(self.grid, width=4, height=2, relief="flat",
                              highlightthickness=0,
                              bd=0, font=(common.FONT, 10), cursor="hand2",
                              activebackground=common.ACCENT,
                              activeforeground="#FFFFFF")
                b.grid(row=r + 1, column=c, padx=1, pady=1)
                self.cells.append(b)
        tk.Frame(outer, bg=common.LINE, height=1).pack(fill="x", pady=(12, 8))
        self.day_title = tk.Label(outer, text="", bg=common.BG,
                                  fg=common.TEXT, font=(common.FONT, 11,
                                                        "bold"))
        self.day_title.pack(anchor="w")
        self.items = tk.Frame(outer, bg=common.BG)
        self.items.pack(fill="x", pady=(4, 6))
        add_row = tk.Frame(outer, bg=common.BG)
        add_row.pack(fill="x")
        self.time_var = tk.StringVar()
        self.text_var = tk.StringVar()
        tk.Entry(add_row, textvariable=self.time_var, width=6, bg=common.ROW,
                 fg=common.TEXT, insertbackground=common.TEXT, relief="flat",
                 font=(common.FONT, 10)).pack(side="left", ipady=5)
        self.entry = tk.Entry(add_row, textvariable=self.text_var, width=26,
                              bg=common.ROW, fg=common.TEXT,
                              insertbackground=common.TEXT, relief="flat",
                              font=(common.FONT, 10))
        self.entry.pack(side="left", padx=6, ipady=5, fill="x", expand=True)
        self.entry.bind("<Return>", self._add)
        common._button(add_row, "+ Add", self._add, primary=True).pack(
            side="left")
        self.hint = tk.Label(outer, text="Time is optional (e.g. 9:30); "
                             "timed items remind you.", bg=common.BG,
                             fg=common.MUTED, font=(common.FONT, 8))
        self.hint.pack(anchor="w", pady=(6, 0))
        self.render()
        win.update_idletasks()
        if near:
            x, y = near
            x = max(0, min(x, win.winfo_screenwidth() - win.winfo_reqwidth()))
            y = max(0, min(y, win.winfo_screenheight() - win.winfo_reqheight()
                           - 48))
            win.geometry("+%d+%d" % (x, y))
            win.lift()
            win.focus_force()
        else:
            common._center(win)
        self.entry.focus_set()

    def go(self, step):
        if step == 0:
            today = dt.date.today()
            self.month, self.day = today.replace(day=1), today
        else:
            y, m = self.month.year, self.month.month + step
            y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
            self.month = dt.date(y, m, 1)
        self.render()

    def pick(self, day):
        self.day = day
        if day.month != self.month.month:
            self.month = day.replace(day=1)
        self.render()
        self.entry.focus_set()

    def render(self):
        data = load()
        today = dt.date.today()
        self.title.configure(text=self.month.strftime("%B %Y"))
        weeks = calendar.Calendar(0).monthdatescalendar(self.month.year,
                                                        self.month.month)
        days = [d for w in weeks for d in w]
        days += [days[-1] + dt.timedelta(days=i + 1)
                 for i in range(42 - len(days))]
        for cell, day in zip(self.cells, days):
            inside = day.month == self.month.month
            marked = day.isoformat() in data
            label = str(day.day) + ("\n•" if marked else "\n ")
            if day == self.day:
                bg, fg = common.ACCENT, "#FFFFFF"
            elif day == today:
                bg, fg = common.ROW, "#FFFFFF"
            else:
                bg, fg = common.BG, common.TEXT if inside else "#5F6676"
            cell.configure(text=label, bg=bg, fg=fg,
                           command=lambda d=day: self.pick(d))
        self.day_title.configure(text=self.day.strftime("%A, %d %B"))
        for child in self.items.winfo_children():
            child.destroy()
        items = data.get(self.day.isoformat(), [])
        if not items:
            tk.Label(self.items, text="Nothing planned.", bg=common.BG,
                     fg=common.MUTED, font=(common.FONT, 9)).pack(anchor="w")
        for i, item in enumerate(items):
            row = tk.Frame(self.items, bg=common.PANEL, padx=8, pady=5)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=item.get("time") or "—", bg=common.PANEL,
                     fg=common.MUTED, font=(common.FONT, 9), width=6,
                     anchor="w").pack(side="left")
            tk.Label(row, text=item.get("text", ""), bg=common.PANEL,
                     fg=common.TEXT, font=(common.FONT, 10), anchor="w",
                     wraplength=240, justify="left").pack(side="left",
                                                          fill="x",
                                                          expand=True)
            x = tk.Label(row, text="✕", bg=common.PANEL, fg=common.MUTED,
                         font=(common.FONT, 9), cursor="hand2")
            x.pack(side="right")
            x.bind("<Button-1>", lambda _e, i=i: self._remove(i))

    def _add(self, _e=None):
        text = self.text_var.get().strip()
        if not text:
            return
        when = parse_time(self.time_var.get())
        if when is None:
            self.hint.configure(text="That time is not clear. Try 9:30 or "
                                "14:00.", fg="#F28B82")
            return
        add(self.day, text, when)
        self.time_var.set("")
        self.text_var.set("")
        self.hint.configure(text="Time is optional (e.g. 9:30); timed items "
                            "remind you.", fg=common.MUTED)
        self.render()

    def _remove(self, index):
        remove(self.day, index)
        self.render()

    def close(self):
        CalendarWindow._open = None
        try:
            self.win.destroy()
        except Exception:
            pass


def calendar_cmd(ctrl, near=None, **_):
    CalendarWindow.show(ctrl, near)
