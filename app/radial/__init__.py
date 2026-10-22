"""The radial menu: nine everyday tools around the mouse, on Ctrl+Alt+Space.

Squint's own shortcuts are untouched; this is one more hotkey, registered
beside them. `open_menu(controller)` is all main.py calls.

Every tool shows in the one panel beside the ring (menu.py). An action is
either "screen" - the ring closes first, because it must not be in the
picture - or "panel" - it carries on inside the panel: settings,
progress, the QR code, the camera.
"""
import sys

from . import common

IS_WINDOWS = sys.platform == "win32"

# The ♥ in the middle of the ring.
SUPPORT_URL = ("https://www.paypal.com/donate/?business=pranayratan%40gmail.com"
               "&item_name=Support+Squint&currency_code=EUR")

SCREEN, PANEL = "screen", "panel"


def _squint(name):
    def run(ctrl, **_):
        if name == "document":
            ctrl.show_window()
        else:
            getattr(ctrl, name)()
    return run


def _tools():
    from . import calendar_view, capture, docs, record, send

    def pdf(action):
        return lambda ctrl, **kw: docs.pdf_cmd(ctrl, action, **kw)

    def zipper(action):
        return lambda ctrl, **kw: docs.zip_cmd(ctrl, action, **kw)

    def conv(action):
        return lambda ctrl, **kw: docs.convert_cmd(ctrl, action, **kw)

    def ext(action):
        return lambda ctrl, **kw: docs.extract_cmd(ctrl, action, **kw)

    def tool(key, label, full, glyph, rows, note="", **extra):
        d = {"key": key, "label": label, "full": full, "glyph": glyph,
             "rows": rows, "note": note}
        d.update(extra)
        return d

    return [
        tool("shot", "Capture", "Screenshot", "",
             [("Region", capture.region, False, SCREEN),
              ("Scrolling", capture.scrolling, False, SCREEN),
              ("Selfie check", capture.selfie, False, PANEL)],
             "Scrolling: scroll down inside the box, Enter to finish. "
             "Saved in Downloads\\Squint\\Screenshots."),
        tool("rec", "Record", "Screen record", "",
             [("Region video", record.video, False, PANEL),
              ("Region GIF (max 6 s)", record.gif, False, SCREEN)],
             "Enter stops, Esc cancels; GIF stops at 6 s. "
             "Saved in Downloads\\Squint\\Recordings."),
        tool("trans", "Translate", "Translate & OCR", "",
             [("Translate region", _squint("trigger_snip"), False, SCREEN),
              ("Copy text (OCR)", capture.copy_text, False, SCREEN),
              ("Translate document", _squint("document"), False, SCREEN),
              ("Translate clipboard", _squint("trigger_clipboard"), False,
               SCREEN)],
             "Powered by Squint. Its own shortcuts still work directly."),
        tool("pdf", "PDF", "PDF tools", "",
             [("Files to PDF", pdf("to_pdf"), True, PANEL),
              ("Merge", pdf("merge"), True, PANEL),
              ("Split", pdf("split"), True, PANEL),
              ("Compress", pdf("compress"), True, PANEL),
              ("Password-lock PDF", pdf("lock"), True, PANEL)],
             "Optional password (AES-256). Saved in Downloads\\Squint\\PDF."),
        tool("zip", "Zip", "Compress", "",
             [("Zip selected", zipper("plain"), True, PANEL),
              ("Zip with password", zipper("password"), True, PANEL),
              ("Extract", zipper("extract"), True, PANEL)],
             "Uses what is selected in Explorer. "
             "Saved in Downloads\\Squint\\Zip."),
        tool("send", "Send", "Local send", "",
             [("Send to nearby device", send.nearby_cmd, True, PANEL),
              ("Receive", send.receive_cmd, False, PANEL),
              ("Phone via QR", send.phone_cmd, True, PANEL)],
             "Same Wi-Fi only. Received files: "
             "Downloads\\Squint\\Received."),
        tool("cal", "Calendar", "Calendar", "", [],
             view=calendar_view.build, wide=True),
        tool("conv", "Convert", "Convert files", "",
             [("Image format / resize", conv("image"), True, PANEL),
              ("Office to PDF", conv("office"), True, PANEL),
              ("Video to MP4", conv("video"), True, PANEL)],
             "Uses what is selected in Explorer. "
             "Saved in Downloads\\Squint\\Converted."),
        tool("ext", "Extract", "Extract media", "",
             [("From PowerPoint", ext("ppt"), True, PANEL),
              ("From Word", ext("word"), True, PANEL),
              ("From PDF", ext("pdf"), True, PANEL)],
             "Every picture, video and sound, saved in "
             "Downloads\\Squint\\Extracted media."),
    ]


_started = set()


def start(ctrl):
    """Once, at startup: reminders for timed agenda items."""
    if "reminders" in _started:
        return
    _started.add("reminders")
    try:
        from . import calendar_view
        calendar_view.start_reminders(ctrl)
    except Exception as exc:              # noqa: BLE001 - never fatal
        common.log("reminders off: %r" % exc)


def open_menu(ctrl):
    """The hotkey: stop a recording if one runs, else show the menu (or
    close it if it is already up)."""
    bar = getattr(ctrl, "radial_recording", None)
    if bar is not None and not bar.done:
        bar.stop()
        return
    from .menu import RadialMenu
    if RadialMenu.current is not None:
        RadialMenu.current.close()
        return
    front = None
    try:
        from .. import platform_util
        front = platform_util.front_handle()
    except Exception:
        pass
    RadialMenu(ctrl, _tools(), front, SUPPORT_URL)
