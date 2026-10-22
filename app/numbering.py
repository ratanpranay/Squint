"""A numbered point keeps its number, in front of it.

A list marker is not language, and an engine handed one reads it as if it
were. On a Chinese notice with items written "1、" "2、" and section
headings "一、" "二、" "三、", translated into Korean and English in one
request, every one of them came back wrong in a different way:

    1、维护期间，…设计软件；   →  …중단됩니다. 1            (moved to the end)
    2、设计网内部终端…          →  …작업은 2 설계 네트워크…  (read as "2 design networks")
    一、维护时间                →  一유지보수 시간            (left, glued on)
    二、影响范围                →  I. 영향 범위               (renumbered)
    三、注意事项                →  三, 주의사항               (left, 、 made a comma)

"、" is the Chinese list comma, so "2、设计网" really can be read as "two,
design networks". There is nothing to repair afterwards: the number is
somewhere else in the sentence, or gone.

So the marker is taken off before the engine sees the paragraph and put
back in front of what comes back. The engine translates the point; the
number is never its to move.

Chinese section numerals come back as Roman numerals — I. II. III. — in a
target that does not read Chinese, which is how Korean and English
documents number sections above a 1. 2. 3. list. In Chinese or Japanese
the original marker goes back exactly as it was.
"""
import re

_HAN_DIGITS = "一二三四五六七八九十"

# Each kind of marker, and how it is written back outside Chinese and
# Japanese. Tried in order; the first that matches at the start wins.
#
# ASCII "1." as well as "1、" and "1．": the engine turned "1." into "1," on
# a Korean page, and a marker that is never sent cannot be retyped.
# `(?!\d)` so that 1.5 kg is a quantity and not item one.
_KINDS = (
    ("han", re.compile(r"^\s*([一二三四五六七八九十]{1,3})\s*[、．.]\s*")),
    ("han_paren", re.compile(
        r"^\s*[(（]\s*([一二三四五六七八九十]{1,3})\s*[)）]\s*[、．.]?\s*")),
    ("paren", re.compile(r"^\s*[(（]\s*(\d{1,2})\s*[)）]\s*[、．.]?\s*")),
    ("dot", re.compile(r"^\s*(\d{1,2})\s*(?:[、．]|\.(?!\d))\s*")),
    ("close", re.compile(r"^\s*(\d{1,2})\s*[)）]\s*")),
    ("circled", re.compile(r"^\s*([①-⑳])\s*")),
    # Bullets. Sent with the text they came back moved, dropped or turned
    # into words; taken off and put back, they stay where they were.
    ("bullet", re.compile(r"^\s*([•·・●○■□◆◇▶►▸›»※▪◦‣∙])\s*")),
    # A dash and a space, the way a list is typed into a plain text box:
    # "- Neue Züge". Sent with the item, it came back on some and not on
    # others, so a list lost its dashes half way down.
    ("dash", re.compile(r"^\s*([-–—])\s+(?=\S)")),
)

# A 、 on its own at the start: the numeral in front of it was not read.
# Sent as it is, it comes back as a comma at the head of the sentence.
_ORPHAN = re.compile(r"^\s*[、，,]\s*")

_ROMAN = ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))


def han_number(text):
    """一 → 1, 十二 → 12, 二十 → 20. None if it is not a number."""
    text = str(text or "")
    if not text or any(ch not in _HAN_DIGITS for ch in text):
        return None
    value = {ch: i + 1 for i, ch in enumerate(_HAN_DIGITS)}
    if "十" not in text:
        return value[text] if len(text) == 1 else None
    tens, _, ones = text.partition("十")
    if len(tens) > 1 or len(ones) > 1 or "十" in ones:
        return None
    return (value[tens] if tens else 1) * 10 + (value[ones] if ones else 0)


def roman(number):
    out = []
    for value, letters in _ROMAN:
        while number >= value:
            out.append(letters)
            number -= value
    return "".join(out)


def _has_words(text):
    """Something after the marker to translate — not just more digits."""
    return any(ch.isalpha() for ch in text)


# What a reader returns for 一 and 二 at the head of a heading, when it
# reads the single stroke as a dash or picks the radical of the same shape.
# Only ever changed where a 、 follows, which is what makes it a numeral.
_LOOKALIKE = (
    (re.compile(r"^(\s*)[—―－ー⼀-](\s*[、．])"), "一"),
    (re.compile(r"^(\s*)[⼆＝=](\s*[、．])"), "二"),
    (re.compile(r"^(\s*)[≡☰](\s*[、．])"), "三"),
)


def split(text):
    """`(marker, rest)`. `marker` is None when there is none to take off.

    A marker is a dict: its kind, its number and the exact characters it
    was written with, so that it can go back unchanged in a language that
    writes it that way.
    """
    text = str(text or "")
    for pattern, numeral in _LOOKALIKE:
        text = pattern.sub(lambda m: m.group(1) + numeral + m.group(2), text,
                           count=1)
    for kind, pattern in _KINDS:
        found = pattern.match(text)
        if not found:
            continue
        rest = text[found.end():]
        if not _has_words(rest):
            return None, text
        return {"kind": kind, "value": found.group(1),
                "written": found.group(0).strip()}, rest
    found = _ORPHAN.match(text)
    if found and _has_words(text[found.end():]):
        return {"kind": "orphan", "value": "", "written": ""}, \
            text[found.end():]
    return None, text


def _keeps_original(target):
    target = str(target or "").lower()
    return target.startswith("zh") or target.startswith("ja")


def written_for(marker, target):
    """How the marker is written in front of a translation into `target`."""
    if not marker or marker["kind"] == "orphan":
        return ""
    kind, value = marker["kind"], marker["value"]
    if _keeps_original(target):
        return marker["written"]
    if kind == "han":
        number = han_number(value)
        return roman(number) + "." if number else marker["written"]
    if kind == "han_paren":
        number = han_number(value)
        return "(%d)" % number if number else marker["written"]
    if kind == "paren":
        return "(%s)" % value
    if kind == "dot":
        return value + "."
    if kind == "close":
        return value + ")"
    if kind == "bullet":
        # The Japanese middle dot reads as punctuation elsewhere.
        return "•" if value in ("・", "·") else value
    if kind == "dash":
        return value
    return marker["written"]                        # circled: universal


# What an engine may have put at the head of the answer anyway, when it
# was asked to translate a sentence that no longer had a marker: the same
# number, with punctuation. Only the same number — "3, 4 and 5 are…" is a
# sentence that starts with a number, not a second marker.
_LEADING = re.compile(r"^\s*[(（]?\s*([0-9]{1,2}|[IVXivx]{1,4}|[一二三四五六七八九十]{1,3})"
                      r"\s*[)）]?\s*[.、．,，)]\s*")


def _same_number(marker, found):
    value = marker["value"]
    number = han_number(value) if marker["kind"] in ("han", "han_paren") \
        else (int(value) if value.isdigit() else None)
    if number is None:
        return False
    return found in (str(number), roman(number), roman(number).lower(),
                     value)


def attach(marker, translated, target):
    """Put the marker back in front of the translation."""
    text = str(translated or "")
    prefix = written_for(marker, target)
    if not prefix or not text.strip():
        return text
    body = text.lstrip()
    if marker.get("kind") in ("bullet", "dash") and body[:1] in \
            ("-", "–", "—", "•", marker.get("value")) and \
            _has_words(body[1:]):
        body = body[1:].lstrip()        # the engine kept it as well
    found = _LEADING.match(body)
    if found and _same_number(marker, found.group(1)) \
            and _has_words(body[found.end():]):
        body = body[found.end():]
    # Chinese and Japanese write the text straight on after 、 — 一、维护.
    joiner = "" if _keeps_original(target) else " "
    return prefix + joiner + body


def split_all(texts):
    """`(markers, rests)` over a list of paragraphs."""
    markers, rests = [], []
    for text in texts:
        marker, rest = split(text)
        markers.append(marker)
        rests.append(rest)
    return markers, rests


def attach_all(markers, translations, target):
    out = [attach(m, t, target) for m, t in zip(markers, translations)]
    return out + list(translations[len(markers):])
