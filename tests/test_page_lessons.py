"""What 20 real web pages in seven languages showed, kept as tests."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402
from app import numbering, ocr, overlay  # noqa: E402


def para(texts, x=100, y0=100, h=20, pitch=30, w=400):
    return [{"text": t, "box": (x, y0 + i * pitch, w, h)}
            for i, t in enumerate(texts)]


class GroupingTests(unittest.TestCase):
    def test_bulleted_headlines_stay_separate(self):
        lines = para(["・30日も関東は雨続く 台風の進路は", "・修繕談合で再発防止を要請 国交省",
                      "・ドンキ トイザらス日本事業買収へ"])
        self.assertEqual(len(overlay.group_paragraphs(lines)), 3)

    def test_menu_items_stay_separate(self):
        lines = para(["一休.comレストラン", "ふるさと納税", "出前館"], w=150)
        self.assertEqual(len(overlay.group_paragraphs(lines)), 3)
        lines = para(["Politique et administration", "Population et société"],
                     w=300)
        self.assertEqual(len(overlay.group_paragraphs(lines)), 2)

    def test_heading_in_colour_above_body_is_not_its_first_line(self):
        lines = [{"text": "Über diese Reformen diskutiert Schwarz-Rot",
                  "box": (100, 100, 600, 28), "ink_colour": (20, 80, 160)},
                 {"text": "Die Bundesregierung beteuert es nahezu täglich",
                  "box": (100, 136, 600, 20), "ink_colour": (30, 30, 30)},
                 {"text": "Herbst hat Schwarz-Rot viel vor und droht sich",
                  "box": (100, 164, 600, 20), "ink_colour": (30, 30, 30)}]
        self.assertEqual(overlay.group_paragraphs(lines), [[0], [1, 2]])

    def test_bullet_is_kept_out_of_the_translation(self):
        marker, rest = numbering.split("・30日も関東は雨続く")
        self.assertEqual(rest, "30日も関東は雨続く")
        self.assertEqual(numbering.attach(marker, "Rain in Kanto", "en"),
                         "• Rain in Kanto")


def page_with(pieces, width=1400, height=120):
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    for x0, x1 in pieces:
        d.rectangle([x0, 44, x1, 60], fill="black")
    return img


class SplitTests(unittest.TestCase):
    def test_line_across_a_wide_gap_is_cut(self):
        img = page_with([(20, 300), (600, 900)])
        line = {"text": "Politique et administration Aix-en-Provence.",
                "box": (20, 40, 880, 24)}
        out = ocr.split_at_gutters([line], img)
        self.assertEqual([l["text"] for l in out],
                         ["Politique et administration", "Aix-en-Provence."])

    def test_menu_row_is_cut_into_items(self):
        img = page_with([(20, 120), (150, 230), (260, 360), (390, 470)])
        line = {"text": "Startseite Pflege Ukraine Inland",
                "box": (20, 40, 450, 24)}
        out = ocr.split_at_gutters([line], img)
        self.assertEqual(len(out), 4)

    def test_sentence_is_not_cut(self):
        img = page_with([(20, 120), (130, 230), (240, 360), (370, 470)])
        line = {"text": "Die Bundesregierung beteuert es nahezu täglich",
                "box": (20, 40, 450, 24)}
        self.assertEqual(len(ocr.split_at_gutters([line], img)), 1)


class CoverTests(unittest.TestCase):
    def test_reach_stops_at_the_edge_of_a_panel(self):
        img = Image.new("RGB", (800, 120), "white")
        d = ImageDraw.Draw(img)
        d.rectangle([20, 44, 300, 60], fill="black")          # the text
        d.rectangle([400, 46, 800, 120], outline=(162, 169, 177),
                    fill=(152, 251, 152))                      # a panel
        run = overlay.background_run(img, (20, 40, 280, 24),
                                     (255, 255, 255), 500, ink=(0, 0, 0))
        self.assertLess(run, 110)

    def test_room_below_stops_at_a_picture(self):
        img = Image.new("RGB", (400, 400), "white")
        ImageDraw.Draw(img).rectangle([0, 200, 400, 400], fill="red")
        clear = overlay.background_below(img, (20, 100, 200, 30),
                                         (255, 255, 255), 400)
        self.assertLess(clear, 75)


if __name__ == "__main__":
    unittest.main()
