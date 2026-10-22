"""The nine tool icons.

Drawn here rather than taken from a font so they look the same everywhere:
the Windows icon font does not exist on a Mac, where the ring used to show
numbers instead. Each icon is laid out on a 24 x 24 grid, like the system
icon sets, drawn four times too big and shrunk, so its edges are smooth on
Windows too (Tk's own canvas lines are not anti-aliased there).
"""
_cache = {}
OVERSAMPLE = 4


def image(key, size, colour):
    """A PIL RGBA image of the icon for tool `key`, `size` px square."""
    from PIL import Image, ImageDraw
    big = max(8, int(round(size))) * OVERSAMPLE
    k = big / 24.0
    w = max(1, int(round(1.75 * k)))
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def P(x, y):
        return (x * k, y * k)

    def line(*pts):
        d.line([P(*pt) for pt in pts], fill=colour, width=w, joint="curve")
        for pt in (pts[0], pts[-1]):          # round ends
            x, y = P(*pt)
            d.ellipse((x - w / 2.0, y - w / 2.0, x + w / 2.0, y + w / 2.0),
                      fill=colour)

    def poly(*pts):
        line(*(pts + (pts[0],)))

    def circle(x, y, r, fill=False):
        box = (P(x - r, y - r), P(x + r, y + r))
        if fill:
            d.ellipse(box, fill=colour)
        else:
            d.ellipse(box, outline=colour, width=w)

    def rect(xa, ya, xb, yb, r=2.0):
        d.rounded_rectangle((P(xa, ya), P(xb, yb)), radius=r * k,
                            outline=colour, width=w)

    if key == "shot":                       # camera
        rect(3, 7, 21, 19.5, 2.5)
        line((8, 7), (9.5, 4.5), (14.5, 4.5), (16, 7))
        circle(12, 13, 3.6)
    elif key == "rec":                      # record
        circle(12, 12, 8.5)
        circle(12, 12, 4.2, fill=True)
    elif key == "trans":                    # globe
        circle(12, 12, 9)
        d.ellipse((P(8, 3), P(16, 21)), outline=colour, width=w)
        line((3, 12), (21, 12))
        line((4.6, 7.5), (19.4, 7.5))
        line((4.6, 16.5), (19.4, 16.5))
    elif key == "pdf":                      # document
        poly((6, 3), (14, 3), (19, 8), (19, 21), (6, 21))
        line((14, 3), (14, 8), (19, 8))
        line((9, 13), (16, 13))
        line((9, 17), (14, 17))
    elif key == "zip":                      # archive box
        rect(3.5, 4, 20.5, 8.5, 1.2)
        line((5, 8.5), (5, 20), (19, 20), (19, 8.5))
        line((10, 12.5), (14, 12.5))
    elif key == "send":                     # paper plane
        poly((3, 11.5), (21, 3.5), (14.5, 21), (11, 13))
        line((11, 13), (21, 3.5))
    elif key == "cal":                      # calendar
        rect(3.5, 5, 20.5, 20.5, 2)
        line((3.5, 9.5), (20.5, 9.5))
        line((8, 3), (8, 6.5))
        line((16, 3), (16, 6.5))
        for gx in (8, 12, 16):
            for gy in (13.5, 17):
                circle(gx, gy, 0.9, fill=True)
    elif key == "conv":                     # two arrows
        line((4, 8), (19.5, 8))
        line((16, 4.5), (19.5, 8), (16, 11.5))
        line((20, 16), (4.5, 16))
        line((8, 12.5), (4.5, 16), (8, 19.5))
    elif key == "ext":                      # picture
        rect(3, 4, 21, 20, 2)
        line((3.8, 17), (9, 11.5), (13, 15.5), (16, 12.5), (20.2, 17))
        circle(15.5, 8.5, 1.6)
    small = max(8, int(round(size)))
    return img.resize((small, small), Image.LANCZOS)


def draw(canvas, key, cx, cy, size, colour, tags=()):
    """Put the icon on a Tk canvas, centred on (cx, cy)."""
    from PIL import ImageTk
    cache_key = (key, int(round(size)), colour)
    photo = _cache.get(cache_key)
    if photo is None:
        photo = ImageTk.PhotoImage(image(key, size, colour))
        _cache[cache_key] = photo          # Tk needs the image kept alive
    canvas.create_image(cx, cy, image=photo, tags=tags)
    return photo

