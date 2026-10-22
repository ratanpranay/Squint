"""An answer that is not its block's translation is asked for again."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import overlay  # noqa: E402

BODY = ("Noch mehr Optionen mit PayPal Ratenzahlung: Zahle bequem in 3 bis "
        "24 monatlichen Raten.")


class Engine:
    def __init__(self):
        self.again = []

    def translate(self, text, target="en", source="auto"):
        self.again.append(text)
        return {"PayPal Ratenzahlung": "PayPal installment payment"}[text]


class Misplaced(unittest.TestCase):
    def test_heading_that_swallowed_the_paragraph_is_redone(self):
        eng = Engine()
        out = overlay._misplaced_again(
            ["PayPal Ratenzahlung", BODY],
            ["Installment Payment Even more options with PayPal "
             "Installments: Pay conveniently in 3 to 24 monthly "
             "installments. We automatically deduct the installments.",
             "Even more options with PayPal installment payments."],
            eng, "en", "de")
        self.assertEqual(out[0], "PayPal installment payment")
        self.assertEqual(eng.again, ["PayPal Ratenzahlung"])

    def test_engine_notes_are_removed(self):
        out = overlay._misplaced_again(
            [BODY], ["Now also on Amazon with up to 48 [unclear - possibly "
                     "referring to a specific payment method] instalments."],
            Engine(), "en", "de")
        self.assertEqual(out[0], "Now also on Amazon with up to 48 "
                                 "instalments.")

    def test_normal_answers_stand(self):
        eng = Engine()
        out = overlay._misplaced_again(["Hallo Welt"], ["Hello world"],
                                       eng, "en", "de")
        self.assertEqual(out, ["Hello world"])
        self.assertEqual(eng.again, [])


if __name__ == "__main__":
    unittest.main()
