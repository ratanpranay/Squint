"""Words the translator must not guess at.

Machine translation is fine at sentences and bad at names. Given 实拍新宝马iX3
a small model will happily invent "Actual Shot New BMW Proposal 3", because it
is translating characters that happen to be a brand. The same goes the other
way: model codes like PHEV, RF8 or ID.AURA come back mangled or "translated".

Two rules fix most of it, and neither needs a bigger model:

* Never translate what is already a name — codes, versions, URLs, numbers.
* Always translate certain terms the same way, from a list you control.

Both are applied by swapping the term for a placeholder before the engine
sees it and swapping the result back afterwards, so they work with whichever
engine happens to answer.
"""
import os
import re

from . import config

FILENAME = "glossary.txt"

# Latin letters and digits stuck together — iX3, RF8, T6, U8L, XC70, PHEV.
# These are names, not words, whatever language surrounds them.
_CODE = re.compile(r"""
    (?:https?://\S+)                 # URLs
  | (?:[\w.+-]+@[\w-]+\.[\w.]+)      # email addresses
  | (?:[A-Za-z]+[.\-]?[A-Za-z]*\d+[A-Za-z0-9.\-]*)   # iX3, ID.AURA, RF8
  | (?:\d+[A-Za-z]{1,4}\b)           # 200km, 4L
""", re.VERBOSE)

# The same, for text in a spaced script: links, addresses, and codes that
# start with a letter. Not "23rd", "25th", "200km" or bare numbers.
_LATIN_CODE = re.compile(r"""
    (?:https?://\S+)
  | (?:[\w.+-]+@[\w-]+\.[\w.]+)
  | (?:\b[A-Za-z]+[.\-]?[A-Za-z]*\d+[A-Za-z0-9.\-]*)
""", re.VERBOSE)

# Two or more capitals in a row, optionally dotted: PHEV, ID.AURA, EV, GT.
_ACRONYM = re.compile(r"\b[A-Z]{2,}(?:\.[A-Z]{2,})*\b")

# Numbers, with whatever separators they carry: phone numbers, times,
# prices, years. A translation model rewrites these as readily as words —
# 400-961-6666 came back as 400-961-666, one digit short, which for a phone
# number is worse than leaving it in Chinese.
_NUMBER = re.compile(r"\d+(?:[.,:/\-]\d+)*")

# Placeholders have to survive a round trip through a translation model.
# Bare digits get rewritten, punctuation gets dropped, and CJK models will
# happily translate a word — an unfamiliar capitalised Latin token is the
# thing they most reliably copy through untouched.
#
# Letters, not digits, for the index: the code pattern above matches
# letters-followed-by-digits, so a numbered placeholder is itself mistaken
# for a model code and masked a second time.
# A date written the way Chinese, Japanese and Korean write one, matched
# as a single thing before the digits inside it are masked separately.
#
# This is the whole of "2026 Year 8 Month 28 Day", seen on a real email.
# 年, 月 and 日 are ordinary words meaning year, month and day, so once the
# numbers around them have been taken out as three separate codes what
# reaches the engine is "ZQXAQ年ZQXBQ月ZQXCQ日" — three placeholders and
# three Chinese words, and there is nothing left in it to suggest a date.
# It translated exactly what it was given.
#
# 号 is the spoken form of 日 and appears in notices; Korean writes 년 월 일.
_CJK_DATE = re.compile(
    r"(?P<y>\d{4})\s*[年년]\s*(?P<m>\d{1,2})\s*[月월]\s*(?P<d>\d{1,2})\s*[日号일]"
    r"|(?P<m2>\d{1,2})\s*[月월]\s*(?P<d2>\d{1,2})\s*[日号일]"
    # A range of months, which a combined issue of anything is written as.
    r"|(?P<yr>\d{4})\s*[年년]\s*(?P<m4>\d{1,2})\s*[-–—~至]\s*(?P<m5>\d{1,2})"
    r"\s*[月월]"
    r"|(?P<y2>\d{4})\s*[年년]\s*(?P<m3>\d{1,2})\s*[月월]")

_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")


def _read_date(match):
    """`(year, month, day)`, any of which may be None."""
    got = match.groupdict()

    def number(*names):
        for name in names:
            if got.get(name):
                return int(got[name])
        return None

    return (number("y", "y2", "yr"), number("m", "m2", "m3", "m4"),
            number("d", "d2"), number("m5"))


def written_date(match, target=None):
    """The same date, written so that no engine has to guess at it.

    English gets a month by name, because that is what the page it is
    going onto reads like. Everything else gets the numeric form in
    year-month-day order, which is unambiguous in every language and is
    the one thing that cannot come back reordered.
    """
    year, month, day, until = _read_date(match)
    if not month or not 1 <= month <= 12:
        return match.group(0)
    if until and not 1 <= until <= 12:
        return match.group(0)
    english = str(target or "").strip().lower().startswith("en")
    if english:
        name = _MONTHS[month - 1]
        if until:
            return "%s–%s %d" % (name, _MONTHS[until - 1], year)
        if day and year:
            return "%d %s %d" % (day, name, year)
        if day:
            return "%d %s" % (day, name)
        return "%s %d" % (name, year)
    if until:
        return "%04d-%02d–%04d-%02d" % (year, month, year, until)
    if day and year:
        return "%04d-%02d-%02d" % (year, month, day)
    if day:
        return "%02d-%02d" % (month, day)
    return "%04d-%02d" % (year, month)


_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_SLOT_FINDER = re.compile(r"ZQX\s*([A-Z]{1,2})\s*Q", re.IGNORECASE)


def _slot(index):
    if index < len(_ALPHABET):
        return "ZQX%sQ" % _ALPHABET[index]
    first, second = divmod(index, len(_ALPHABET))
    return "ZQX%s%sQ" % (_ALPHABET[first - 1], _ALPHABET[second])


def _slot_index(letters):
    letters = letters.upper()
    if len(letters) == 1:
        return _ALPHABET.index(letters)
    return (_ALPHABET.index(letters[0]) + 1) * len(_ALPHABET) \
        + _ALPHABET.index(letters[1])

DEFAULT_GLOSSARY = """\
# Squint glossary
#
# One rule per line:      term = replacement
# To leave a term alone:  term
#
# Terms are matched in the text before it is translated, so they work with
# every engine. Lines starting with # are ignored.

宝马 = BMW
奔驰 = Mercedes-Benz
大众 = Volkswagen
比亚迪 = BYD
实拍 = real photos of
试驾 = test drive
预售 = pre-sale
预订 = pre-order
续航 = range
"""


def path():
    return os.path.join(config.app_dir(), FILENAME)


def user_path():
    """The glossary an update does not touch.

    The shipped one sits in the app folder, and the app folder is exactly
    what an update replaces — `updater.REPLACE_FILES` lists glossary.txt by
    name. So every rule anybody added to it was thrown away the next time
    they updated, silently, and the terms they had fixed started coming
    back wrong again.

    This one lives with the settings and the log, which an update is not
    allowed near. Rules here are read first, so a rule of your own beats
    the shipped rule for the same term.
    """
    return os.path.join(config.data_dir(), FILENAME)


USER_HEADER = """\
# Your own glossary. Squint reads this as well as the one that ships with
# the app, and nothing here is ever changed by an update.
#
# One rule per line:      term = replacement
# To leave a term alone:  term
# For one language only:  zh: term = replacement
#
# A rule here wins over the shipped rule for the same term.
"""


def ensure_file():
    """Create both glossaries the first time they are needed."""
    target = path()
    if not os.path.isfile(target):
        try:
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(DEFAULT_GLOSSARY)
        except Exception:
            return ""
    mine = user_path()
    if not os.path.isfile(mine):
        try:
            os.makedirs(os.path.dirname(mine), exist_ok=True)
            with open(mine, "w", encoding="utf-8") as handle:
                handle.write(USER_HEADER)
        except Exception:
            pass
    return target


# A rule may name the language it belongs to: "de: Menge = Quantity".
# Without one it applies to every language, which is right for a brand and
# wrong for a word: "Art" is German for "type" and English for art, and a
# rule that rewrites it everywhere damages one language to help another.
_TAGGED = re.compile(r"^([A-Za-z]{2}(?:-[A-Za-z]{2,4})?)\s*:\s*(.+)$")


def _read(where):
    """The rules in one file, in the order they are written."""
    entries = []
    try:
        with open(where, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                language = None
                tagged = _TAGGED.match(line)
                if tagged:
                    language, line = tagged.group(1).lower(), tagged.group(2)
                if "=" in line:
                    term, replacement = line.split("=", 1)
                    term, replacement = term.strip(), replacement.strip()
                else:
                    term, replacement = line.strip(), None
                if term:
                    entries.append((term, replacement or None, language))
    except Exception:
        return []
    return entries


def load():
    """Returns [(term, replacement_or_None, language_or_None)].

    Both glossaries: the one that ships with the app, and the user's own,
    which an update never touches. The user's are read first and a stable
    sort keeps them there, so where both name the same term theirs is the
    one that applies — `protect` replaces on the first match and the term
    is gone from the text by the time the second rule is tried.

    Longest term first: 新宝马 has to be tried before 宝马, or the longer
    term is never seen.
    """
    ensure_file()
    entries = _read(user_path()) + _read(path())
    entries.sort(key=lambda item: len(item[0]), reverse=True)
    return entries


def protect(text, entries=None, auto_codes=True, source=None, target=None):
    """Swap protected terms for placeholders.

    Returns (masked text, {placeholder: final text}).

    `source` is the language the text is in, when it is known. Rules that
    name a language are applied only when it matches; a rule that names
    none applies always. Where the language is not known — the reader was
    left on Detect and nothing said otherwise — the language-specific rules
    are skipped, so not knowing costs a term left to the engine rather than
    an English word rewritten by a German rule.
    """
    entries = load() if entries is None else entries
    here = str(source or "").strip().lower().split("-")[0]
    if here in ("", "auto", "detect"):
        here = None
    mapping = {}

    def take_slot(value):
        slot = _slot(len(mapping))
        mapping[slot] = value
        return slot

    # Measured on the input, before anything is masked: the placeholders are
    # themselves all capitals, so counting after masking makes every text
    # look like a shouted headline and switches this off exactly when it is
    # needed.
    letters = [c for c in text if c.isalpha() and c.isascii()]
    upper = sum(1 for c in letters if c.isupper())
    mostly_caps = bool(letters) and upper > len(letters) * 0.6

    # Codes first, on the untouched text, then glossary terms. The other
    # order lets a glossary replacement be re-masked as if it were a code.
    def mask(match):
        token = match.group(0)
        # A placeholder is itself a run of capitals, so without this the
        # acronym pass masks the code pass's placeholders and the result
        # needs unwrapping twice — which restore does not do.
        #
        # fullmatch was not enough, and the gap it left reached the screen.
        # "0.24Cd" is masked in two pieces — ZQXAQ for the code, ZQXBQ for
        # the number — which leaves the literal text "ZQXBQ.ZQXAQ" sitting
        # in the sentence. That is two placeholders joined by a dot, so it
        # is not *a* placeholder and fullmatch says no; it is however a run
        # of capitals with a dot in it, which is precisely what the acronym
        # pattern is looking for. So the acronym pass masked the pair as
        # one thing, and restore put back a value that was itself two
        # placeholders and stopped there. On screen: "connect the
        # ZQXBQ.ZQXAQ aerodynamic goals with the exterior design."
        #
        # Any token containing a placeholder is already spoken for.
        if _SLOT_FINDER.search(token):
            return token
        return take_slot(token)

    if auto_codes:
        # Dates first, before the numbers inside them are taken out one at
        # a time. Order is the whole fix: after `_NUMBER` has run there is
        # no date left to recognise, only three separate numbers with the
        # words for year, month and day between them.
        text = _CJK_DATE.sub(
            lambda found: take_slot(written_date(found, target)), text)
        if any(_is_cjk(ch) for ch in text):
            text = _CODE.sub(mask, text)
            text = _NUMBER.sub(mask, text)
        else:
            # Text in a spaced script — English, German, Russian — keeps
            # its numbers. Masking them was for Chinese, Japanese and
            # Korean, where a model rewrote a phone number and read a
            # model code as a word. Here it did harm: "on 23rd Sep" went
            # to the engine as "on ZQXAQ Sep", came back as "am 1.
            # September (23rd)", and "44.17EUR" could not become
            # "44,17 EUR". Every engine translates "25th June" properly
            # and writes the number the target language's way. Links,
            # addresses and letter-first codes (iX3, RF8) are still kept.
            text = _LATIN_CODE.sub(mask, text)
        # Acronyms and all-caps names: PHEV, ID.AURA, EV. Skipped when the
        # text is mostly capitals, because then these are ordinary words in
        # a shouted headline and protecting them would leave it untranslated.
        if not mostly_caps:
            text = _ACRONYM.sub(mask, text)

    for entry in entries:
        term, replacement = entry[0], entry[1]
        language = entry[2] if len(entry) > 2 else None
        if language and (here is None or language.split("-")[0] != here):
            continue
        if not term:
            continue
        if term in text:
            text = text.replace(term, take_slot(replacement or term))
            continue
        # Spaced out. A recogniser hands back one box per glyph and joins
        # them itself, so a marque can arrive as "享 界" — which reads the
        # same, draws the same, and does not match. The readers are being
        # made to agree about this (see `ocr._clean_lines`), but a rule
        # somebody wrote down should not stop working because one of five
        # readers spaces things differently. So a term that did not match
        # is tried again allowing gaps between its characters.
        loose = _spaced(term)
        if loose is not None and loose.search(text):
            text = loose.sub(lambda _m: take_slot(replacement or term), text)
    return text, mapping


def _is_cjk(ch):
    code = ord(ch)
    return (0x3040 <= code <= 0x30FF or 0x3400 <= code <= 0x4DBF
            or 0x4E00 <= code <= 0x9FFF or 0xF900 <= code <= 0xFAFF
            or 0xAC00 <= code <= 0xD7AF)


_spaced_cache = {}


def _spaced(term):
    """The term, allowing whitespace between its characters — or None.

    Only for terms written in characters that are not spaced when written
    properly. Doing this to a Latin term would let "BMW" match "B M W",
    and worse, "Art" match across the end of one word and the start of the
    next.
    """
    if term in _spaced_cache:
        return _spaced_cache[term]
    pattern = None
    if len(term) > 1 and all(_is_cjk(ch) for ch in term):
        pattern = re.compile(r"\s*".join(re.escape(ch) for ch in term))
    _spaced_cache[term] = pattern
    return pattern


def restore(text, mapping, _depth=0):
    """Put the real terms back where the placeholders ended up.

    Runs again on its own output while anything is still masked. The
    masking pass is supposed to make nesting impossible and now does, but
    a placeholder reaching the user is the worst failure this module has —
    it is unreadable, it is untranslated, and it looks like a bug in the
    app rather than in one sentence. Unwrapping until it is done costs a
    pass over a short string and removes a whole category of ways to be
    wrong. The depth limit is there because a mapping that somehow refers
    to itself must terminate rather than spin.
    """
    if not mapping:
        return text

    original = text

    def put_back(match):
        try:
            slot = _slot(_slot_index(match.group(1)))
        except (ValueError, IndexError):
            return ""
        value = mapping.get(slot)
        if value is None:
            # A placeholder with nothing behind it was never made by the
            # masking pass — the engine invented it. A language model given
            # a paragraph full of ZQXAQ, ZQXBQ, ZQXCQ will occasionally
            # produce a ZQXQQ of its own, and there is no value to put
            # there because nothing was ever taken from there.
            #
            # It used to be left where it stood, which is how "ZQXQQ kwh"
            # reached a bill in place of "3.344 kWh". Leaving it is the
            # worst of the three options: the reader sees a machine's
            # internals and cannot tell what was lost. Removing it leaves a
            # gap in a sentence, which reads as a translation that dropped
            # a word — recoverable, and honest.
            return ""
        # Space is added from what is actually next to the placeholder.
        # Deciding it afterwards with a pattern cannot tell "BMWiX3" (two
        # protected terms that belong together) from a word run together
        # with its neighbour, and splits the first into "BM WiX3".
        start, end = match.span()
        before = original[start - 1] if start else ""
        after = original[end] if end < len(original) else ""
        prefix = " " if before.isalnum() and value[:1].isalnum() else ""
        suffix = " " if after.isalnum() and value[-1:].isalnum() else ""
        return prefix + value + suffix

    # Loose match: an engine may change the case of the placeholder or put a
    # space inside it while still keeping the letters.
    text = _SLOT_FINDER.sub(put_back, text)
    text = re.sub(r"[ \t]{2,}", " ", text)

    # If a value was itself masked, one pass leaves a placeholder in the
    # finished sentence. The masking pass no longer allows that, and this
    # is here so that a future one cannot bring it back quietly.
    if _depth < 3 and _SLOT_FINDER.search(text):
        return restore(text, mapping, _depth + 1)

    # Anything the engine deleted outright is put back rather than lost.
    # Only at the top: at an inner level a value can be legitimately
    # absent because its placeholder has not been unwrapped yet, and
    # appending it there is how "24Cd 0" ended up on the end of a
    # paragraph about aerodynamics.
    if _depth == 0:
        for value in mapping.values():
            if value not in text:
                text = text.rstrip() + " " + value
    return text.strip()
