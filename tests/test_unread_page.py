"""A page Windows has no pack for is read by PaddleOCR on this computer,
with or without a cloud reader - never shown as Latin rubbish."""
import os
import random
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from app import ocr  # noqa: E402

CJK_FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
LATIN_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

ZH = ["今天是小明的第一天上学。他早上七点", "起床，吃了妈妈做的早饭，然后穿上新",
      "衣服。他的书包里有很多新书和文具。", "小明感到有点紧张，但也很兴奋。",
      "到了学校，小明看到了很多穿着校服的", "孩子们。他们在操场上玩耍。小明的老",
      "师是王老师，她非常亲切。她带小明去", "教室，并给他介绍了新同学。"]
EN = ["Today is the first day of school for", "Xiao Ming. He got up at seven and",
      "ate the breakfast his mother made,", "then put on his new clothes. His bag",
      "had many new books in it. He felt a", "little nervous, but also excited.",
      "At school he saw many children in", "uniforms playing on the field."]


def page(rows, font_path, photo=False):
    font = ImageFont.truetype(font_path, 28)
    img = Image.new("RGB", (1100 if photo else 620, 60 + 44 * len(rows)),
                    "white")
    draw = ImageDraw.Draw(img)
    boxes = []
    for i, row in enumerate(rows):
        y = 30 + 44 * i
        draw.text((30, y), row, font=font, fill="black")
        x0, y0, x1, y1 = draw.textbbox((30, y), row, font=font)
        boxes.append({"text": row, "box": (x0, y0, x1 - x0, y1 - y0)})
    if photo:
        rnd = random.Random(1)
        for x in range(660, 1080, 3):
            for y in range(20, img.height - 20, 3):
                v = rnd.randint(60, 200)
                draw.rectangle((x, y, x + 2, y + 2), fill=(v, v - 20, v - 40))
    return img, boxes


JUNK = [{"text": "fR3 A — Bj, fifi A fifi A A fifi ± g;p-x-, 25, tg",
         "box": (30, 30, 500, 30)}]


class Decision(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(ocr, "use_paddle", lambda: True),
                  mock.patch.object(ocr, "_cjk_pack_installed", lambda: False)):
            p.start()
            self.addCleanup(p.stop)

    def test_chinese_read_as_scraps_is_unread(self):
        img, _ = page(ZH, CJK_FONT)
        self.assertEqual(ocr._second_opinion(JUNK[0]["text"], JUNK, img),
                         "unread")

    def test_one_junk_word_is_misread(self):
        img, _ = page(ZH, CJK_FONT)
        self.assertIsNotNone(ocr._second_opinion("L-i*4Dfi7,", JUNK, img))

    def test_a_good_english_reading_stands(self):
        img, boxes = page(EN, LATIN_FONT)
        self.assertIsNone(ocr._second_opinion(" ".join(EN), boxes, img))

    def test_long_english_reading_beside_photos_stands(self):
        # Photos are rows with edges too; a whole English reading that
        # covers only the text beside them is not "unread".
        img, boxes = page(EN, LATIN_FONT, photo=True)
        half = boxes[:3]
        text = " ".join(EN[:3])
        self.assertIsNone(ocr._second_opinion(text, half, img))

    def test_english_with_one_odd_word_stands(self):
        # A Korean PC (Korean and English packs, no key) reading an English
        # page with one misread word: Windows' reading stands - the slow
        # reader took 7-8 s a snip for nothing better.
        img, boxes = page(EN, LATIN_FONT)
        text = " ".join(EN) + " L61E3xQ"
        with mock.patch.object(ocr, "cloud_readers", lambda: []):
            self.assertIsNone(ocr._second_opinion(text, boxes, img))

    def test_korean_named_with_its_pack_stands(self):
        img, _ = page(ZH, CJK_FONT)
        with mock.patch.object(ocr, "_has_pack", lambda head: True):
            self.assertIsNone(ocr._second_opinion("오늘은 날씨가 좋다",
                                                  JUNK, img, source="ko"))

    def test_english_beside_a_photo_stands(self):
        img, boxes = page(EN, LATIN_FONT, photo=True)
        self.assertIsNone(ocr._second_opinion(" ".join(EN), boxes, img))

    def test_a_latin_language_named_is_trusted(self):
        img, _ = page(ZH, CJK_FONT)
        self.assertIsNone(ocr._second_opinion(JUNK[0]["text"], JUNK, img,
                                              source="de"))

    def test_with_a_chinese_pack_windows_stands(self):
        img, _ = page(ZH, CJK_FONT)
        with mock.patch.object(ocr, "_cjk_pack_installed", lambda: True):
            self.assertIsNone(ocr._second_opinion(JUNK[0]["text"], JUNK,
                                                  img))


class Reading(unittest.TestCase):
    """image_to_lines on a PC with English and Italian packs, no cloud."""

    def read(self, img, windows_lines, paddle_lines):
        with mock.patch.object(ocr, "use_windows_ocr", lambda: True), \
                mock.patch.object(ocr, "use_vision", lambda: False), \
                mock.patch.object(ocr, "prefer_cloud_vision", lambda: False), \
                mock.patch.object(ocr, "prefer_gemini_ocr", lambda: False), \
                mock.patch.object(ocr, "cloud_readers", lambda: []), \
                mock.patch.object(ocr, "use_paddle", lambda: True), \
                mock.patch.object(ocr, "_cjk_pack_installed", lambda: False), \
                mock.patch.object(ocr.ocr_windows, "image_to_lines",
                                  lambda i, source=None: (windows_lines,
                                                          "en-GB")), \
                mock.patch.object(ocr, "_paddle_read",
                                  lambda i, s, want_lines=True:
                                  (paddle_lines, "zh", False)), \
                mock.patch.object(ocr, "_clean_lines", lambda l, i: l):
            return ocr.image_to_lines(img)

    def test_chinese_page_is_read_by_paddle(self):
        img, boxes = page(ZH, CJK_FONT)
        lines, used = self.read(img, JUNK, boxes)
        self.assertEqual(used, "zh")
        self.assertEqual(lines[0]["text"], ZH[0])

    def test_single_junk_word_goes_to_paddle(self):
        img, boxes = page(ZH, CJK_FONT)
        junk = [{"text": "L-i*4Dfi7,", "box": (30, 30, 200, 30)}]
        lines, used = self.read(img, junk, boxes)
        self.assertEqual(used, "zh")

    def test_english_page_stays_with_windows(self):
        img, boxes = page(EN, LATIN_FONT)
        paddle = [{"text": "Today is the frst day", "box": b["box"]}
                  for b in boxes]
        lines, used = self.read(img, boxes, paddle)
        self.assertEqual(used, "en-GB")


if __name__ == "__main__":
    unittest.main()


class WithAllPacks(unittest.TestCase):
    """A PC whose Windows reads Chinese, Japanese and Korean: the slow
    reader only for a reading that is plainly rubbish (1.48.44 asked it on
    every small doubt: 5-9 s a snip on a 4K screen)."""

    def setUp(self):
        for p in (mock.patch.object(ocr, "use_paddle", lambda: True),
                  mock.patch.object(ocr, "_cjk_pack_installed", lambda: True)):
            p.start()
            self.addCleanup(p.stop)

    def test_small_doubt_stands(self):
        self.assertIsNone(ocr._second_opinion(
            "Il corso forma esperti L61E in grado", None, None))

    def test_rubbish_still_asks(self):
        self.assertEqual(ocr._second_opinion(
            "iRERJXIJXFL8Y }RERJXlJXFL8Y xkcdqwrtz", None, None), "misread")


class Background(unittest.TestCase):
    """The read-ahead never runs the slow reader; it notes that it needed
    it, and the snip reads the page itself."""

    def test_quick_only_skips_and_says_so(self):
        img, boxes = page(ZH, CJK_FONT)
        asked = []
        with mock.patch.object(ocr, "use_windows_ocr", lambda: True), \
                mock.patch.object(ocr, "use_vision", lambda: False), \
                mock.patch.object(ocr, "prefer_cloud_vision", lambda: False), \
                mock.patch.object(ocr, "prefer_gemini_ocr", lambda: False), \
                mock.patch.object(ocr, "cloud_readers", lambda: []), \
                mock.patch.object(ocr, "use_paddle", lambda: True), \
                mock.patch.object(ocr, "_cjk_pack_installed", lambda: False), \
                mock.patch.object(ocr.ocr_windows, "image_to_lines",
                                  lambda i, source=None: (JUNK, "en-GB")), \
                mock.patch.object(ocr, "_paddle_read",
                                  lambda *a, **k: asked.append(1)), \
                mock.patch.object(ocr, "_clean_lines", lambda l, i: l):
            with ocr.quick_only():
                ocr.image_to_lines(img)
                self.assertTrue(ocr.skipped_slow())
        self.assertEqual(asked, [])

    def test_doubtful_page_not_used_for_a_snip(self):
        from app import preread
        reader = preread.Reader.__new__(preread.Reader)
        img, _ = page(ZH, CJK_FONT)
        p = preread.Page(img, {"left": 0, "top": 0}, 1.0, JUNK, "en", None,
                         0.1)
        p.doubtful = True
        with mock.patch.object(reader, "current", lambda wait=0: p,
                               create=True), \
                mock.patch.object(preread, "enabled", lambda: True):
            reader.reading = __import__("threading").Event()
            self.assertIsNone(reader.lines_for(img, (0, 0, img.width,
                                                     img.height), 0, 0,
                                               wait=False))


class LatinTie(unittest.TestCase):
    def test_pack_of_the_language_wins(self):
        from app import ocr_windows as ow
        texts = {"ru-RU": "11 corso forma esperti in grado di analizzare",
                 "it-IT": "Il corso forma esperti in grado di analizzare"}
        self.assertEqual(ow._judge_part(texts), "it-IT")

    def test_latin_pack_over_non_latin_pack(self):
        from app import ocr_windows as ow
        texts = {"ru-RU": "Il corso forma esperti", "en-US": "Il corso forma esperti"}
        self.assertEqual(ow._judge_part(texts), "en-US")
