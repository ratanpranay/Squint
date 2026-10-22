"""The Google setup checklist.

Three steps, each with a button that opens the exact page that fixes it and
a dot that says whether it is actually done — checked against Google, not
assumed. The user does the parts only they can do (create a key, press
Enable, add a card) and the app does the finding-out.

The reason this is a checklist rather than a wizard: a wizard walks you
forward and has no idea whether any of it worked. Every failure here comes
back from Google as a bare 403 whatever the cause, so the value is entirely
in telling apart "the API is off", "the key does not include it" and "there
is no card on the account" — and pointing at the right page for each.
"""
import tkinter as tk
import webbrowser

from . import config, setup_google, theme as theme_mod
from .ui_kit import Field, PillButton, ScrollArea, Surface, label

CFG = config.CONFIG


class GoogleSetup(tk.Toplevel):
    """Opened from Settings. Saves the key itself when it works."""

    def __init__(self, master, palette=None, on_saved=None):
        super().__init__(master)
        self.palette = palette or theme_mod.resolve("light")
        self.on_saved = on_saved
        p = self.palette
        self.title("Set up Google")
        self.configure(bg=p["window"])
        # Only ever up. The type in here follows the page's
        # scale, and a page drawn small leaves these windows
        # with more room than they need — which is fine. Taking
        # the window down with it is not: the rows inside have
        # widths of their own and they stop fitting.
        scale = max(1.0, min(1.4, theme_mod.PAGE_SCALE))
        self.geometry("%dx%d" % (720 * scale, 680 * scale))
        self.minsize(int(640 * scale), int(560 * scale))
        self._checking = False

        root = tk.Frame(self, bg=p["window"])
        root.pack(fill="both", expand=True, padx=24, pady=(20, 18))

        label(root, p, "Set up Google", size=17, weight="bold",
              display=True).pack(anchor="w")
        label(root, p,
              "Five steps, about ten minutes, done once. Each button opens "
              "the page for that step; press Check and save at any point "
              "and the dots turn green as Google confirms them.",
              size=9, dim=True, wraplength=620,
              justify="left").pack(anchor="w", pady=(6, 14))

        # The Check button and the status line are pinned to the bottom,
        # outside the scroll. A step that fails prints a paragraph of
        # explanation and grows its card; with everything in one column
        # that pushed the only button in the window off the bottom edge,
        # at exactly the moment the user needed it.
        footer = tk.Frame(root, bg=p["window"])
        footer.pack(side="bottom", fill="x", pady=(14, 0))
        self.check_button = PillButton(
            footer, "Check and save", command=self.check, palette=p,
            kind="primary", height=38)
        self.check_button.pack(side="left")
        PillButton(footer, "Close", command=self.destroy, palette=p,
                   kind="ghost", height=38).pack(side="right")
        self.status = label(root, p, "", size=10, dim=True, wraplength=560,
                            justify="left")
        self.status.pack(side="bottom", anchor="w", pady=(12, 0))

        area = ScrollArea(root, p)
        area.pack(fill="both", expand=True)
        column = area.body
        self.scroll = area

        self._picture_card(column)

        # Shown in the order they are done in the console, which is not
        # the order they are checked in: the key's API list only offers
        # APIs already switched on, so the key comes after both, and
        # switching one on is what first asks for the project and card.
        self.steps = setup_google.steps()
        by_name = {step.name: step for step in self.steps}
        self.project_row = self._step_row(column, 0, setup_google.PROJECT)
        order = [by_name["Cloud Translation API"], by_name["Cloud Vision API"],
                 by_name["An API key"]]
        rows = {}
        for index, step in enumerate(order, start=1):
            rows[step.name] = self._step_row(column, index, step)
        self.rows = [rows[step.name] for step in self.steps]

        # -- the key ---------------------------------------------------
        key_card = Surface(column, p, radius=16, padding=20, bg=p["window"])
        key_card.pack(fill="x", pady=(4, 0), padx=(0, 4))
        body = key_card.body
        label(body, p, "Paste the key here", size=11, weight="bold",
              bg=p["surface"]).pack(anchor="w")
        self.var_key = tk.StringVar(value=CFG.get("google_api_key", ""))
        Field(body, p, textvariable=self.var_key, width=46, height=38,
              bg=p["surface"], fill=p["field_on_card"]).pack(anchor="w",
                                                             pady=(10, 0))
        label(body, p,
              "Both allowances are free and separate: 500,000 characters "
              "translated and 1,000 screenshots read, every month. Squint "
              "shows what is left of each in Settings.",
              size=9, dim=True, wraplength=560, justify="left",
              bg=p["surface"]).pack(anchor="w", pady=(12, 0))

        self._upgrade_row(column, len(order) + 1)

        self.transient(master)
        self.after(120, area.bind_wheel_recursive)
        if self.var_key.get():
            # A key is already saved, so the interesting question is not
            # "what do I do" but "what is still broken".
            self.after(250, self.check)

    # -- the picture guide ----------------------------------------------
    # The checklist says which page; the picture shows which button on
    # it. Offered first, with a glimpse of it, because the glimpse is
    # what tells somebody there are screenshots behind the button.
    THUMB = (132, 96)

    def _picture_card(self, parent):
        try:
            from . import ui_guide
            if not ui_guide.available("google"):
                return
        except Exception:
            return
        p = self.palette
        card = Surface(parent, p, radius=16, padding=14, bg=p["window"])
        card.pack(fill="x", pady=(0, 10), padx=(0, 4))
        body = card.body
        opener = self._open_picture_guide

        thumb = self._thumbnail()
        if thumb is not None:
            self._thumb_photo = thumb
            shot = tk.Label(body, image=thumb, bd=0, cursor="hand2",
                            bg=p["surface"], highlightthickness=1,
                            highlightbackground=p.get("line", p["text_faint"]))
            shot.pack(side="left", padx=(0, 14))
            shot.bind("<Button-1>", lambda _e: opener())

        PillButton(body, "Open picture guide", command=opener, palette=p,
                   kind="primary", height=34,
                   bg=p["surface"]).pack(side="right")
        words = tk.Frame(body, bg=p["surface"])
        words.pack(side="left", fill="x", expand=True)
        label(words, p, "Step-by-step picture guide", size=11,
              weight="bold", bg=p["surface"]).pack(anchor="w")
        label(words, p,
              "Every screen of the Google console, with the button to "
              "press circled. Opens beside this window, so you can follow "
              "it while you tick the steps below.",
              size=9, dim=True, wraplength=300, justify="left",
              bg=p["surface"]).pack(anchor="w", pady=(4, 0))

    def _thumbnail(self):
        """The top of the guide, small. None if it cannot be drawn."""
        try:
            from PIL import Image, ImageTk
            from . import ui_guide
            path = ui_guide.asset(ui_guide.GUIDES["google"][0])
            picture = Image.open(path).convert("RGB")
            w, h = self.THUMB
            # The top-left of the guide: the title and the first steps,
            # which is what reads as "a guide" at this size.
            crop = picture.crop((0, 0, picture.width // 2,
                                 int(picture.width // 2 * h / w)))
            crop = crop.resize((w, h), Image.LANCZOS)
            return ImageTk.PhotoImage(crop, master=self)
        except Exception:
            return None

    def _open_picture_guide(self):
        try:
            from . import ui_guide
            ui_guide.show(self.master, "google", palette=self.palette)
        except Exception:
            pass

    # -- the last step: keep it working ----------------------------------
    def _upgrade_row(self, parent, index):
        from . import google_billing
        from .ui_kit import Switch
        p = self.palette
        step = setup_google.UPGRADE
        row = self._step_row(parent, index, step)
        body = row["body"]
        line = tk.Frame(body, bg=p["surface"])
        line.pack(anchor="w", pady=(10, 0))
        self.var_upgraded = tk.BooleanVar(value=google_billing.is_upgraded())
        Switch(line, p, variable=self.var_upgraded,
               command=self._upgraded_changed,
               bg=p["surface"]).pack(side="left")
        label(line, p, "Done — I upgraded", size=9,
              bg=p["surface"]).pack(side="left", padx=(8, 0))
        self.upgrade_row = row
        self._paint_upgrade()

    def _upgraded_changed(self, *_):
        from . import google_billing
        google_billing.mark_upgraded(bool(self.var_upgraded.get()))
        self._paint_upgrade()

    def _paint_upgrade(self):
        step = setup_google.UPGRADE
        if self.var_upgraded.get():
            step.state, step.detail = "ok", ""
        else:
            step.state, step.detail = "waiting", ""
        self._paint_step(self.upgrade_row, step)

    # -- a single step -------------------------------------------------
    def _step_row(self, parent, index, step):
        p = self.palette
        card = Surface(parent, p, radius=16, padding=18, bg=p["window"])
        card.pack(fill="x", pady=(0, 10), padx=(0, 4))
        body = card.body

        head = tk.Frame(body, bg=p["surface"])
        head.pack(fill="x")
        dot = tk.Label(head, text="○", bg=p["surface"], fg=p["text_faint"],
                       font=theme_mod.font(self, 12))
        dot.pack(side="left", padx=(0, 10))
        label(head, p, "%d. %s" % (index + 1, step.name), size=11,
              weight="bold", bg=p["surface"]).pack(side="left")
        PillButton(head, step.action,
                   command=lambda url=step.url: webbrowser.open(url),
                   palette=p, kind="secondary", height=34,
                   bg=p["surface"]).pack(side="right")

        label(body, p, step.why, size=9, dim=True, wraplength=540,
              justify="left", bg=p["surface"]).pack(anchor="w",
                                                    pady=(8, 0))
        detail = label(body, p, "", size=9, dim=True, wraplength=540,
                       justify="left", bg=p["surface"])
        return {"dot": dot, "detail": detail, "body": body, "card": card}

    def _paint_step(self, row, step):
        p = self.palette
        marks = {"ok": ("●", p["success"]),
                 "failed": ("●", p["danger"]),
                 "waiting": ("○", p["text_faint"])}
        glyph, colour = marks.get(step.state, marks["waiting"])
        row["dot"].configure(text=glyph, fg=colour)
        if step.detail:
            row["detail"].configure(
                text=step.detail,
                fg=p["danger"] if step.state == "failed" else p["text_dim"])
            row["detail"].pack(anchor="w", pady=(6, 0))
        else:
            row["detail"].pack_forget()

    def _scroll_to(self, row):
        try:
            self.update_idletasks()
            box = self.scroll.canvas.bbox("all")
            if not box:
                return
            total = max(1, box[3] - box[1])
            top = max(0, row["card"].winfo_y() - 8)
            self.scroll.canvas.yview_moveto(min(1.0, top / float(total)))
        except Exception:
            pass

    # -- checking ------------------------------------------------------
    def check(self):
        if self._checking:
            return
        self._checking = True
        self.check_button.set_enabled(False)
        self.status.configure(text="Asking Google…",
                              fg=self.palette["text_dim"])
        key = "".join(self.var_key.get().split())
        self.var_key.set(key)

        import threading
        threading.Thread(target=self._work, args=(key,),
                         daemon=True).start()

    def _work(self, key):
        try:
            results = setup_google.check(key)
        except Exception as exc:
            results = None
            self.after(0, self._failed, str(exc)[:200])
            return
        self.after(0, self._done, results, key)

    def _done(self, results, key):
        self._checking = False
        try:
            self.check_button.set_enabled(True)
        except Exception:
            pass
        self.steps = results
        for row, step in zip(self.rows, results):
            self._paint_step(row, step)
        self._paint_step(self.project_row,
                         setup_google.project_state(results))
        # Put the thing that still needs doing in front of the user rather
        # than leaving them to scroll for the red dot.
        for row, step in zip(self.rows, results):
            if step.state == "failed":
                self._scroll_to(row)
                break
        ok, message = setup_google.summary(results)

        # The key is saved when it does something, not merely when it is
        # typed. Saving a rejected key leaves the app looking configured
        # and quietly using the free services instead.
        if any(step.ok for step in results[1:]):
            CFG.set("google_api_key", key)
            try:
                from . import google_billing
                google_billing.key_saved(key)
                google_billing.note_working()
            except Exception:
                pass
            if callable(self.on_saved):
                try:
                    self.on_saved()
                except Exception:
                    pass
            message += "  Key saved."
            if ok and not self.var_upgraded.get():
                message += ("  Last step: upgrade in Billing so the key "
                            "keeps working after 90 days.")
        self.status.configure(
            text=message,
            fg=self.palette["success"] if ok else self.palette["text_dim"])

    def _failed(self, message):
        self._checking = False
        try:
            self.check_button.set_enabled(True)
        except Exception:
            pass
        self.status.configure(text=message, fg=self.palette["danger"])
