"""Headless UI smoke test (Linux/Xvfb).

Builds the real windows against stubbed Windows-only pieces so layout and
widget-API mistakes surface without a Windows box. Not shipped functionality —
a development check.
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# --- stub the modules that only exist on Windows / aren't installed here ---
for name in ("pystray", "mss", "pytesseract", "fitz", "docx", "langdetect"):
    if name not in sys.modules:
        try:
            __import__(name)
        except Exception:
            sys.modules[name] = types.ModuleType(name)

if not hasattr(sys.modules.get("deep_translator", None), "GoogleTranslator"):
    dt = types.ModuleType("deep_translator")

    class GoogleTranslator:  # noqa: D401
        def __init__(self, source="auto", target="en"):
            self.target = target

        def translate(self, text):
            return "[%s] %s" % (self.target, text)

    dt.GoogleTranslator = GoogleTranslator
    dt.single_detection = lambda *a, **k: "en"
    sys.modules["deep_translator"] = dt

import tkinter as tk  # noqa: E402

from app import config, ocr  # noqa: E402
from app.ui_main import MainWindow  # noqa: E402
from app.ui_result import ResultPopup, StatusToast  # noqa: E402

# OCR can't run here; make the settings tab's probe fail gracefully.
ocr.ensure_ready = lambda: None
ocr.installed_packs = lambda: {"eng", "deu", "osd"}


class FakeController:
    def __init__(self, root):
        self.root = root
        self.config = config.CONFIG
        self.icon_path = os.path.join(ROOT, "assets", "icon.ico")
        self.calls = []

    def trigger_snip(self):
        self.calls.append("snip")

    def refresh_tray(self):
        self.calls.append("tray")

    def apply_hotkeys(self, a, b):
        self.calls.append(("hotkeys", a, b))
        return True, "Shortcuts active"

    def set_run_at_startup(self, enabled):
        return True, ""

    def show_window(self):
        pass

    def request_restart_for_theme(self):
        self.calls.append("theme")


def main():
    root = tk.Tk()
    root.withdraw()
    controller = FakeController(root)

    win = MainWindow(controller)
    win.update_idletasks()
    print("main window built:", win.winfo_reqwidth(), "x",
          win.winfo_reqheight())

    # exercise every pane through the segmented control
    for index, name in enumerate(("Files", "Text", "Settings")):
        win.segmented.select(index, animate=False)
        win.update_idletasks()
    print("panes ok:", list(win.panes))

    # language switch through the custom dropdown
    win._on_lang_change("German")
    assert config.CONFIG["target_lang"] == "de", config.CONFIG["target_lang"]
    win._on_lang_change("English")
    win.sync_language()
    assert win.lang_dropdown.get() == "English"
    print("language switching ok")

    # widgets that draw themselves
    win.file_progress.set(0.4)
    win.var_copy.set(False)
    print("switches:", win.var_copy.get(), win.var_orig.get())

    # text tab: typing must translate on its own, without pressing anything
    # translator is stubbed at module import; auto-translate exercises it
    win._fill(win.text_src, "Guten Morgen")
    win._schedule_auto()
    assert win._auto_job is not None, "auto-translate was not scheduled"
    import time
    deadline = time.time() + 5
    while time.time() < deadline and not win.text_dst.get("1.0",
                                                          "end-1c").strip():
        root.update()
        win._pump_ui_once()
        time.sleep(0.05)
    produced = win.text_dst.get("1.0", "end-1c").strip()
    assert produced, "auto-translate never produced output"
    print("auto-translate ->", produced)

    # a second scheduling with unchanged text must not re-run
    win._last_translated = win.text_src.get("1.0", "end-1c").strip()
    before = produced
    win._auto_translate()
    assert win.text_dst.get("1.0", "end-1c").strip() == before
    print("unchanged text does not re-translate")

    # changing the target language must invalidate and redo
    win._on_lang_change("German")
    assert win._last_translated is None, "language change did not invalidate"
    assert win._auto_job is not None, "language change did not reschedule"
    win._on_lang_change("English")
    root.update()
    print("language change retriggers translation")

    # hotkey status must be visible in the window, not only the tray
    win.set_hotkey_status(["that shortcut is already taken"])
    assert "already taken" in win.subtitle.cget("text")
    win.set_hotkey_status([])
    assert "Press" in win.subtitle.cget("text")
    print("hotkey status surfaces in the header")

    # progress + status helpers
    win._set_progress(3, 10, "Translating page 3 of 5")
    win.refresh_packs()
    print("settings ok:", win.packs_label.cget("text")[:60])

    # result popup — the window must actually be sized to its content
    popup = ResultPopup(root, "Good morning", "Guten Morgen",
                        "Latin -> English", show_original=True)
    popup.update_idletasks()
    pw, ph = popup.winfo_width(), popup.winfo_height()
    print("popup built:", pw, "x", ph)
    assert pw > 180 and ph > 120, "popup collapsed to %dx%d" % (pw, ph)
    body_h = popup.body.winfo_reqheight()
    assert abs(ph - body_h) <= 6, \
        "window %dpx does not match its content %dpx" % (ph, body_h)
    assert popup.canvas.winfo_width() > 180, "canvas never got a size"
    popup.copy()
    popup.close()

    # a long translation must grow, but stay bounded
    tall = ResultPopup(root, "Zeile eins\n" * 200, "x" * 4000, "test")
    tall.update_idletasks()
    th = tall.winfo_height()
    assert th > ph, "long popup (%d) is not taller than short one (%d)" % (
        th, ph)
    assert th < 900, "popup grew to %d px" % th
    print("long popup grew %d -> %d px, still bounded" % (ph, th))
    tall.close()

    # failures must render as a card, not vanish into the tray
    err = ResultPopup(root, "The OCR engine is missing. Run fix_ocr.bat.",
                      "", "Could not translate", show_original=False,
                      kind="error")
    err.update_idletasks()
    assert err.winfo_width() > 180 and err.winfo_height() > 90, \
        "error card collapsed to %dx%d" % (err.winfo_width(),
                                           err.winfo_height())
    print("error card:", err.winfo_width(), "x", err.winfo_height())
    err.close()

    # window chrome must never make the window invisible
    from app import win_effects
    for value in (0.0, -1, 0.5, 1.0, "nonsense"):
        got = win_effects.set_opacity(win, value)
        assert got is None or got >= win_effects.MIN_ALPHA, \
            "opacity %r produced %r" % (value, got)
    print("opacity clamped at >=", win_effects.MIN_ALPHA)
    assert not hasattr(win_effects, "blur_behind"), \
        "blur path is incompatible with Tk and must stay removed"
    assert config.DEFAULTS["window_effects"] is False, \
        "compositing must stay off by default"
    assert win.effects == {}, "no window effects should have been applied"
    print("no compositing applied:", win.effects)

    # the window must actually contain painted widgets, not an empty frame
    def count_widgets(widget):
        total = 1
        for child in widget.winfo_children():
            total += count_widgets(child)
        return total

    widgets = count_widgets(win)
    assert widgets > 60, "window has only %d widgets - it is empty" % widgets
    painted = [w for w in (win.snip_button, win.segmented, win.lang_dropdown)
               if w.winfo_width() > 10]
    assert len(painted) == 3, "header controls did not get sizes"
    assert win.file_src.winfo_width() > 100, "text panes have no width"
    print("window populated: %d widgets, header controls sized" % widgets)

    # overlay window: must appear at the given screen position, sized to
    # the image, and dismiss on a click
    from PIL import Image as _Img
    from app.ui_result import OverlayWindow
    shot = _Img.new("RGB", (320, 90), "white")
    ov = OverlayWindow(root, shot, 40, 60, on_copy="hello")
    root.update()
    assert ov.winfo_width() == 320 and ov.winfo_height() == 90, \
        "overlay is %dx%d, expected 320x90" % (ov.winfo_width(),
                                               ov.winfo_height())
    ov._copy()
    ov.close()
    assert ov not in OverlayWindow._open
    print("overlay window sized and dismissed")

    toast = StatusToast(root, "Reading text…")
    toast.update_idletasks()
    tw, thh = toast.winfo_width(), toast.winfo_height()
    assert tw > 100 and thh > 30, "toast collapsed to %dx%d" % (tw, thh)
    toast.set("Translating…")
    root.update_idletasks()
    toast.close()
    print("toast ok:", tw, "x", thh)

    win.hide()
    root.destroy()
    print("\nSMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
