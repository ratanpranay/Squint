"""The radial menu: nine everyday tools around the mouse, on Ctrl+Alt+Space.

Squint's own shortcuts are untouched; this is one more hotkey, registered
beside them. `open_menu(controller)` is all main.py calls.
"""
import sys

from . import common

IS_WINDOWS = sys.platform == "win32"


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

    # (key, ring label, full name, icon glyph, [(action, run, uses files)],
    #  footer note)
    return [
        ("shot", "Capture", "Screenshot", "",
         [("Region", capture.region, False),
          ("Scrolling", capture.scrolling, False)],
         "Scrolling: scroll down slowly, Enter to finish. Saved in Downloads\\Squint\\Screenshots."),
        ("rec", "Record", "Screen record", "",
         [("Region video", record.video, False),
          ("Region GIF (max 6 s)", record.gif, False)],
         "Enter stops, Esc cancels; GIF stops at 6 s. Saved in Downloads\\Squint\\Recordings."),
        ("trans", "Translate", "Translate & OCR", "",
         [("Translate region", _squint("trigger_snip"), False),
          ("Copy text (OCR)", capture.copy_text, False),
          ("Translate document", _squint("document"), False),
          ("Translate clipboard", _squint("trigger_clipboard"), False)],
         "Powered by Squint. Its own shortcuts still work directly."),
        ("pdf", "PDF", "PDF tools", "",
         [("Files to PDF", pdf("to_pdf"), True),
          ("Merge", pdf("merge"), True),
          ("Split", pdf("split"), True),
          ("Compress", pdf("compress"), True),
          ("Password-lock PDF", pdf("lock"), True)],
         "Optional password (AES-256). Saved in Downloads\\Squint\\PDF."),
        ("zip", "Zip", "Compress", "",
         [("Zip selected", zipper("plain"), True),
          ("Zip with password", zipper("password"), True),
          ("Extract", zipper("extract"), True)],
         "Uses what is selected in Explorer. Saved in Downloads\\Squint\\Zip."),
        ("send", "Send", "Local send", "",
         [("Send to nearby device", send.nearby_cmd, True),
          ("Receive", send.receive_cmd, False),
          ("Phone via QR", send.phone_cmd, True)],
         "Same Wi-Fi only. Received files: Downloads\\Squint\\Received."),
        ("cal", "Calendar", "Calendar", "", [], ""),
        ("conv", "Convert", "Convert files", "",
         [("Image format / resize", conv("image"), True),
          ("Office to PDF", conv("office"), True),
          ("Video to MP4", conv("video"), True)],
         "Uses what is selected in Explorer. Saved in Downloads\\Squint\\Converted."),
        ("ext", "Extract", "Extract media", "",
         [("From PowerPoint", ext("ppt"), True),
          ("From Word", ext("word"), True),
          ("From PDF", ext("pdf"), True)],
         "Every picture, video and sound, saved in Downloads\\Squint\\Extracted media."),
    ], calendar_view.calendar_cmd


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
    """The hotkey: stop a recording if one runs, else show the menu."""
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
    tools, calendar_cmd = _tools()
    RadialMenu(ctrl, tools, calendar_cmd, front)
