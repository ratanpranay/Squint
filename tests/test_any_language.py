"""Any language to any language: text already in the target language is
left as it is, and the offline model is not asked for languages it does
not write."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config, langid, offline_model, profile, translator  # noqa

try:
    import langdetect  # noqa: F401
    HAVE_DETECTOR = True
except Exception:
    HAVE_DETECTOR = False


class InLanguage(unittest.TestCase):
    def test_scripts(self):
        cases = [
            (u"今天是小明的第一天上学。", "zh-CN", True),
            (u"今天是小明的第一天上学。", "ja", None),
            (u"銀杏のにおい、食べる部分が臭い", "ja", True),
            (u"銀杏のにおい、食べる部分が臭い", "zh-CN", False),
            (u"오늘은 날씨가 좋아서 공원에 갔습니다", "ko", True),
            (u"오늘은 날씨가 좋아서 공원에 갔습니다", "ja", False),
            (u"Сегодня хорошая погода, мы идём в парк", "ru", True),
            (u"Сьогодні гарна погода, ми йдемо в парк", "ru", False),
            (u"Сьогодні гарна погода, ми йдемо в парк", "uk", True),
            (u"مرحبا بكم في المدينة", "ar", True),
            (u"Hello there, how are you today", "zh-CN", False),
            (u"Hello there, how are you today", "hi", False),
            (u"9/29 10:40", "de", None),
        ]
        for text, target, want in cases:
            self.assertEqual(langid.in_language(text, target), want,
                             (text, target))

    @unittest.skipUnless(HAVE_DETECTOR, "language detector not installed")
    def test_latin(self):
        de = u"Die Bundesregierung beteuert es nahezu täglich"
        self.assertTrue(langid.in_language(de, "de"))
        self.assertFalse(langid.in_language(de, "en"))
        self.assertIsNone(langid.in_language(u"Pflege, Rente", "de"))

    def test_same_script(self):
        self.assertTrue(langid.same_script(u"Pflege, Rente", "de"))
        self.assertFalse(langid.same_script(u"Pflege, Rente", "ja"))


@unittest.skipUnless(HAVE_DETECTOR, "language detector not installed")
class LeftAsItIs(unittest.TestCase):
    PAGE = [u"Die Bundesregierung beteuert es nahezu täglich: Deutschland",
            u"Über diese Reformen diskutiert Schwarz-Rot seit Wochen heftig",
            u"Pflege, Rente, Gesundheit",
            u"今天是小明的第一天上学。"]

    def run_page(self, target):
        sent = []

        def fake(lines, target, source, job, blocks):
            sent.extend(lines)
            return ["T:" + l for l in lines]
        with mock.patch.object(translator, "_translate_lines", fake), \
                mock.patch.object(translator, "_block_get",
                                  lambda *a: None), \
                mock.patch.object(translator, "_block_put",
                                  lambda *a: None):
            out = translator.translate_lines(list(self.PAGE), target,
                                             blocks=True)
        return out, sent

    def test_german_page_into_german(self):
        out, sent = self.run_page("de")
        self.assertEqual(sent, [self.PAGE[3]])
        self.assertEqual(out[:3], self.PAGE[:3])

    def test_german_page_into_english(self):
        out, sent = self.run_page("en")
        self.assertEqual(len(sent), 4)


class OfflineWrites(unittest.TestCase):
    def test_list(self):
        for code in ("en", "de", "zh-CN", "zh-TW", "ja", "ko", "ar", "hi",
                     "ru", "uk", "fr", "es", "it", "pt", "vi", "th"):
            self.assertTrue(offline_model.writes(code), code)
        for code in ("sv", "no", "da", "fi", "hu", "sk", "ml", "pa", "el"):
            self.assertFalse(offline_model.writes(code), code)

    def test_automatic_does_not_ask_it(self):
        with mock.patch.object(profile, "current", lambda: profile.AUTO), \
                mock.patch.object(profile, "_hymt_ready", lambda: True), \
                mock.patch.dict(config.CONFIG, {"target_lang": "sv"}):
            order, _ = profile.translating(profile.SPEED)
        self.assertNotIn("hymt", order)
        with mock.patch.object(profile, "current", lambda: profile.AUTO), \
                mock.patch.object(profile, "_hymt_ready", lambda: True), \
                mock.patch.dict(config.CONFIG, {"target_lang": "de"}):
            order, _ = profile.translating(profile.SPEED)
        self.assertEqual(order[0], "hymt")


if __name__ == "__main__":
    unittest.main()
