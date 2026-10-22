import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import ocr_windows  # noqa: E402


class Misread(unittest.TestCase):
    def test_a_german_page_with_long_compounds_is_trusted(self):
        text = ("Noch mehr Optionen mit PayPal Ratenzahlung: Zahle bequem in "
                "drei bis 24 monatlichen Raten. Wir buchen die Raten "
                "automatisch von deiner Zahlungsquelle ab. "
                "Rechtsschutzversicherung Vorbehaltlich "
                "Kreditwürdigkeitsprüfung")
        self.assertFalse(ocr_windows.might_be_misread(text))

    def test_a_short_jumbled_reading_still_asks(self):
        self.assertTrue(ocr_windows.might_be_misread("}RERJXlJXFL8Y abc"))


if __name__ == "__main__":
    unittest.main()
