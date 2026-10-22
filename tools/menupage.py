# -*- coding: utf-8 -*-
"""A shop's navigation menu, drawn so it can be checked every build.

Forty-one links in seven columns came back as twenty blocks. Whole
columns were run together and handed to the engine as a sentence —
"Sports Shoes Hiking Boots Sneakers Flip-Flops Water Shoes All
Products" — while the column beside them, laid out identically, came
back correctly as six links. Which way any one of them fell came down
to a pixel of recogniser noise.

Menus, tables of contents, indexes, address blocks and verse are all
the same shape: items at one margin, one line apart, in one size, with
no right margin. The corpus had prose and tables and nothing of this
kind, so nothing ever asked.

    python tools/menupage.py tests/pages
"""
import sys
from PIL import Image, ImageDraw, ImageFont
W, H = 1500, 760
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)
B = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 21)
R = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
d.text((56, 30), "Herren", font=B, fill="#101020")
COLS = [
 (56, [("Sportbekleidung", 1), ("Regenbekleidung", 0), ("Funktionsunterwäsche", 0),
   ("Fleeceoberteile", 0), ("Pullover, Langarmshirts", 0), ("T-Shirts & Hemden", 0),
   ("Alle Produkte  >", 0)]),
 (420, [("Schuhe", 1), ("Sportschuhe", 0), ("Wanderschuhe", 0), ("Sneakers", 0),
   ("Badelatschen", 0), ("Wasserschuhe", 0), ("Alle Produkte  >", 0)]),
 (790, [("Accessoires", 1), ("Sporttaschen & Rucksäcke", 0), ("Sportuhren", 0),
   ("Sonnenbrillen", 0), ("Caps", 0), ("Trinkflaschen", 0), ("Alle Produkte  >", 0)]),
 (1140, [("Bademode", 1), ("Badebekleidung", 0), ("Neoprenbekleidung", 0),
   ("UV-Bekleidung", 0), ("Bademäntel & Ponchos", 0), ("Alle Produkte  >", 0)]),
]
ROW2 = [
 (56, [("Sportswear", 1), ("Sportswear Sneaker", 0), ("Sportswear Bekleidung", 0),
   ("Sportswear Accessoires", 0), ("Alle Produkte  >", 0)]),
 (420, [("Outdoorwelt", 1), ("Bekleidung", 0), ("Schuhe", 0),
   ("Outdoor Ausrüstung", 0), ("Alle Produkte  >", 0)]),
 (790, [("Gebrauchte Bekleidung", 1), ("Bekleidung", 0), ("Schuhe", 0),
   ("Alle Produkte  >", 0)]),
]
def column(x, items, top):
    y = top
    for text, bold in items:
        d.text((x, y), text, font=(B if bold else R), fill="#101020" if bold else "#3a3a46")
        y += 47 if bold else 41
    return y
for x, items in COLS: column(x, items, 100)
for x, items in ROW2: column(x, items, 440)
import os
where = sys.argv[1] if len(sys.argv) > 1 else "."
os.makedirs(where, exist_ok=True)
img.save(os.path.join(where, "german-menu.png"))
print("menu page written: %d links in %d columns"
      % (sum(len(i) for _x, i in COLS + ROW2), len(COLS) + len(ROW2)))
