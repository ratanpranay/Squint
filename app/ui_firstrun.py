"""The first-run screens: two short questions before the app is used.

Three screens — welcome, language, key. The target-language choice and the
translation key never touch Windows or download anything; a permission
prompt before the app has done anything at all is a worse first impression
than not having it yet. The one thing on the language screen that can ask
for that is opt-in and clearly marked: a checklist of "languages you often
read", off by default, and turning one on installs that language's Windows
text-recognition pack in the background — one permission prompt covering
everything picked, one dism.exe commit rather than one per language (see
win_langpack.install_many), while setup carries on to the next screen. Left
off, or declined, or the machine refuses it: nothing breaks, and the same
offer still appears later, just-in-time, from Settings — see
MainWindow._langpack_row.

What this collects: which language translations should come out in
(target_lang, already a setting — this just asks for it up front instead of
defaulting silently to English), which languages (if any) to fetch a
Windows pack for, and an optional translation key. Each is saved as its
screen is left, not held until the end, so closing the window partway
through keeps whatever was already filled in or already started.

Shown once. "Finish" and closing the window (the X, or Escape) both count
as done — asked once, never nagged about again. There is no wrong way to
leave this window.
"""
import queue
import threading
import time
import tkinter as tk
import traceback

from . import config, platform_util, theme as theme_mod, win_langpack
from .langs import target_choices, name_for, code_for_name
from .ui_kit import (Dropdown, Field, PillButton, ProgressBar, ScrollArea,
                     Surface, Switch, label)

CFG = config.CONFIG


def _log(message):
    """Same shape as main.log(), kept local rather than imported.

    Not imported from .main because that module is what creates this
    window in the first place — importing it back would work (it is
    already loaded by the time _show_first_run runs) but there is no
    reason to depend on that ordering for four lines.
    """
    try:
        with open(config.log_path(), "a", encoding="utf-8") as fh:
            fh.write(message.rstrip() + "\n")
    except Exception:
        pass

WELCOME_BODY = (
    "Squint reads text off your screen and translates it in place — a "
    "screenshot, a photo, a PDF, anything you can select. Two short "
    "questions and it is ready."
)

LANGUAGE_BODY = (
    "This is what Squint translates into. It reads any language back over "
    "the internet once a key is added on the next screen — nothing on "
    "this screen is required for that."
)

PACKS_BODY = (
    "Optional. Turning one on asks Windows to install that language's "
    "text-recognition pack — free, a few minutes, one permission prompt "
    "covering everything picked here. It happens in the background: "
    "setup carries on to the next screen while it downloads, and Squint "
    "keeps reading over the internet the whole time either way. Leave "
    "these off if you are not sure — Squint offers the same thing later, "
    "only when a specific language actually needs it."
)

KEY_INTRO = (
    "Optional, and it is what makes Squint work at all — on this PC, on "
    "one with no language packs installed, and on a Mac. Without a key "
    "the app falls back to free services, which are rate-limited and "
    "plainer."
)

KEY_NOTE = (
    "A key is not the same as a language pack. The key does the reading "
    "and translating over the internet. A Windows pack lets one computer "
    "read one language by itself, offline — that is a bonus you can add "
    "later, in Settings, and you need a key either way."
)

GEMINI_URL = "https://aistudio.google.com/apikey"
# Google's key is walked through with the same multi-step checklist
# Settings uses (GoogleSetup) rather than a bare link — it is two API
# toggles and a key, in two different corners of the console, and every
# failure along the way arrives as the same bare 403. DeepL is one page,
# so a link is the whole answer there.
DEEPL_URL = "https://www.deepl.com/en/pro-api"


class FirstRunSetup(tk.Toplevel):
    """Three screens, shown once. See module docstring."""

    STEPS = ("welcome", "language", "key")

    # Shown first on the language checklist, ahead of everything else
    # Windows offers a pack for: the scripts most likely to actually need
    # one, since a misread there is a wrong character rather than a wrong
    # accent. Everything else Windows offers is one tap away behind "More
    # languages…" rather than filling the screen with all thirty-odd of
    # them.
    SHORTLIST_TAGS = ("zh-CN", "ja-JP", "ko-KR", "ru-RU", "ar-SA", "de-DE")

    def __init__(self, master, on_done=None):
        super().__init__(master)
        self.on_done = on_done
        # Deliberately the light palette, like the main window — see the
        # note in ui_main.MainWindow.__init__. This window exists for one
        # sitting near the start of using the app; it should look the same
        # for everyone rather than following a theme nobody has set yet.
        self.palette = theme_mod.resolve("light")
        p = self.palette
        self.title("Welcome to Squint")
        self.configure(bg=p["window"])
        # Wide enough for a field and a button side by side on the key
        # screen without either being squeezed — measured, not guessed,
        # after the key rows grew a second and third "get one" button (see
        # _screen_key). The language screen's own overflow risk (an
        # expanded pack checklist) is handled separately, by scrolling
        # rather than by width.
        # Only ever up. The type in here follows the page's
        # scale, and a page drawn small leaves these windows
        # with more room than they need — which is fine. Taking
        # the window down with it is not: the rows inside have
        # widths of their own and they stop fitting.
        scale = max(1.0, min(1.4, theme_mod.PAGE_SCALE))
        self.geometry("%dx%d" % (700 * scale, 560 * scale))
        self.minsize(int(620 * scale), int(520 * scale))
        self._closing = False
        self._step = 0

        self.var_target = tk.StringVar(
            value=name_for(CFG.get("target_lang", "en")))
        self.var_gemini = tk.StringVar(value=CFG.get("gemini_api_key", ""))
        self.var_google = tk.StringVar(value=CFG.get("google_api_key", ""))
        self.var_deepl = tk.StringVar(value=CFG.get("deepl_api_key", ""))

        # -- language-pack checklist state ------------------------------
        # Populated once, off the main thread (available_packs() runs
        # PowerShell), and kept across re-renders: the widgets get
        # rebuilt every time _render() swaps the body, but a BooleanVar
        # is not a child of any widget and survives that on its own, so
        # there is no reason to ask Windows twice.
        self._packs_loaded = False
        self._packs_loading = False
        self._available_packs = []          # [(tag, capability)], not
                                             # yet installed
        self._pack_vars = {}                # tag -> BooleanVar
        self._show_all_packs = False
        self._pack_install_started = False
        # Set the instant _pack_install_done runs, checked at the top of
        # _update_pack_progress — the ticker thread and the install thread
        # both post to the same queue, and the ticker's posts go through
        # real file I/O (win_langpack.progress reads a log file) while the
        # install call in tests (and sometimes in reality, e.g. an
        # "already installed" batch) can finish first. Without this flag
        # a stale "Installing…" message processed after the real result
        # can overwrite it, since _pump() drains the queue strictly in
        # arrival order rather than logical order.
        self._pack_install_finished = False

        # Cross-thread plumbing for the two background jobs above
        # (loading the pack list, running the install) — the same
        # queue-and-poll shape MainWindow uses, at the size this window
        # actually needs.
        self._ui_queue = queue.Queue()

        # A ScrollArea rather than a plain frame — "More languages…" on
        # the language screen can push the pack checklist past any fixed
        # window height (30-odd rows once expanded), and a window that
        # only grows by being dragged bigger, with the rest of it silently
        # clipped and no hint that there is more below, is worse than a
        # scrollbar.
        self._body_area = ScrollArea(self, p)
        self._body_area.pack(fill="both", expand=True, padx=(32, 28),
                             pady=(28, 0))
        self._body = self._body_area.body

        # Lives between the body and the footer, outside both — so a
        # background install keeps reporting itself here no matter which
        # screen setup has since moved on to, and survives _render()
        # clearing the body out from under it.
        self._progress_row = tk.Frame(self, bg=p["window"])
        self._progress_row.pack(fill="x", padx=32, pady=(0, 4))
        self._progress_bar = ProgressBar(self._progress_row, p)
        self._progress_bar.pack(fill="x")
        self._progress_label = label(
            self._progress_row, p, "", size=9, dim=True)
        self._progress_label.pack(anchor="w", pady=(4, 0))

        footer = tk.Frame(self, bg=p["window"])
        footer.pack(fill="x", padx=32, pady=(0, 24))
        self._step_label = label(footer, p, "", size=9, dim=True)
        self._step_label.pack(side="left")
        self.next_button = PillButton(
            footer, "Continue", command=self._next, palette=p,
            kind="primary", height=38)
        self.next_button.pack(side="right")
        self.back_button = PillButton(
            footer, "Back", command=self._back, palette=p,
            kind="ghost", height=38)

        self.protocol("WM_DELETE_WINDOW", self._skip)
        # Deliberately not transient(master): master is Controller.root,
        # which is permanently withdrawn (see Controller.__init__) and
        # never shown as a window in its own right. A window transient to
        # one that is never mapped can end up with no taskbar entry of its
        # own on Windows, which combined with not being raised leaves it
        # with no way back if it opens behind something else — invisible
        # and unreachable at once. MainWindow itself is built the same
        # way, transient to nothing, for the same reason.
        self._render()

        # This is the one window in the app that has to appear with
        # nobody having just clicked anything — every other dialog opens
        # in response to a click, at which point the app already has
        # focus. Windows in particular can refuse to foreground a window
        # from a process the user did not just interact with, so this
        # asks properly (lift + focus + the topmost kick already used for
        # MainWindow.show()) and then checks its own work, the same way
        # Controller._confirm_visible does for the main window.
        self.lift()
        try:
            self.focus_force()
        except Exception:
            pass
        platform_util.raise_to_front(self)
        self.after(400, self._confirm_visible)
        self._pump_id = self.after(80, self._pump)

    def _confirm_visible(self):
        try:
            viewable = bool(self.winfo_viewable())
        except Exception:
            return
        _log("first-run  : viewable=%s" % viewable)
        if not viewable:
            platform_util.raise_to_front(self)
            _log("first-run  : forced to front")

    # -- cross-thread plumbing, for the pack list and the install -------
    def _post(self, func, *args):
        """Call `func(*args)` on the Tk thread. Safe from any thread."""
        self._ui_queue.put((func, args))

    def _pump(self):
        try:
            while True:
                func, args = self._ui_queue.get_nowait()
                try:
                    func(*args)
                except Exception:
                    pass
        except queue.Empty:
            pass
        except Exception:
            pass
        if self._closing:
            return
        try:
            self._pump_id = self.after(80, self._pump)
        except Exception:
            pass

    # -- navigation ------------------------------------------------------
    def _render(self):
        for child in self._body.winfo_children():
            child.destroy()
        name = self.STEPS[self._step]
        getattr(self, "_screen_%s" % name)(self._body)
        # Each screen starts scrolled to the top — otherwise leaving the
        # language screen part-way down its (possibly expanded) list and
        # coming back to it, or moving on to the key screen, would carry
        # that scroll position over onto content it does not belong to.
        try:
            self._body_area.canvas.yview_moveto(0)
        except Exception:
            pass
        self._step_label.configure(
            text="Step %d of %d" % (self._step + 1, len(self.STEPS)))
        if self._step == 0:
            self.back_button.pack_forget()
        else:
            self.back_button.pack(side="left")
        self.next_button.configure_text(
            "Finish" if self._step == len(self.STEPS) - 1 else "Continue")
        # Wheel events only reach whatever widget is under the pointer, so
        # each freshly-built screen's widgets need their own forwarding —
        # same call Settings and the key-checklist dialog make after
        # building their own scrollable content.
        self.after(120, self._body_area.bind_wheel_recursive)

    def _back(self):
        if self._step == 0:
            return
        self._save_step()
        self._step -= 1
        self._render()

    def _next(self):
        self._save_step()
        if self._step >= len(self.STEPS) - 1:
            self._complete()
            return
        self._step += 1
        self._render()

    def _skip(self):
        """Closing the window early. Whatever was already entered is kept —
        each screen saves itself before this ever runs on the current one."""
        self._save_step()
        self._complete()

    def _complete(self):
        if self._closing:
            return
        self._closing = True
        CFG.set("setup_complete", True)
        # A pack install started from the language screen may still be
        # running — that is fine and deliberate (see the module
        # docstring), it just means nothing here should go on trying to
        # paint progress into a window that is about to stop existing.
        try:
            self.after_cancel(self._pump_id)
        except Exception:
            pass
        try:
            self.destroy()
        finally:
            if callable(self.on_done):
                try:
                    self.on_done()
                except Exception:
                    pass

    def _save_step(self):
        name = self.STEPS[self._step]
        saver = getattr(self, "_save_%s" % name, None)
        if callable(saver):
            saver()

    def _save_welcome(self):
        pass

    def _save_language(self):
        try:
            CFG.set("target_lang", code_for_name(self.var_target.get()))
        except Exception:
            pass
        self._start_pack_install()

    def _save_key(self):
        for var, key in ((self.var_gemini, "gemini_api_key"),
                         (self.var_google, "google_api_key"),
                         (self.var_deepl, "deepl_api_key")):
            value = "".join(var.get().split())
            if value:
                CFG.set(key, value)

    # -- screens -----------------------------------------------------
    def _screen_welcome(self, body):
        p = self.palette
        label(body, p, "Welcome to Squint", size=20, weight="bold",
              display=True).pack(anchor="w")
        label(body, p, WELCOME_BODY, size=11, dim=True, wraplength=520,
              justify="left").pack(anchor="w", pady=(10, 0))

    def _screen_language(self, body):
        p = self.palette
        label(body, p, "Which language do you read?", size=20,
              weight="bold", display=True).pack(anchor="w")
        label(body, p, LANGUAGE_BODY, size=11, dim=True, wraplength=520,
              justify="left").pack(anchor="w", pady=(10, 18))
        names = [n for _c, n in target_choices()]
        if self.var_target.get() not in names:
            self.var_target.set(names[0] if names else "English")
        Dropdown(body, p, names, value=self.var_target.get(),
                 command=self.var_target.set, width=260,
                 height=Dropdown.HEIGHT).pack(anchor="w")

        # A Mac reads every language already (see win_langpack's own
        # docstring) — this whole idea is Windows-specific, so it simply
        # is not there to skip on a Mac rather than being shown disabled.
        if not platform_util.IS_WINDOWS:
            return
        label(body, p, "Languages you often read on screen", size=11,
              weight="bold").pack(anchor="w", pady=(24, 4))
        label(body, p, PACKS_BODY, size=9, dim=True, wraplength=520,
              justify="left").pack(anchor="w", pady=(0, 10))
        self._pack_area = tk.Frame(body, bg=p["window"])
        self._pack_area.pack(fill="x")
        if self._packs_loaded:
            self._render_pack_grid()
        else:
            label(self._pack_area, p,
                  "Checking what this PC can already read…", size=9,
                  dim=True).pack(anchor="w")
            if not self._packs_loading:
                self._packs_loading = True
                threading.Thread(target=self._load_packs,
                                 daemon=True).start()

    # -- the language-pack checklist -------------------------------------
    def _load_packs(self):
        try:
            packs = win_langpack.available_packs()
        except Exception:
            packs = []
        self._post(self._packs_ready, packs)

    def _packs_ready(self, packs):
        self._packs_loading = False
        self._packs_loaded = True
        self._available_packs = [(tag, capability) for tag, capability,
                                 installed in packs if not installed]
        for tag, _capability in self._available_packs:
            self._pack_vars.setdefault(tag, tk.BooleanVar(value=False))
        if self.STEPS[self._step] == "language":
            self._render_pack_grid()

    def _render_pack_grid(self):
        area = getattr(self, "_pack_area", None)
        if area is None or not area.winfo_exists():
            return
        for child in area.winfo_children():
            child.destroy()
        p = self.palette
        if not self._available_packs:
            label(area, p, "This PC already reads every language Windows "
                          "offers a pack for.", size=9, dim=True,
                  wraplength=520, justify="left").pack(anchor="w")
            return
        from .ui_main import MainWindow
        shortlist = [item for item in self._available_packs
                    if item[0] in self.SHORTLIST_TAGS]
        rest = [item for item in self._available_packs
               if item[0] not in self.SHORTLIST_TAGS]
        shown = self._available_packs if (self._show_all_packs or
                                          not shortlist) else shortlist

        grid = tk.Frame(area, bg=p["window"])
        grid.pack(fill="x")
        for index, (tag, _capability) in enumerate(shown):
            row = tk.Frame(grid, bg=p["window"])
            row.grid(row=index // 2, column=index % 2, sticky="w",
                     padx=(0, 20), pady=4)
            Switch(row, p, variable=self._pack_vars[tag]).pack(side="left")
            label(row, p, MainWindow._pack_name(tag) or tag,
                  size=10).pack(side="left", padx=(9, 0))
        if shortlist and rest and not self._show_all_packs:
            PillButton(area, "More languages…",
                       command=self._show_more_packs, palette=p,
                       kind="ghost", height=32).pack(anchor="w", pady=(10, 0))
        # "More languages…" can add thirty-odd rows well past what any
        # reasonable window height shows at once — this is the one screen
        # that actually needs the scrollbar the body sits in, so make sure
        # wheel events reach these specific new rows too.
        self.after(120, self._body_area.bind_wheel_recursive)

    def _show_more_packs(self):
        self._show_all_packs = True
        self._render_pack_grid()

    def _start_pack_install(self):
        if self._pack_install_started or not platform_util.IS_WINDOWS:
            return
        capabilities = [capability for tag, capability
                        in self._available_packs
                        if self._pack_vars.get(tag) and
                        self._pack_vars[tag].get()]
        if not capabilities:
            return
        self._pack_install_started = True
        self._progress_label.configure(text="Starting…",
                                       fg=self.palette["text_dim"])
        threading.Thread(target=self._run_pack_install,
                         args=(capabilities,), daemon=True).start()

    def _run_pack_install(self, capabilities):
        """Runs entirely off the Tk thread — win_langpack.install_many()
        blocks on the elevated process for as long as Windows takes,
        which is minutes. A second thread polls the same progress log
        install() has always used and posts a tick roughly once a
        second; neither thread touches a widget directly, both go
        through _post."""
        started = time.time()
        stop = threading.Event()

        def tick():
            while not stop.is_set():
                self._post(self._update_pack_progress,
                           win_langpack.progress(), started)
                stop.wait(1.0)

        ticker = threading.Thread(target=tick, daemon=True)
        ticker.start()
        try:
            results = win_langpack.install_many(capabilities)
        except Exception:
            results = {c: (False, "") for c in capabilities}
        finally:
            stop.set()
        self._post(self._pack_install_done, results)

    def _update_pack_progress(self, percent, started):
        if not self.winfo_exists() or self._pack_install_finished:
            return
        elapsed = int(time.time() - started)
        clock = "%d:%02d" % (elapsed // 60, elapsed % 60)
        if percent is None:
            # DISM says nothing for the first stretch while it works out
            # what it is doing (see win_langpack.progress) — a sliver
            # rather than an empty-looking bar says something is
            # happening without claiming to know how much.
            self._progress_bar.set(0.02)
            self._progress_label.configure(
                text="Installing language packs — %s elapsed" % clock)
        else:
            self._progress_bar.set(percent / 100.0)
            self._progress_label.configure(
                text="Installing language packs — %d%%, %s elapsed"
                % (percent, clock))

    def _pack_install_done(self, results):
        self._pack_install_finished = True
        if not self.winfo_exists():
            return
        self._progress_bar.set(0.0)
        from .ui_main import MainWindow
        installed = []
        for capability, (ok, _message) in results.items():
            if not ok:
                continue
            found = win_langpack.CAPABILITY.match(capability)
            tag = found.group(2) if found else ""
            installed.append(MainWindow._pack_name(tag) or tag)
        if installed:
            self._progress_label.configure(
                text="Installed: %s." % ", ".join(installed),
                fg=self.palette["success"])
        else:
            # Declined, refused by this edition of Windows, or a company
            # policy that just says no — any of those is a reasonable
            # outcome and not an error. Squint keeps working over the
            # internet regardless, and the same offer comes back later,
            # just-in-time, from Settings.
            self._progress_label.configure(text="")

    def _screen_key(self, body):
        p = self.palette
        label(body, p, "Add one translation key", size=20, weight="bold",
              display=True).pack(anchor="w")
        label(body, p, KEY_INTRO, size=11, dim=True, wraplength=520,
              justify="left").pack(anchor="w", pady=(10, 16))

        # Each row's "get one" affordance fits how many clicks that key
        # actually takes: Gemini is one page and a button, Google is two
        # API toggles and a key spread across two corners of the console
        # (walked by the same checklist Settings uses), and DeepL is one
        # page, same as Gemini.
        #
        # Label above, field-and-button below — not the three-across row
        # this used to be. That fit Gemini alone; "Set up Google…" next to
        # a full-width field ran the row past this window's fixed 620px
        # (measured, not guessed — a plain side-by-side pack put every one
        # of these rows past the visible width once a second button
        # existed to share the line with). Stacking costs a few pixels of
        # height, which this screen can spare a good deal more easily than
        # it can spare horizontal room.
        rows = (
            ("Gemini key (free)", self.var_gemini,
             "Get a free key…", lambda: self._open(GEMINI_URL)),
            ("Google Translate key", self.var_google,
             "Set up Google…", self._open_google_setup),
            ("DeepL key (optional)", self.var_deepl,
             "Get a key…", lambda: self._open(DEEPL_URL)),
        )
        for text, var, button_text, command in rows:
            row = tk.Frame(body, bg=p["window"])
            row.pack(fill="x", pady=(0, 14))
            label(row, p, text, size=10).pack(anchor="w")
            sub = tk.Frame(row, bg=p["window"])
            sub.pack(fill="x", pady=(6, 0))
            Field(sub, p, textvariable=var, width=24, height=36,
                 ).pack(side="left")
            PillButton(sub, button_text, command=command, palette=p,
                       kind="secondary", height=Dropdown.HEIGHT).pack(
                           side="left", padx=(10, 0))

        label(body, p, KEY_NOTE, size=9, dim=True, wraplength=520,
              justify="left").pack(anchor="w", pady=(14, 0))

    @staticmethod
    def _open(url):
        import webbrowser
        webbrowser.open(url)

    def _open_google_setup(self):
        """The same walkthrough Settings offers for a Google key — three
        steps in two corners of the console, not a page to figure out
        alone. Reused rather than re-explained: one place that knows what
        Google currently asks for."""
        from .ui_setup import GoogleSetup
        try:
            window = GoogleSetup(self, palette=self.palette,
                                 on_saved=self._google_setup_done)
            window.lift()
            platform_util.raise_to_front(window)
        except Exception:
            _log(traceback.format_exc())

    def _google_setup_done(self):
        """Pick up the key the checklist just saved."""
        try:
            self.var_google.set(CFG.get("google_api_key", ""))
        except Exception:
            pass
