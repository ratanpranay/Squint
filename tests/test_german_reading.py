"""Latin pages read with more than one language pack: real words are kept,
and the pack that knows the letters wins a tie."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import ocr, ocr_windows as ow  # noqa: E402


class RealWordsAreKept(unittest.TestCase):
    WORDS = ["Fahrradhändler", "Datenschutzerklärung", "Gesellschaftsform",
             "Postleitzahl", "(geschäftlich)", "Rechtsschutzversicherung",
             "Selbstständige", "Kfz-Haftpflichtversicherung", "E-Mail-Adresse",
             "Herbststurm", "Wirtschaftsprüfungsgesellschaft", "Öffnungszeiten",
             "Überweisung", "Schwarzschild", "Wszystkich", "przepływ",
             "Skłodowska", "iPhone", "YouTube", "McDonald", "PowerPoint"]
    NOISE = ["iRERJXIJXFL8Y", "}RERJXlJXFL8Y", "xkcdqwrtz", "zhdrqpt",
             "qwrtplk", "L61E3xQ"]

    def test_words_are_not_noise(self):
        for w in self.WORDS:
            self.assertFalse(ow._is_jumble(w), w)

    def test_noise_is_noise(self):
        for w in self.NOISE:
            self.assertTrue(ow._is_jumble(w), w)

    def test_single_word_label_is_read(self):
        for w in ("Gesellschaftsform", "Fahrradhändler", "Datenschutzerklärung",
                  "Postleitzahl"):
            self.assertEqual(ow._judge_part({"en-US": w}), "en-US", w)

    def test_noise_line_still_dropped(self):
        self.assertIsNone(ow._judge_part({"en-US": "}RERJXlJXFL8Y"}))


class TieGoesToThePackThatKnowsTheLetters(unittest.TestCase):
    def test_umlaut_reading_wins(self):
        for en, de in (("0ber uns", "Über uns"), ("Uber uns", "Über uns"),
                       ("pers6nlich beraten", "persönlich beraten"),
                       ("Vorteile fur Sie", "Vorteile für Sie")):
            self.assertEqual(ow._judge_part({"en-US": en, "de-DE": de}),
                             "de-DE", en)
            self.assertEqual(ow._judge_part({"de-DE": de, "en-US": en}),
                             "de-DE", en)

    def test_whole_page_choice_agrees(self):
        picked = ow.choose_reading([("en-US", [], "0ber uns pers6nlich"),
                                    ("de-DE", [], "Über uns persönlich")])
        self.assertEqual(picked[0], "de-DE")

    def test_units_are_not_misreads(self):
        self.assertEqual(ow.latin_rank("5min 10km 2nd")[0],
                         ow.reading_score("5min 10km 2nd"))


class Debris(unittest.TestCase):
    def test_specks_are_dropped(self):
        self.assertTrue(ocr.is_debris('| "If | "If'))
        self.assertTrue(ocr.is_debris("i | l | /"))

    def test_marks_and_short_text_are_kept(self):
        for t in ("•", "a)", "(i)", "z.B.", "e.V.", "Ja / Nein", "1 | 2 | 3",
                  "中 | 文 | 字", "OK", "§ 5"):
            self.assertFalse(ocr.is_debris(t), t)


if __name__ == "__main__":
    unittest.main()


class FootnoteNotACode(unittest.TestCase):
    def test_word_before_a_footnote_is_not_a_code(self):
        from app import identifiers
        self.assertEqual(identifiers.find("einer Woche Hausarrest.[15]"), [])
        self.assertEqual(identifiers.find("in Haft genommen[5][6] und"), [])
        self.assertIn("XC60", identifiers.find("Modell XC60 und L8Y"))
