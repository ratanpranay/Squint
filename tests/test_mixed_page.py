"""A page in several languages is read part by part, each part by the
language pack that reads it in its own script."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ocr_windows import merge_readings  # noqa: E402


def line(text, x, y, w=300, h=20):
    return {"text": text, "box": (x, y, w, h)}


def reading(tag, lines):
    return (tag, lines, " ".join(l["text"] for l in lines))


class MergeTests(unittest.TestCase):
    def test_each_part_in_its_own_script(self):
        de = reading("de-DE", [
            line("Mit großem Interesse habe ich Ihren Artikel gelesen.", 10, 10),
            line("EI 700/0 @71RIQ.", 10, 60),
            line("10É4a&12É14ao", 400, 60),
        ])
        ko = reading("ko-KR", [
            line("Mit gro 금 Interesse habe ich lhren Artikel gelesen.", 10, 11),
            line("흐리고 비 · 강수확률 70%", 10, 60),
            line("딘 여샤 대장", 400, 60),
        ])
        ja = reading("ja-JP", [
            line("会期：10月4日～12月14日", 400, 61),
            line("エ 700/0", 10, 61),
        ])
        lines, tag = merge_readings([de, ko, ja])
        texts = [l["text"] for l in lines]
        self.assertIn("Mit großem Interesse habe ich Ihren Artikel gelesen.",
                      texts)
        self.assertIn("흐리고 비 · 강수확률 70%", texts)
        self.assertIn("会期：10月4日～12月14日", texts)
        self.assertEqual(len(texts), 3)

    def test_junk_from_a_latin_pack_where_nothing_else_read_is_dropped(self):
        de = reading("de-DE", [line("}RERJXlJXFL8Y iRERJXIJ", 10, 10)])
        zh = reading("zh-Hans-CN", [line("员工行为准则", 10, 200)])
        lines, tag = merge_readings([de, zh])
        self.assertEqual([l["text"] for l in lines], ["员工行为准则"])
        self.assertEqual(tag, "zh-Hans-CN")

    def test_single_language_page_is_unchanged(self):
        de = reading("de-DE", [line("Erste Zeile hier.", 10, 10),
                               line("Zweite Zeile dort.", 10, 40)])
        zh = reading("zh-Hans-CN", [line("Erste Zeile hier.", 10, 10),
                                    line("Zweite Zei1e dort.", 10, 40)])
        lines, tag = merge_readings([de, zh])
        self.assertEqual([l["text"] for l in lines],
                         ["Erste Zeile hier.", "Zweite Zeile dort."])


if __name__ == "__main__":
    unittest.main()


class MemoryTests(unittest.TestCase):
    def test_changing_a_translation_setting_forgets_translations(self):
        from unittest import mock
        from app import config, translator, xray
        translator._cache_put(("x",), "old")
        translator._block_put("en", [("ein langer Satz mit genug Worten", "a")],
                              "hymt")
        xray._cache_put(("page",), ["blocks"])
        with mock.patch.object(type(config.CONFIG), "save", lambda self: None), \
                mock.patch.dict(config.CONFIG, {"target_lang": "en"}):
            config.CONFIG.set("target_lang", "xx-test")
        self.assertIsNone(translator._cache_get(("x",)))
        self.assertEqual(translator._blocks, {})
        self.assertIsNone(xray._cache_get(("page",)))

    def test_engine_choice_is_part_of_what_is_remembered(self):
        from unittest import mock
        from app import profile, translator
        with mock.patch.object(profile, "current", lambda: "local"):
            translator._cache_put(("y",), "offline answer")
        with mock.patch.object(profile, "current", lambda: "groq"):
            self.assertIsNone(translator._cache_get(("y",)))
        with mock.patch.object(profile, "current", lambda: "local"):
            self.assertEqual(translator._cache_get(("y",)), "offline answer")
