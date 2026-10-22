"""Codes that must come back the way they went in.

A translation engine is a good writer and an unreliable typist. Hand it a
sentence with a reference number in the middle of it — "please quote
LH-2026-037 when you call" — and the sentence comes back well written, with
the number set as LH‑2026‑037, or LH-2026-O37, or gone. The reader has no
way to tell: the answer is fluent, the code is typeset as neatly as
everything else, and it is wrong.

That is the failure this exists to stop, and it is worse in the case the
app is for. Someone reading a document in a language they do not have
cannot sanity-check a part number against the sentence around it, because
they cannot read the sentence around it. Every other mistake in a
translation is one the reader can catch; this one is not.

So: find the things in the source that a person would copy rather than
read, and after the engine has answered, put them back exactly.

**What counts.** Narrowly, on purpose. An email or a web address; a token
mixing letters and digits (LH-2026-037, ISO9001, v2.1, A4); a long run of
digits with the separators an account or a phone number is written with.

**What deliberately does not.** Dates and times and amounts. "2026年9月18日"
*should* come back as "18 September 2026", and 03:00 - 05:00 as 3 to 5
o'clock if that is how the target language writes it. Forcing the source
form back onto those would be the same fault from the other side.

**How it is put back.** Not by masking the code before translating, which
needs the engine to leave a marker alone, and different engines do
different things to markers — a guess that cannot be tested without the
engine in front of you. Instead the answer is repaired: if the code is
already there, nothing happens; if something of the same shape is there
instead, it is replaced by the original; if it is nowhere, that is
reported rather than papered over.
"""
import difflib
import re

# An email or a web address. Kept separate because these are the ones
# where a wrong answer sends somebody somewhere real.
# ASCII throughout, for the reason given on `_CODE` below and found on a
# real page: `\w` matches a Chinese character, so a local part written as
# `[\w.+-]+` swallowed the whole sentence in front of the address —
# 次日09:00前将本部门的卡片更换情况反馈至facility-ops@example.internal came
# back as one enormous "address", which matches nothing in the answer and
# so was reported missing while the real one, quietly changed from
# example.internal to example.com, went through untouched.
_ADDRESS = re.compile(r"""
    (?<![A-Za-z0-9._%+-])
    (?:[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]*[A-Za-z0-9])
  | (?:https?://[A-Za-z0-9._~:/?#@!$&*+;=%-]+)
  | (?<![A-Za-z0-9.])
    (?:www\.[A-Za-z0-9-]+\.[A-Za-z]{2,}
       (?:/[A-Za-z0-9._~:/?#@!$&*+;=%-]*)?)
""", re.VERBOSE | re.IGNORECASE)

# A token mixing letters and digits: LH-2026-037, ISO9001, v2.1, DN-4A.
# Anchored on both sides so it is a whole token and not the tail of a word.
# The boundaries are ASCII on purpose. `\w` matches a Chinese character,
# and a Chinese document writes a part number straight onto the word
# before it — 型号KX-9B, not 型号 KX-9B — so a boundary that counts 号 as
# part of a word finds no code on the page at all. Codes are written in
# ASCII in every language, which is what makes them codes.
_CODE = re.compile(r"(?<![A-Za-z0-9_/-])"
                   r"(?=[A-Za-z0-9][A-Za-z0-9._/-]*[A-Za-z0-9])"
                   r"(?=[^\s]*[A-Za-z])(?=[^\s]*[0-9])"
                   r"[A-Za-z0-9][A-Za-z0-9._/-]{2,}"
                   r"(?![A-Za-z0-9_-])")

# A long run of digits, with or without the separators an account number,
# an invoice number or a telephone number is written with.
_NUMBER = re.compile(r"(?<![A-Za-z0-9_.,:/-])\+?\d[\d\s.-]{5,}\d"
                     r"(?![A-Za-z0-9_.,:/-])")

# A layout written as numbers added together — the seats in each row of a
# car, 2+2+3; a 5+2; a 4+4+2 shift pattern. Nothing about it is language,
# and an engine will still "translate" it: 2+2+3 七座布局 came back in
# Korean as 7인승(2, 2, 3), which is a different thing to a reader who
# knows these layouts and nothing at all to one who does not. ASCII
# boundaries rather than \w, because Chinese writes it straight onto the
# word after — 2+2+3七座 — and \w counts 七 as part of the word.
_LAYOUT = re.compile(r"(?<![A-Za-z0-9+])\d{1,2}(?:\+\d{1,2}){1,4}"
                     r"(?![A-Za-z0-9+])")

# Things that look like codes and are not: a date, a time, a year, an
# amount. These come back changed on purpose — a date written 2026年9月18日
# is meant to arrive as 18 September 2026 — so they are left alone.
_NOT_A_CODE = re.compile(r"""
    ^(?:
        \d{1,2}[.:/-]\d{2}(?:[.:/-]\d{2,4})?      # 18:00, 18.09.2026
      | \d{4}[.:/-]\d{1,2}[.:/-]\d{1,2}           # 2026-09-18
      | \d{1,4}                                    # a bare number or year
      | \d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?          # 1.284,00
      | \d{1,4}(?:st|nd|rd|th)                      # 23rd, 9th
      | (?-i:\d+-?[a-z]{2,})                       # 10-fach, 1990er, 3-mal
      | (?-i:\d+-[A-Z][a-z]{2,})                   # 32-Loch, 10-Gang
      | \d+(?:[.,]\d+)?\s?(?:eur|usd|gbp|chf|inr|jpy|cny|rmb|
            kg|km|cm|mm|ml|kwh|kw|gb|mb|tb|min|hrs?|pcs)  # 44.17EUR, 200km
    )$
""", re.VERBOSE | re.IGNORECASE)

# Below this, two strings are different things rather than one thing
# mistyped. Measured against what an engine actually does to a code: it
# changes a hyphen, drops a leading zero, swaps O for 0, or splits it —
# all of which stay well above.
LIKENESS = 0.6


def find(text):
    """The codes in this text, longest first.

    Longest first so that repairing an address does not leave half of it
    behind when a code inside it matches too.
    """
    text = str(text or "")
    found = []
    for match in _ADDRESS.finditer(text):
        found.append(match.group(0))
    for pattern in (_CODE, _NUMBER, _LAYOUT):
        for match in pattern.finditer(text):
            token = match.group(0).strip()
            # "44.17EUR." at the end of a sentence carries its full stop.
            if not token or _NOT_A_CODE.match(token.rstrip(".,")):
                continue
            # A word with a footnote mark after it - "Hausarrest.[15]" -
            # passed the look-ahead for a digit on the mark's digits, and
            # the word was kept back as a code the engine had "dropped".
            if pattern is _CODE and not any(c.isdigit() for c in token):
                continue
            if any(token in seen for seen in found):
                continue
            found.append(token)
    return sorted(set(found), key=lambda item: (-len(item), item))


def shape(token):
    """A code with its letters and digits flattened.

    What survives an engine's attention is the shape: how many letters,
    how many digits, in what order. Comparing shapes is what tells a
    mistyped copy of this code from an entirely different one.
    """
    out = []
    for ch in str(token or ""):
        if ch.isdigit():
            out.append("9")
        elif ch.isalpha():
            out.append("a")
        else:
            out.append(ch)
    return "".join(out)


def _runs(text, most):
    """Every run of up to `most` words in this text, with its position."""
    words = []
    for match in re.finditer(r"\S+", text):
        words.append((match.start(), match.end()))
    for start in range(len(words)):
        for length in range(1, most + 1):
            if start + length > len(words):
                break
            yield words[start][0], words[start + length - 1][1]


def _closest(token, text):
    """Where in `text` the nearest thing to `token` is, or None."""
    # A code the engine broke in two — DN-4A coming back as "DN 4A" — is
    # two words where the original was one, so the search has to be
    # willing to look at a run of them.
    most = min(4, max(1, len(token.split())) + 2)
    best, where = 0.0, None
    for start, end in _runs(text, most):
        candidate = text[start:end]
        if abs(len(candidate) - len(token)) > max(4, len(token) // 2):
            continue
        # Same kind of thing: both have digits, or neither does, and
        # about as many. An engine that retypes a code keeps its length —
        # it turns a zero into an O, changes a hyphen, splits it in two.
        # Something with two digits where the original had seven is a
        # different thing, and replacing it would be the worse mistake.
        here = sum(1 for ch in token if ch.isdigit())
        there = sum(1 for ch in candidate if ch.isdigit())
        if bool(here) != bool(there) or abs(here - there) > 1:
            continue
        if shape(token) == shape(candidate) and token.lower() != \
                candidate.lower():
            # Same shape, different characters: exactly the case this is
            # for, and worth more than the letter-by-letter score.
            best, where = 1.0, (start, end)
            continue
        score = difflib.SequenceMatcher(None, token.lower(),
                                        candidate.lower()).ratio()
        if score > best:
            best, where = score, (start, end)
    return where if best >= LIKENESS else None


def repair(source, translated):
    """`(text, missing)` — the translation with its codes put back.

    A code already there is left alone, which is the ordinary case and
    costs nothing. A code that came back altered is replaced by the
    original. A code that is not there at all is named in `missing` rather
    than guessed at: putting it back would mean choosing a place for it,
    and a reference number in the wrong sentence is worse than one that is
    visibly absent.
    """
    text = str(translated or "")
    if not text.strip():
        return text, []
    missing = []
    text = _list_marker(source, text)
    text = _times_back(source, text)
    for token in find(source):
        if token in text:
            continue
        if _LAYOUT.fullmatch(token):
            fixed = _layout_back(token, text)
            if fixed is not None:
                text = fixed
                continue
        if not any(ch.isalpha() for ch in token):
            fixed = _number_back(token, text)
            if fixed is not None:
                text = fixed
                continue
        where = _closest(token, text)
        if where is None:
            missing.append(token)
            continue
        start, end = where
        text = text[:start] + token + text[end:]
    text = _currency_back(source, text)
    return text, missing


_CURRENCY = "€$£¥₹₩₽"
_AMOUNT_AFTER = re.compile(r"(\d[\d.,\s\-–]*\d|\d)\s?([%s])" % _CURRENCY)
_AMOUNT_BEFORE = re.compile(r"([%s])\s?(\d[\d.,\-–]*\d|\d)" % _CURRENCY)


_CURRENCY_WORDS = re.compile(
    r"\b(?:euros?|EUR|dollars?|USD|pounds?|GBP|yen|JPY|yuan|CNY|RMB|"
    r"rupees?|INR|won|KRW|rubles?|roubles?|RUB)\b|[円元원]", re.I)


def _currency_back(source, text):
    """A price whose currency sign the engine dropped: "2.500-3000€" came
    back as "2.500-3000", a price in no currency. The sign goes back on
    the same figures, on the side it was written."""
    for found in _AMOUNT_AFTER.finditer(source):
        amount, sign = found.group(1).strip(), found.group(2)
        if amount + sign in text or amount + " " + sign in text:
            continue
        at = text.find(amount)
        if at < 0 or sign in text[max(0, at - 2):at + len(amount) + 3] or \
                _CURRENCY_WORDS.search(text[max(0, at - 12):
                                            at + len(amount) + 12]):
            continue
        end = at + len(amount)
        text = text[:end] + sign + text[end:]
    for found in _AMOUNT_BEFORE.finditer(source):
        sign, amount = found.group(1), found.group(2).strip()
        at = text.find(amount)
        if at < 0 or sign in text[max(0, at - 3):at + len(amount) + 2] or \
                _CURRENCY_WORDS.search(text[max(0, at - 12):
                                            at + len(amount) + 12]):
            continue
        text = text[:at] + sign + text[at:]
    return text


def _layout_back(token, text):
    """Put a layout back where the engine re-punctuated it, or None.

    A layout is its numbers in order and nothing else, so it can be found
    by exactly that: the same digits in the same order with nothing but
    punctuation between them, whatever brackets and commas the engine
    wrapped them in. 2+2+3 came back as (2, 2, 3) — a closeness score
    rightly calls those two different strings, but they are one layout.
    """
    digits = re.findall(r"\d+", token)
    sep = r"\s*[,，+/、・·]\s*"
    pattern = (r"[(（]?\s*" + sep.join(re.escape(d) for d in digits)
               + r"\s*[)）]?")
    match = re.search(r"(?<!\d)" + pattern + r"(?!\d)", text)
    if not match:
        return None
    start, end = match.span()
    before = text[start - 1] if start else ""
    # Written back as a word of its own. "7인승(2, 2, 3)을" with the
    # brackets taken away would otherwise run straight into the word in
    # front: 7인승2+2+3을.
    lead = " " if before and not before.isspace() and before not in "(（" \
        else ""
    return text[:start] + lead + token + text[end:]


def _number_back(token, text):
    """Put back a number the engine spaced out, or None.

    "（010-12345678）" came back in Korean as "(010 - 12345678)로". The
    search in `_closest` compares runs of words, and here the words are
    "헬프데스크(010", "-" and "12345678)로" — the number is glued to the
    Korean on both sides, so no run of words is anything like it and it
    was reported missing while standing in plain sight. A number is its
    digits in order, so it is found by exactly that: the same groups of
    digits, with nothing between them but space and the separators a
    number is written with.
    """
    groups = re.findall(r"\d+", token)
    if not groups:
        return None
    pattern = r"\s*[-–.·/\s]?\s*".join(re.escape(g) for g in groups)
    # A leading + is part of the number and is taken with it, so that it
    # is not written twice.
    lead = r"(?<![\d+])(?:\+\s*)?" if token.lstrip().startswith("+") \
        else r"(?<![\d+])"
    match = re.search(lead + pattern + r"(?!\d)", text)
    if not match:
        return None
    return text[:match.start()] + token + text[match.end():]


_MARKER = re.compile(r"^\s*(\d{1,2})\s*[.．、]")


def _list_marker(source, text):
    """A numbered point keeps its number as a number.

    "1. 造型设计：…" came back as "1, 디자인: …" — the full stop after the
    number turned into a comma, so a numbered list read as a list of
    numbers followed by commas. Where the source begins with a numbered
    marker and the translation begins with the same number and some other
    punctuation, the marker is put back.
    """
    found = _MARKER.match(str(source or ""))
    if not found:
        return text
    number = found.group(1)
    return re.sub(r"^(\s*)" + re.escape(number) + r"\s*[,，、)）]\s*",
                  lambda m: m.group(1) + number + ". ", text, count=1)


# A clock time, and a range of two. See `_times_back`.
_TIME = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])")
_TIME_RANGE = re.compile(r"(?<![\d:])(\d{1,2}:\d{2})\s*([-–~～])\s*"
                         r"(\d{1,2}:\d{2})(?![\d:])")


def _times_back(source, text):
    """A time comes back as a time, not as "20: 00 - 23: 00".

    Times are left out of `find` on purpose — a target language may write
    them another way, and that is its business. What is not another way of
    writing a time is a space after the colon: "20: 00" is the engine
    treating the colon as punctuation in a sentence. So where the source
    has a time, the same digits with space round the colon are closed up;
    and where the source wrote a range tight, 20:00-23:00, the same two
    times with space round the dash are closed up to match.
    """
    source = re.sub(r"(?<=\d)\s*：\s*(?=\d)", ":", str(source or ""))
    times = set(_TIME.findall(source))
    for hours, minutes in times:
        text = re.sub(r"(?<![\d:])(0?%s)\s*[:：]\s+(%s)(?![\d:])"
                      % (re.escape(hours.lstrip("0") or "0"),
                         re.escape(minutes)),
                      r"\1:\2", text)
    for start, dash, end in _TIME_RANGE.findall(source):
        tight = start + dash + end
        if tight not in source:
            continue
        text = re.sub(r"(?<![\d:])(%s)\s*[-–~～]\s*(%s)(?![\d:])"
                      % (re.escape(start), re.escape(end)),
                      lambda m: m.group(1) + dash + m.group(2), text)
    return text


# A date written the Chinese and Japanese way, 2026年9月18日 or 9月18日.
_HAN_DATE = re.compile(r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def korean_dates(source, text):
    """9月18日 in Korean is 9월 18일, not (09-18).

    An engine translating into Korean turned a Chinese month and day into
    a numeric 09-18, which no Korean document writes in running text and
    which reads as a range or a code. Korean has the same month-and-day
    form as Chinese, with 월 and 일 for 月 and 日, so where the source has
    one and the translation has only the numbers, it is written back that
    way. For Korean only: every other target has its own way, and the
    engine's is usually right.
    """
    text = str(text or "")
    for year, month, day in _HAN_DATE.findall(str(source or "")):
        m, d = int(month), int(day)
        said = "%d월 %d일" % (m, d)
        if said in text:
            continue
        numeric = re.compile(
            r"(?<![\d.\-/])(?:(\d{4})\s*[-./]\s*)?0?%d\s*[-./]\s*0?%d"
            r"(?![\d.\-/])" % (m, d))
        found = numeric.search(text)
        if not found:
            continue
        year_said = found.group(1) or year
        written = ("%s년 " % year_said if year_said else "") + said
        text = text[:found.start()] + written + text[found.end():]
    return text


def repair_all(sources, translations):
    """The same, over a list of paragraphs. Returns `(texts, missing)`."""
    out, missing = [], []
    for source, translated in zip(sources, translations):
        fixed, lost = repair(source, translated)
        out.append(fixed)
        missing.extend(lost)
    if len(translations) > len(sources):
        out.extend(translations[len(sources):])
    return out, missing
