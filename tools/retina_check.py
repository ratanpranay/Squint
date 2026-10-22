"""Is this window being drawn at the screen's real resolution?

Run it and read what it prints. Nothing is changed and nothing is saved.

    .venv/bin/python tools/retina_check.py

Why this exists. A Mac with a Retina display has two device pixels to
the point. A process that has not declared it can cope is drawn at one
pixel to the point and scaled up afterwards by the window server — so
every line is twice as wide as it should be, every curve is stepped, and
a photograph is at half the resolution it was prepared at.

From a screenshot that looks like a drawing fault, and it is not: it is
the whole window, the text included. Chasing it one widget at a time —
the icons, the pills, the mark in the corner — cannot work, because none
of those is where it happens. This prints the one number that says which
of the two it is, so nobody has to guess from a screenshot again.

It also draws three things side by side in a window, at the same size:

    left    a shape rendered by the imaging library and placed as a
            picture, which is how every pill and icon in the app is
            drawn on Windows and Linux
    middle  the same shape drawn by Tk's own canvas
    right   a line of text

Screenshot that window and look at the three. If all three are equally
soft, the window is at half resolution and the answer is the number
above, not the drawing. If the text is sharp and the other two are not,
it is the drawing after all, and the middle one says which way to go.
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def facts():
    """Everything worth knowing, as lines to print."""
    out = ["python      : %s" % sys.executable,
           "platform    : %s" % sys.platform]
    try:
        from app import config
        out.append("build       : %s" % config.build_id())
    except Exception:
        pass
    if sys.platform != "darwin":
        out.append("note        : this matters on macOS; elsewhere it is "
                   "one device pixel to the point and there is nothing "
                   "to declare")
        return out
    try:
        from Foundation import NSBundle
        bundle = NSBundle.mainBundle()
        info = (bundle.localizedInfoDictionary() or bundle.infoDictionary()
                if bundle is not None else None)
        out.append("bundle      : %s" % (bundle.bundlePath()
                                         if bundle is not None else "none"))
        out.append("declared    : NSHighResolutionCapable = %s"
                   % (info.get("NSHighResolutionCapable")
                      if info is not None else "?"))
    except Exception as exc:
        out.append("bundle      : could not read (%s)" % str(exc)[:70])
    try:
        from AppKit import NSScreen
        screen = NSScreen.mainScreen()
        out.append("screen      : backing scale %s"
                   % screen.backingScaleFactor())
    except Exception as exc:
        out.append("screen      : could not read (%s)" % str(exc)[:70])
    return out


def window_scale(root):
    """What the window itself is being drawn at, which is the answer.

    The screen can be a Retina screen and the window still be drawn at
    one pixel to the point; that is the whole point of this. So the
    window is asked, not the screen.
    """
    try:
        from AppKit import NSApp
        root.update()
        windows = [w for w in NSApp().windows() if w.isVisible()]
        if not windows:
            return "no window on screen yet"
        return ", ".join(str(w.backingScaleFactor()) for w in windows)
    except Exception as exc:
        return "could not read (%s)" % str(exc)[:70]


def main():
    lines = facts()

    root = tk.Tk()
    root.title("Squint — resolution check")
    root.configure(bg="#101418")
    side = 120

    frame = tk.Frame(root, bg="#101418")
    frame.pack(padx=24, pady=24)

    # 1. The imaging library, placed as a picture.
    picture = tk.Canvas(frame, width=side, height=side, bg="#101418",
                        highlightthickness=0)
    picture.grid(row=0, column=0, padx=12)
    try:
        from PIL import Image, ImageDraw, ImageTk
        img = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        pen = ImageDraw.Draw(img)
        pen.ellipse([6, 6, side - 7, side - 7], outline=(120, 170, 255, 255),
                    width=3)
        pen.line([(24, side // 2), (side - 24, side // 2)],
                 fill=(120, 170, 255, 255), width=3)
        picture.photo = ImageTk.PhotoImage(img, master=picture)
        picture.create_image(0, 0, anchor="nw", image=picture.photo)
    except Exception as exc:
        picture.create_text(side / 2, side / 2, text="no PIL",
                            fill="#8899aa")
        lines.append("PIL         : %s" % str(exc)[:70])
    tk.Label(frame, text="a picture", bg="#101418", fg="#8899aa").grid(
        row=1, column=0)

    # 2. Tk's own canvas, drawing the same thing.
    drawn = tk.Canvas(frame, width=side, height=side, bg="#101418",
                      highlightthickness=0)
    drawn.grid(row=0, column=1, padx=12)
    drawn.create_oval(6, 6, side - 7, side - 7, outline="#78aaff", width=3)
    drawn.create_line(24, side // 2, side - 24, side // 2,
                      fill="#78aaff", width=3)
    tk.Label(frame, text="the canvas", bg="#101418", fg="#8899aa").grid(
        row=1, column=1)

    # 3. Text, as a control. It is drawn by the system either way.
    words = tk.Canvas(frame, width=side + 40, height=side, bg="#101418",
                      highlightthickness=0)
    words.grid(row=0, column=2, padx=12)
    words.create_text(side / 2 + 20, side / 2, text="Handgloves",
                      fill="#78aaff", font=("Helvetica", 22))
    tk.Label(frame, text="text", bg="#101418", fg="#8899aa").grid(
        row=1, column=2)

    lines.append("window      : backing scale %s" % window_scale(root))

    report = "\n".join(lines)
    print(report)
    box = tk.Text(root, width=78, height=len(lines) + 1, bd=0,
                  bg="#171d24", fg="#cfd8e3", padx=14, pady=12,
                  font=("Menlo", 12) if sys.platform == "darwin"
                  else ("Consolas", 10))
    box.pack(padx=24, pady=(0, 24), fill="x")
    box.insert("1.0", report)
    box.configure(state="disabled")

    verdict = ("On a Retina Mac the window's backing scale should be 2.0. "
               "If it says 1.0, the whole window is at half resolution and "
               "no change to how anything is drawn will help.")
    tk.Label(root, text=verdict, bg="#101418", fg="#8899aa",
             wraplength=560, justify="left").pack(padx=24, pady=(0, 20))
    root.mainloop()


if __name__ == "__main__":
    main()
