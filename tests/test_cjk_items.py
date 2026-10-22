"""Chinese list items, each a line ending in ；, stay apart."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import overlay  # noqa: E402


def line(text, y, w):
    return {"text": text, "box": (40, y, w, 22), "conf": 95}


class Items(unittest.TestCase):
    def test_items_ending_in_semicolon_are_separate(self):
        lines = [line("请各位同事提前保存好相关业务系统内的未提交数据；", 100, 780),
                 line("维护影响范围较大，如无必要，建议避开维护时间段内现场加班；", 130, 650),
                 line("维护结束后，相关系统将自动恢复访问；", 160, 380),
                 line("维护结束后如遇访问异常，可联系桌面帮助台处理。", 190, 1100)]
        groups = overlay.group_paragraphs(lines)
        self.assertEqual(len(groups), 4)

    def test_wrapped_chinese_paragraph_still_joins(self):
        lines = [line("为进一步提升办公网络架构的安全性与稳定性，保障后续业务系统", 100, 1100),
                 line("的高效运行，保障部计划于本周五对数据中心办公网核心防火墙", 130, 1100),
                 line("设备进行更换升级。", 160, 300)]
        self.assertEqual(len(overlay.group_paragraphs(lines)), 1)


if __name__ == "__main__":
    unittest.main()
