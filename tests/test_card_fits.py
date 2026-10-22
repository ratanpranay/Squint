"""The translation card fits its text: nothing cut off, a short phrase in
a small card."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import tkinter as tk
    from app import ui_result
    root = tk.Tk()
    root.withdraw()
except Exception:                     # pragma: no cover
    root = None

KO = (u"초기에는 관리자의 역량은 삭제하는 것에만 국한되었습니다. 측면에서의 방어와, "
      u"알리지지 않은 사용자들의 접근을 차단하는 것. 서버 관리자는 데이터베이스를 "
      u"직접 처리해야 했으며, 라이선도 마찬가지였습니다. 선거 결과에 따라 관리자 "
      u"권한이 부여됩니다. 2004년 2월 25일부터는 등록된 사용자를 차단하는 기능이 "
      u"활성화되었습니다. 보안상의 이유로, 2005년에 그 기능이 중단되었습니다.")


@unittest.skipIf(root is None, "no display")
class Fits(unittest.TestCase):
    def card(self, text):
        c = ui_result.ResultPopup(root, text, "", "selection → Korean",
                                  show_original=False)
        root.update()
        self.addCleanup(lambda: (c.close(), root.update()))
        return c

    def test_long_korean_is_not_cut_off(self):
        c = self.card(KO)
        self.assertEqual(c.text.yview(), (0.0, 1.0))

    def test_short_phrase_small_card(self):
        small = self.card(u"디자인 리더")
        big = self.card(KO)
        self.assertLess(small.winfo_height(), big.winfo_height())
        self.assertLessEqual(small.winfo_width(), big.winfo_width())
        self.assertEqual(small.text.yview(), (0.0, 1.0))


if __name__ == "__main__":
    unittest.main()
