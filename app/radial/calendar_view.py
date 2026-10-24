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


# -- in the ring's panel ---------------------------------------------------

_view = {"month": None, "day": None}


def build(menu, frame):
    """The month, the chosen day's agenda, and the world clock."""
    CalendarPanel(menu, frame)


class CalendarPanel:
    def __init__(self, menu, frame):
        self.menu = menu
        self.s = menu.s
        today = dt.date.today()
        if _view["day"] is None:
            _view["day"] = today
            _view["month"] = today.replace(day=1)
        self.outer = frame
        menu.header(frame, "Calendar", "key 7")
        self.body = tk.Frame(frame, bg=common.PANEL)
        self.body.pack(fill="x")
        self.render()

    # month, day, agenda, clocks -----------------------------------------------

    def render(self):
        for child in self.body.winfo_children():
            child.destroy()
        m, s = self.menu, self.s
        data = load()
        today = dt.date.today()
        month, day = _view["month"], _view["day"]

        nav = tk.Frame(self.body, bg=common.PANEL)
        nav.pack(fill="x")
        tk.Label(nav, text=month.strftime("%B %Y"), bg=common.PANEL,
                 fg=common.TEXT, font=m.f(15, True)).pack(side="left")
        for text, step in (("›", 1), ("Today", 0), ("‹", -1)):
            b = m.button(nav, text, lambda st=step: self.go(st))
            b.configure(padx=int(10 * s), pady=int(3 * s), font=m.f(12))
            b.pack(side="right", padx=(int(3 * s), 0))

        grid = tk.Frame(self.body, bg=common.PANEL)
        grid.pack(fill="x", pady=(int(8 * s), 0))
        # Column 0: the ISO week number ("KW"), as German calendars show it.
        grid.columnconfigure(0, weight=0, minsize=int(30 * s))
        tk.Label(grid, text="Wk", bg=common.PANEL, fg="#5F6676",
                 font=m.f(11, True)).grid(row=0, column=0, sticky="we",
                                          pady=(0, int(4 * s)))
        for i, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat",
                                  "Sun")):
            grid.columnconfigure(i + 1, weight=1, uniform="day")
            tk.Label(grid, text=name, bg=common.PANEL, fg=common.MUTED,
                     font=m.f(11, True)).grid(row=0, column=i + 1, sticky="we",
                                              pady=(0, int(4 * s)))
        weeks = calendar.Calendar(0).monthdatescalendar(month.year,
                                                        month.month)
        for r, week in enumerate(weeks):
            tk.Label(grid, text=str(week[0].isocalendar()[1]) + "\n ",
                     bg=common.PANEL, fg="#7D8597", font=m.f(11),
                     pady=int(2 * s)).grid(row=r + 1, column=0, sticky="nsew")
            for c, d in enumerate(week):
                inside = d.month == month.month
                marked = d.isoformat() in data
                if d == day:
                    bg, fg = common.ACCENT, "#FFFFFF"
                elif d == today:
                    bg, fg = common.ROW, "#FFFFFF"
                else:
                    bg, fg = common.PANEL, common.TEXT if inside else "#5F6676"
                cell = tk.Label(grid, text=str(d.day) + ("\n•" if marked
                                                          else "\n "),
                                bg=bg, fg=fg, font=m.f(14), cursor="hand2",
                                pady=int(2 * s))
                cell.grid(row=r + 1, column=c + 1, padx=1, pady=1, sticky="nsew")
                cell.bind("<Button-1>", lambda _e, d=d: self.pick(d))

        tk.Frame(self.body, bg=common.LINE, height=1).pack(
            fill="x", pady=(int(8 * s), int(6 * s)))
        tk.Label(self.body, text="%s  ·  Week %d" % (day.strftime("%A, %d %B"),
                                          day.isocalendar()[1]), bg=common.PANEL,
                 fg=common.TEXT, font=m.f(14, True), anchor="w").pack(
            fill="x")
        items = data.get(day.isoformat(), [])
        if not items:
            tk.Label(self.body, text="Nothing planned.", bg=common.PANEL,
                     fg=common.MUTED, font=m.f(12), anchor="w").pack(fill="x")
        for i, item in enumerate(items):
            row = tk.Frame(self.body, bg=common.ROW)
            row.pack(fill="x", pady=(int(3 * s), 0))
            tk.Label(row, text=item.get("time") or "—", bg=common.ROW,
                     fg=common.MUTED, font=m.f(12), width=6,
                     anchor="w").pack(side="left", padx=(int(6 * s), 0))
            tk.Label(row, text=item.get("text", ""), bg=common.ROW,
                     fg=common.TEXT, font=m.f(13), anchor="w",
                     justify="left",
                     wraplength=m.panel_width() - int(140 * s)).pack(
                side="left", fill="x", expand=True, pady=int(4 * s))
            delete = tk.Label(row, text="Delete", bg=common.ROW,
                              fg="#F28B82", font=m.f(12), cursor="hand2",
                              padx=int(8 * s))
            delete.pack(side="right")
            delete.bind("<Button-1>", lambda _e, i=i: self.remove(i))

        add_row = tk.Frame(self.body, bg=common.PANEL)
        add_row.pack(fill="x", pady=(int(6 * s), 0))
        self.time_var = tk.StringVar()
        self.text_var = tk.StringVar()
        t = tk.Entry(add_row, textvariable=self.time_var, width=5,
                     bg=common.ROW, fg=common.TEXT, relief="flat",
                     insertbackground=common.TEXT, highlightthickness=0,
                     font=m.f(13))
        t.pack(side="left", ipady=int(4 * s))
        e = tk.Entry(add_row, textvariable=self.text_var, bg=common.ROW,
                     fg=common.TEXT, relief="flat", highlightthickness=0,
                     insertbackground=common.TEXT, font=m.f(13))
        e.pack(side="left", fill="x", expand=True, padx=int(4 * s),
               ipady=int(4 * s))
        e.bind("<Return>", self.add)
        b = m.button(add_row, "+ Add", self.add, primary=True)
        b.configure(padx=int(12 * s), pady=int(4 * s), font=m.f(12))
        b.pack(side="left")
        self.hint = tk.Label(self.body, text="Time optional (9:30). Timed "
                             "items remind you.", bg=common.PANEL,
                             fg=common.MUTED, font=m.f(11), anchor="w")
        self.hint.pack(fill="x", pady=(int(3 * s), 0))

        self.clocks()
        m.relayout()

    def clocks(self):
        from . import worldclock
        m, s = self.menu, self.s
        tk.Frame(self.body, bg=common.LINE, height=1).pack(
            fill="x", pady=(int(8 * s), int(6 * s)))
        tk.Label(self.body, text="World clock  ·  click a city to change it",
                 bg=common.PANEL, fg=common.MUTED, font=m.f(11),
                 anchor="w").pack(fill="x")
        grid = tk.Frame(self.body, bg=common.PANEL)
        grid.pack(fill="x", pady=(int(4 * s), 0))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        labels = []
        for slot, name in enumerate(worldclock.chosen()):
            tile = tk.Frame(grid, bg=common.ROW, cursor="hand2",
                            padx=int(8 * s), pady=int(5 * s))
            tile.grid(row=slot // 2, column=slot % 2, sticky="we",
                      padx=(0 if slot % 2 == 0 else int(3 * s), 0),
                      pady=(0, int(3 * s)))
            city = tk.Label(tile, text=name, bg=common.ROW, fg=common.MUTED,
                            font=m.f(12), anchor="w")
            city.pack(fill="x")
            time_l = tk.Label(tile, text="", bg=common.ROW, fg="#FFFFFF",
                              font=m.f(21, True), anchor="w")
            time_l.pack(fill="x")
            for w in (tile, city, time_l):
                w.bind("<Button-1>", lambda _e, sl=slot: self.pick_city(sl))
            labels.append((name, time_l))

        def tick():
            try:
                if not grid.winfo_exists():
                    return
                for name, label in labels:
                    hhmm, wday, rel = worldclock.describe(name)
                    label.configure(text="%s  %s" % (hhmm, rel or wday))
            except tk.TclError:
                return
            grid.after(15000, tick)

        tick()

    def pick_city(self, slot):
        from . import worldclock
        menu = self.menu

        def build_picker(frame):
            s = menu.s
            menu.header(frame, "Choose a city", close=True)
            query = tk.StringVar()
            entry = tk.Entry(frame, textvariable=query, bg=common.ROW,
                             fg=common.TEXT, relief="flat",
                             highlightthickness=0,
                             insertbackground=common.TEXT, font=menu.f(11))
            entry.pack(fill="x", ipady=int(4 * s), pady=(0, int(6 * s)))
            box = tk.Listbox(frame, height=10, bg=common.ROW, fg=common.TEXT,
                             selectbackground=common.ACCENT,
                             selectforeground="#FFFFFF", relief="flat",
                             highlightthickness=0, activestyle="none",
                             font=menu.f(12))
            box.pack(fill="x")
            names = sorted(worldclock.CITIES)

            def fill(*_a):
                box.delete(0, "end")
                q = query.get().strip().lower()
                for n in names:
                    if q in n.lower():
                        hhmm, _w, rel = worldclock.describe(n)
                        box.insert("end", "%s   %s%s" % (
                            n, hhmm, ("  " + rel) if rel else ""))

            def pick(_e=None):
                sel = box.curselection()
                if not sel:
                    sel = (0,) if box.size() else ()
                if not sel:
                    return
                name = box.get(sel[0]).split("   ")[0]
                worldclock.choose(slot, name)
                menu.select(menu.selected)

            query.trace_add("write", fill)
            box.bind("<Double-Button-1>", pick)
            box.bind("<ButtonRelease-1>", pick)
            entry.bind("<Return>", pick)
            menu.note(frame, "Daylight saving is followed automatically.")
            fill()
            entry.focus_set()

        menu.show_view(build_picker, pinned=True, name="cities")

    # actions -----------------------------------------------------------------

    def go(self, step):
        if step == 0:
            today = dt.date.today()
            _view["month"], _view["day"] = today.replace(day=1), today
        else:
            month = _view["month"]
            y, mth = month.year, month.month + step
            y, mth = y + (mth - 1) // 12, (mth - 1) % 12 + 1
            _view["month"] = dt.date(y, mth, 1)
        self.render()

    def pick(self, day):
        _view["day"] = day
        if day.month != _view["month"].month:
            _view["month"] = day.replace(day=1)
        self.render()

    def add(self, _e=None):
        text = self.text_var.get().strip()
        if not text:
            return
        when = parse_time(self.time_var.get())
        if when is None:
            self.hint.configure(text="That time is not clear. Try 9:30.",
                                fg="#F28B82")
            return
        add(_view["day"], text, when)
        self.render()

    def remove(self, index):
        remove(_view["day"], index)
        self.render()


def next_item(now=None):
    """The next thing on the agenda, short, for the middle of the ring:
    a timed item later today, else anything left today, else the first
    item tomorrow. "" when there is nothing."""
    now = now or dt.datetime.now()
    data = load()
    today = data.get(now.date().isoformat(), [])
    clock = now.strftime("%H:%M")
    for item in today:
        if item.get("time") and item["time"] >= clock:
            return "%s %s" % (item["time"], item["text"])
    for item in today:
        if not item.get("time"):
            return "Today: %s" % item["text"]
    tomorrow = data.get((now.date() + dt.timedelta(days=1)).isoformat(), [])
    if tomorrow:
        item = tomorrow[0]
        return "Tomorrow %s%s" % (item["time"] + " " if item.get("time")
                                  else "", item["text"])
    return ""
