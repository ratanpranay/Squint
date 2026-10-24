"""The radial menu: eight everyday tools around the mouse, on Ctrl+Alt+Space.

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
SUPPORT_URL = "https://www.paypal.com/qrcodes/p2pqrc/VCMMGZLN8W22C"

SCREEN, PANEL = "screen", "panel"


def _squint(name):
    def run(ctrl, **_):
        if name == "document":
            ctrl.show_window()
        else:
            getattr(ctrl, name)()
    return run


def _tools():
    tools = _tool_list()
    if sys.platform == "darwin":
        # Same words a Mac uses.
        for t in tools:
            t["note"] = t["note"].replace("Explorer", "Finder").replace(
                "Downloads\\Squint\\", "Downloads/Squint/").replace(
                "Downloads\\Squint", "Downloads/Squint")
    return tools


def _tool_list():
    from . import calendar_view, capture, docs, record, send, tools

    def pdf(action):
        return lambda ctrl, **kw: docs.pdf_cmd(ctrl, action, **kw)

    def zipper(action):
        return lambda ctrl, **kw: docs.zip_cmd(ctrl, action, **kw)

    def ext(action):
        return lambda ctrl, **kw: docs.extract_cmd(ctrl, action, **kw)

    # Each tool's own colour: its icon, and its fill once picked.
    colours = {"shot": "#3D7BF5", "rec": "#F05252", "tools": "#14A8C4",
               "pdf": "#F08C3A", "zip": "#9B6BF2", "send": "#22A86E",
               "cal": "#E0A800", "ext": "#E0609F"}

    def tool(key, label, full, glyph, rows, note="", **extra):
        d = {"key": key, "label": label, "full": full, "glyph": glyph,
             "rows": rows, "note": note,
             "colour": colours.get(key, common.ACCENT)}
        d.update(extra)
        return d

    return [
        tool("shot", "Capture", "Screenshot", "",
             [("Region", capture.region, False, SCREEN),
              ("Scrolling", capture.scrolling, False, SCREEN),
              ("Copy text (OCR)", capture.copy_text, False, SCREEN),
              ("Selfie check", capture.selfie, False, PANEL)],
             "Scrolling: scroll down inside the box, Enter to finish. "
             "Saved in Downloads\\Squint\\Screenshots."),
        tool("rec", "Record", "Screen record", "",
             [("Region video", record.video, False, PANEL),
              ("Region GIF (max 6 s)", record.gif, False, SCREEN),
              ("Video to MP4", docs.video_cmd, True, PANEL)],
             "Enter stops, Esc cancels; GIF stops at 6 s. Video to MP4 "
             "takes MOV, MKV, AVI, WMV, WebM and more. "
             "Saved in Downloads\\Squint\\Recordings."),
        tool("tools", "Tools", "Tools", "",
             [("Open Downloads", tools.open_downloads, False, SCREEN),
              ("Calculator", tools.calculator, False, PANEL),
              ("Squint", tools.open_squint, False, SCREEN)],
             "Open Downloads shows Downloads\\Squint, where every tool "
             "saves. Squint opens its main window."),
        tool("pdf", "PDF", "PDF tools", "",
             [("Convert to PDF", pdf("to_pdf"), True, PANEL),
              ("Merge", pdf("merge"), True, PANEL),
              ("Split", pdf("split"), True, PANEL),
              ("Compress", pdf("compress"), True, PANEL),
              ("Password-lock PDF", pdf("lock"), True, PANEL)],
             "Convert takes Word, PowerPoint, Excel, pictures and PDFs. "
             "Optional password (AES-256). Saved in Downloads\\Squint\\PDF."),
        tool("zip", "Zip", "Compress", "",
             [("Zip selected", zipper("plain"), True, PANEL),
              ("Zip with password", zipper("password"), True, PANEL),
              ("Extract", zipper("extract"), True, PANEL)],
             "Uses what is selected in Explorer. "
             "Saved in Downloads\\Squint\\Zip."),
        tool("send", "Transfers", "Transfers", "",
             [("Send to nearby device", send.nearby_cmd, True, PANEL),
              ("Receive from nearby device", send.receive_cmd, False, PANEL),
              ("Phone via QR", send.phone_cmd, True, PANEL)],
             "Same Wi-Fi only. Received files: "
             "Downloads\\Squint\\Received.", top=send.name_row,
             top_label=lambda: "Your name: %s  ·  Change" % send.device_name(),
             top_title="Your name on Wi-Fi",
             top_note="Nearby computers and phones see you by this name."),
        tool("cal", "Calendar", "Calendar", "", [],
             view=calendar_view.build, wide=True),
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
    spec = getattr(ctrl, "radial_hotkey", None) or "alt+space"
    names = {"alt": "Option", "ctrl": "Control", "cmd": "Command"} \
        if sys.platform == "darwin" else {}
    shortcut = " + ".join(names.get(p, p.capitalize())
                          for p in spec.split("+"))
    RadialMenu(ctrl, _tools(), front, SUPPORT_URL, shortcut)
