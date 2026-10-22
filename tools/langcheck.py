"""Score the ten languages against each other, in both directions.

`langpages.py` writes one page per language and records which paragraph
every line was written as. This reads that back and asks the three
questions the result is judged on:

  paras    did the app gather the lines back into the paragraphs they
           were written as? This is the wording question, and it is asked
           here rather than of the engine on purpose. Squint translates
           through Google, so the words come back the way Google words
           them — as long as Google is handed a paragraph. Handed a line,
           it answers about a line, and that is where "It is pos sible."
           came from. `split` is a paragraph chopped into more than one
           request; `merged` is two paragraphs sent as one.

  overlap  pairs of blocks whose text lands on top of other text.

  offpage  blocks reaching past the edge of the capture.

Reading is not scored here: these pages carry their own true lines, so a
failure is the app's and not the recogniser's. `pagecheck.py` is the one
that goes through the recogniser.

    python tools/langcheck.py <folder from langpages.py> [--grow 1.2]
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from PIL import Image                                         # noqa: E402

from app import overlay                                       # noqa: E402
import langpages                                              # noqa: E402
import pagecheck                                              # noqa: E402

# Enough of each script to make stand-in text that measures like the real
# thing. The engine cannot be reached from a test machine, and its wording
# is not what is being measured — the size and shape of what comes back is.
ALPHABET = {
    "en": "abcdefghijklmnopqrstuvwxyz",
    "de": "abcdefghijklmnopqrstuvwxyzäöüß",
    "fr": "abcdefghijklmnopqrstuvwxyzéèàç",
    "es": "abcdefghijklmnopqrstuvwxyzáéíóñ",
    "it": "abcdefghijklmnopqrstuvwxyzàèéìò",
    "pt": "abcdefghijklmnopqrstuvwxyzãçõáê",
    "ru": "абвгдеёжзийклмнопрстуфхцчшщыэюя",
    "hi": "कखगघचछजझटठडढणतथदधनपफबभमयरलवशषसह",
    "ar": "ابتثجحخدذرزسشصضطظعغفقكلمنهوي",
    "zh-CN": "该部今天宣布一项新政策详情如下规则将从下个月日起生效维护技术",
    "ja": "報告書年次保守技術部実施夜間早朝一部利用担当窓口",
    "ko": "보고시스템연간유지보수기술부수행야간이른아침일부",
}
MARKS = {"hi": "ािीुूेैोौंँ"}
DENSE = {"zh-CN", "ja"}

# Roughly how much longer this language runs than English for the same
# meaning. Used only to make the stand-in the right length.
RUNS = {"en": 1.0, "de": 1.15, "fr": 1.15, "es": 1.15, "it": 1.1,
        "pt": 1.15, "ru": 1.05, "hi": 1.1, "ar": 1.0,
        "zh-CN": 0.55, "ja": 0.6, "ko": 0.95}


class Stand:
    """A translator that answers in the target's own script, at length."""

    SPEED = "speed"

    def __init__(self, code, grow=1.0):
        self.code = code
        self.grow = grow * RUNS.get(code, 1.0)
        self.blocks = []
        self.letters = ALPHABET[code]
        self.marks = MARKS.get(code, "")

    def word(self, seed, length):
        out = []
        for i in range(length):
            out.append(self.letters[(seed * 7 + i * 13) % len(self.letters)])
            if self.marks and i % 3 == 2:
                out.append(self.marks[(seed + i) % len(self.marks)])
        return "".join(out)

    def translate_lines(self, blocks, target=None, job=None):
        self.blocks = list(blocks)
        out = []
        for number, block in enumerate(blocks):
            count = max(1, int(round(pagecheck.words_in(block) * self.grow)))
            if self.code in DENSE:
                out.append("".join(self.word(number * 31 + i, 1)
                                   for i in range(max(1, count))))
            else:
                out.append(" ".join(self.word(number * 31 + i, 3 + (i % 5))
                                    for i in range(count)))
        return out


def grouping(lines):
    """How the app's paragraphs compare with the ones on the page."""
    groups, _held = overlay.paragraphs_for(lines)
    truth = {}
    for index, line in enumerate(lines):
        truth.setdefault(line["pid"], set()).add(index)
    exact = split = merged = 0
    for group in groups:
        pids = {lines[i]["pid"] for i in group}
        if len(pids) > 1:
            merged += 1
            continue
        only = pids.pop()
        if set(group) == truth[only]:
            exact += 1
        else:
            split += 1
    return {"paragraphs": len(truth), "groups": len(groups),
            "exact": exact, "split": split, "merged": merged}


def score(folder, source, target, grow):
    name = source.replace("-", "")
    with open(os.path.join(folder, "%s.json" % name), encoding="utf-8") as fh:
        page = json.load(fh)
    lines = page["lines"]
    image = Image.open(os.path.join(folder, "%s.png" % name)).convert("RGB")
    got = grouping(lines)
    engine = Stand(target, grow)
    texts = overlay.translate_grouped(lines, engine, target)
    blocks, height = overlay.layout(image, lines, texts, target, min_size=7)
    sizes = sorted(block["size"] for block in blocks)
    shrunk = [block for block in blocks
              if block["size"] < 0.8 * max(1, block.get("natural", 0))]
    ratios = sorted(block["size"] / float(max(1, block.get("natural", 1)))
                    for block in blocks)
    got.update({
        "shrunk": len(shrunk),
        "blocks": len(blocks),
        "tightest": int(round(100 * ratios[0])) if ratios else 100,
        "median": int(round(100 * ratios[len(ratios) // 2])) if ratios else 100,
        "overlap": pagecheck.overlapping(blocks),
        "offpage": pagecheck.off_page(blocks, image.width,
                                      height or image.height),
        "smallest": sizes[0] if sizes else 0,
        "grew": int(round(100.0 * (height or image.height) / image.height)),
    })
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--grow", type=float, default=1.0)
    ap.add_argument("--languages", default="")
    args = ap.parse_args()
    codes = (args.languages.split(",") if args.languages
             else langpages.LANGUAGES)

    print("reading each page as its own language")
    print("%-7s %6s %6s %6s %6s" % ("source", "paras", "exact", "split",
                                    "merged"))
    for code in codes:
        got = score(args.folder, code, "en", args.grow)
        print("%-7s %6d %6d %6d %6d" % (code, got["paragraphs"], got["exact"],
                                        got["split"], got["merged"]))

    print("\nlaying every pair out (%d x %d)" % (len(codes), len(codes)))
    print("%-7s %8s %8s %8s %9s %8s %8s"
          % ("source", "overlap", "offpage", "shrunk", "of blocks",
             "tightest", "median"))
    worst = []
    for source in codes:
        overlap = offpage = shrunk = blocks = 0
        tightest, median = 100, 100
        for target in codes:
            got = score(args.folder, source, target, args.grow)
            overlap += got["overlap"]
            offpage += got["offpage"]
            shrunk += got["shrunk"]
            blocks += got["blocks"]
            tightest = min(tightest, got["tightest"])
            median = min(median, got["median"])
            if got["overlap"] or got["offpage"]:
                worst.append((source, target, got["overlap"], got["offpage"]))
        print("%-7s %8d %8d %8d %9d %7d%% %7d%%"
              % (source, overlap, offpage, shrunk, blocks, tightest, median))
    if worst:
        print("\npairs with something drawn over something else:")
        for source, target, over, off in worst:
            print("  %-6s -> %-6s overlap=%d offpage=%d"
                  % (source, target, over, off))
    else:
        print("\nno pair drew text over text or off the page")


if __name__ == "__main__":
    main()
