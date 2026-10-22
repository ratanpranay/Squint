"""Open the real window and save a picture of it.

Not a test — a way to look at the thing. It used to assemble its own
copy of the front page out of the same widgets, which meant it drifted
from the page the moment the page changed, and a picture of a layout
nobody ships is worse than no picture. It now builds `MainWindow` with
a stub controller, so what it photographs is what opens.

usage:
    xvfb-run -a -s "-screen 0 1512x982x24" \
        python tools/frontpage_shot.py out.png [Translate|Settings|Support]
        [light|dark] [seconds]

The last number is how long to let the window run before the shutter:
the picture at the top of the page is a loop, and at under two and a
half seconds it has not reached the part with the answer in it.
"""
import os
import subprocess
import sys
import tkinter as tk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import config                                 # noqa: E402


class Stub:
    """Everything MainWindow asks of a controller, and nothing behind it."""

    def __init__(self, root):
        self.root = root
        self.icon_path = None

    def trigger_snip(self):
        pass

    def refresh_tray(self):
        pass

    def apply_hotkeys(self, snip, clip):
        return True, ""

    def set_run_at_startup(self, on):
        return True, ""

    def show_window(self):
        pass

    def request_restart_for_theme(self):
        pass


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "frontpage.png"
    pane = sys.argv[2] if len(sys.argv) > 2 else "Translate"
    mode = sys.argv[3] if len(sys.argv) > 3 else "light"
    wait = float(sys.argv[4]) if len(sys.argv) > 4 else 3.0
    config.CONFIG.set("theme", mode)

    from app.ui_main import MainWindow
    from app import ui_home

    root = tk.Tk()
    root.withdraw()
    window = MainWindow(Stub(root))
    window.show()
    window.open_pane(pane)
    for _ in range(8):
        window.update_idletasks()
        window.update()
    root.after(int(wait * 1000), root.quit)
    root.mainloop()
    window.update_idletasks()
    window.update()
    # ImageMagick rather than Pillow: Pillow dropped the X window dump
    # format, and this is one line of shell against a page of ctypes.
    subprocess.run(["import", "-window", "root", out], check=True)
    print("%s  %s / %s  window %dx%d  scale %.2f  screen %dx%d"
          % (out, pane, mode, window.winfo_width(), window.winfo_height(),
             ui_home.SCALE, root.winfo_screenwidth(),
             root.winfo_screenheight()))
    root.destroy()


if __name__ == "__main__":
    main()
