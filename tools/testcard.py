"""Pages built to make faults visible, for testing against a real engine.

The corpus pages are documents somebody found. These are documents made on
purpose, each carrying the things that are known to go wrong and cannot be
checked from a machine with no engine on it:

  codes       a part number, an order number, a card number, a version, an
              email, a URL, a phone number — inside sentences, where the
              engine can retype them and the reader cannot tell.
  dates       written the source language's way, which the engine *should*
              change and the app must not drag back.
  columns     two of them, so a paragraph gathered wrongly shows up as a
              sentence that starts nowhere.
  a table     with cells of very different lengths, so a row that has to
              grow can be seen growing.
  a quotation with the punctuation that must not begin a line.
  small print at the bottom, which is where text set too small shows first.

Each page is written out with a key naming what a correct answer contains,
so a test is a comparison rather than an impression.

    python tools/testcard.py <folder> [name]
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw                              # noqa: E402

from app import identifiers, overlay                          # noqa: E402

WIDTH = 1000
MARGIN = 60
GUTTER = 40

CARDS = {}

CARDS["visitors-zh"] = {
    "lang": "zh-CN",
    "title": "关于新访客管理系统上线及门禁卡更换的通知",
    "sub": "文件编号 GT-2026-114 ｜ 发布日期 2026年9月14日 ｜ 密级：内部",
    "left": [
        "公司将于2026年9月28日启用新的访客管理系统（系统名称 VisitorHub，"
        "版本 v3.2），届时所有外部访客须由接待人员提前在系统中登记，并在到访"
        "当日凭二维码通行。旧系统将于同日18:00停止服务。",
        "请各部门于9月25日前将常驻承包商名单提交至 "
        "facility-ops@example.internal，逾期提交的名单需重新走审批流程，"
        "处理时间约为三个工作日。",
    ],
    "right": [
        "门禁卡将统一更换为新卡（型号 KX-9B），旧卡在10月10日之后不再有效。"
        "更换地点为一号楼前台，办理时请携带工号与身份证件，现场不接受代办。",
        "如遇读卡器故障，请拨打内线 8137 或发送邮件说明卡号（例如 "
        "CARD-000482）。夜间与周末的紧急情况请联系值班人员，"
        "电话 +49 89 1234 5678。",
    ],
    "head": ["系统", "停用时间段", "负责人", "备注"],
    "rows": [
        ["访客登记", "9月28日 01:00 - 04:00", "王建国", "需提前导出名单"],
        ["门禁主机", "9月28日 02:00 - 05:30", "李静",
         "影响一号楼与二号楼，含地下车库入口"],
        ["考勤接口", "9月28日 03:00 - 06:00", "A. Weber",
         "与工资系统同步暂停"],
    ],
    "list": [
        "请在9月26日18:00前确认本部门访客名单，逾期系统将按空名单处理。",
        "切换期间请勿修改门禁权限设置，相关改动将不会保存。",
        "次日09:00前将本部门的卡片更换情况反馈至 "
        "facility-ops@example.internal。",
    ],
    "quote": "项目负责人表示：“新系统的目的不是增加流程，而是让访客在前台"
             "等待的时间从平均十二分钟缩短到三分钟。”（详见内部公告 "
             "GT-2026-115）",
    "foot": "本通知自发布之日起生效；解释权归行政与设施管理部所有。"
            "未经许可不得转发至第三方。 联系人：行政与设施管理部 张伟 ｜ "
            "facility-ops@example.internal ｜ 分机 8137 ｜ 参考号 GT-2026-114",
    "meaning": [
        "The company starts a new visitor management system on 28 "
        "September 2026 (VisitorHub, version v3.2). External visitors must "
        "be registered in advance by their host and enter with a QR code. "
        "The old system stops at 18:00 the same day.",
        "Departments must send the list of resident contractors to "
        "facility-ops@example.internal before 25 September; a late list "
        "goes through approval again, which takes about three working "
        "days.",
        "Access cards are replaced with a new model, KX-9B. Old cards stop "
        "working after 10 October. Collect the new one at the Building 1 "
        "reception with your staff number and an ID; nobody may collect on "
        "your behalf.",
        "If a card reader fails, call extension 8137 or send an email "
        "quoting the card number, for example CARD-000482. Out of hours, "
        "call the duty officer on +49 89 1234 5678.",
        "The table lists three systems, the window each is down for on 28 "
        "September, who owns it, and a note. The second note is longer "
        "than the others: it affects Buildings 1 and 2 including the "
        "underground car park entrance.",
        "Three instructions: confirm the visitor list before 18:00 on 26 "
        "September or the system treats it as empty; do not change access "
        "permissions during the switch, changes will not be saved; report "
        "your department's card replacement by 09:00 the next day.",
        "A quotation from the project lead: the point of the new system is "
        "not more process but cutting the average wait at reception from "
        "twelve minutes to three. See internal notice GT-2026-115.",
        "The small print: the notice takes effect on the day of issue, the "
        "facilities department is the authority on its interpretation, and "
        "it may not be forwarded outside the company without permission.",
    ],
}


def write(draw, text, font, x, y, width, colour, lines, kind, leading=None):
    lead = leading or int(font.size * 1.5)
    for row in overlay._wrap(draw, text, font, width):
        draw.text((x, y), row, font=font, fill=colour)
        box = draw.textbbox((x, y), row, font=font)
        lines.append({"box": (box[0], box[1], max(1, box[2] - box[0]),
                              max(1, box[3] - box[1])),
                      "text": row, "kind": kind})
        y += lead
    return y


def build(name):
    card = CARDS[name]
    kind = overlay._font_family_for(card["lang"])
    body = overlay.load_font(kind, 16)
    small = overlay.load_font(kind, 11)
    sub = overlay.load_font(kind, 12)
    title = overlay.load_font(kind, 28)

    page = Image.new("RGB", (WIDTH, 1600), "white")
    draw = ImageDraw.Draw(page)
    lines = []
    column = (WIDTH - 2 * MARGIN - GUTTER) // 2

    y = write(draw, card["title"], title, MARGIN, MARGIN,
              WIDTH - 2 * MARGIN, (17, 24, 39), lines, "title",
              int(28 * 1.4))
    y += 4
    y = write(draw, card["sub"], sub, MARGIN, y, WIDTH - 2 * MARGIN,
              (90, 96, 110), lines, "sub", int(12 * 1.7))
    y += 12
    draw.line([MARGIN, y, WIDTH - MARGIN, y], fill=(30, 58, 95), width=2)
    y += 22

    top = y
    left = top
    for para in card["left"]:
        left = write(draw, para, body, MARGIN, left, column,
                     (25, 28, 34), lines, "prose") + 12
    right_x = MARGIN + column + GUTTER
    right = top
    for para in card["right"]:
        right = write(draw, para, body, right_x, right, column,
                      (25, 28, 34), lines, "prose") + 12

    y = max(left, right) + 26
    at = [MARGIN, MARGIN + 190, MARGIN + 420, MARGIN + 560]
    widths = [180, 220, 130, 260]
    draw.rectangle([MARGIN - 8, y - 8, WIDTH - MARGIN + 8, y + 24],
                   fill=(30, 58, 95))
    for text, x, width in zip(card["head"], at, widths):
        write(draw, text, body, x, y, width, (255, 255, 255), lines, "head")
    y += 40
    for number, row in enumerate(card["rows"]):
        if number % 2:
            draw.rectangle([MARGIN - 8, y - 8, WIDTH - MARGIN + 8, y + 44],
                           fill=(244, 246, 250))
        bottom = y
        for text, x, width in zip(row, at, widths):
            bottom = max(bottom, write(draw, text, body, x, y, width,
                                       (25, 28, 34), lines, "cell"))
        y = bottom + 18

    y += 14
    for number, item in enumerate(card["list"], 1):
        y = write(draw, "%d. %s" % (number, item), body, MARGIN, y,
                  WIDTH - 2 * MARGIN, (25, 28, 34), lines, "item") + 8

    y += 16
    draw.rectangle([MARGIN - 10, y - 10, WIDTH - MARGIN + 10, y + 62],
                   outline=(210, 214, 222))
    y = write(draw, card["quote"], body, MARGIN + 4, y + 2,
              WIDTH - 2 * MARGIN - 8, (40, 44, 52), lines, "quote") + 22

    y += 18
    draw.line([MARGIN, y, WIDTH - MARGIN, y], fill=(190, 194, 202))
    y += 12
    y = write(draw, card["foot"], small, MARGIN, y, WIDTH - 2 * MARGIN,
              (110, 116, 126), lines, "foot", int(11 * 1.7))

    return page.crop((0, 0, WIDTH, min(1600, y + MARGIN))), lines, card


def main():
    out = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else "visitors-zh"
    os.makedirs(out, exist_ok=True)
    page, lines, card = build(name)
    page.save(os.path.join(out, "%s.png" % name))
    # From the paragraphs, not from the drawn lines: a code that happens
    # to be wrapped across two lines is one code, and asking each line
    # about it separately finds two halves.
    codes = []
    whole = []
    for key in ("title", "sub", "quote", "foot"):
        whole.append(card[key])
    for key in ("left", "right", "list"):
        whole.extend(card[key])
    for row in card["rows"]:
        whole.extend(row)
    for text in whole:
        for token in identifiers.find(text):
            if token not in codes:
                codes.append(token)
    key = {"page": name, "language": card["lang"], "size": page.size,
           "codes_that_must_come_back_exactly": codes,
           "what_it_says": card["meaning"]}
    with open(os.path.join(out, "%s-key.json" % name), "w",
              encoding="utf-8") as fh:
        json.dump(key, fh, ensure_ascii=False, indent=2)
    print("%s  %dx%d  %d lines  %d codes"
          % (name, page.size[0], page.size[1], len(lines), len(codes)))
    for token in codes:
        print("   ", token)


if __name__ == "__main__":
    main()
