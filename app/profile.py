"""One choice instead of two, and what each one resolves to.

Settings used to ask twice: which engine reads, and which engine
translates. Five options each, so twenty-five combinations, of which about
four are things anybody wants. That is not a choice, it is a puzzle — and
the person answering it has to already know that Windows can read but not
translate, that DeepL can translate but not read, and that Gemini does
both slowly. Nobody thinks "Windows reads and DeepL translates". They
think "use DeepL".

So there is one control now, and it names an intention rather than a
mechanism. What it resolves to is printed underneath it, because that is
the information the second dropdown used to carry and it should not be
lost — it is also the answer to the question that started this: "I chose
this computer, why is Google answering".

Two rules run through everything here.

The first is that On this computer means it. Every other choice may fall
back to every other engine, because a preference is not worth a dead app —
that rule was written when Gemini's quota ran out and the only pinned
backend answered 429 to everything. But falling back from local to a web
service is a different act. Somebody who picked this option may have
picked it so that nothing leaves the machine, and quietly posting their
text to a free endpoint is not a smaller failure than not translating. It
is a worse one, and it is invisible.

The second is that Automatic decides per job rather than once. Drawing an
overlay is twenty short lines with somebody watching the screen, and the
right engine is the quickest that is any good. A paragraph on the result
card is one request that will be read properly, and the right engine is
the best one there is. Pinning either choice for the whole session gets
one of those two wrong every time.
"""
from . import config

KEY = "engine_profile"
CLOUD_READ_KEY = "always_cloud_read"

AUTO, LOCAL, GEMINI, GOOGLE, DEEPL, GROQ = (
    "auto", "local", "gemini", "google", "deepl", "groq")

# Short enough to fit the control whole. What each one costs you goes in
# the line underneath, which has room for a sentence; a name cut off at
# "Automatic — best available for each…" tells you less than "Automatic"
# would have.
PROFILES = (
    (AUTO, "Automatic — best for each job"),
    (LOCAL, "On this computer only"),
    (DEEPL, "DeepL — fast"),
    (GEMINI, "Gemini — best, slower"),
    (GOOGLE, "Google Translate — fast"),
    (GROQ, "Groq — fast, free key"),
)

# The sentence under the dropdown, before the resolved line.
ABOUT = {
    AUTO: "Translates on this computer when the offline engine is set up; "
          "Groq or Gemini step in when it is slow or cannot answer.",
    LOCAL: "Nothing leaves this computer, and nothing is sent anywhere if "
           "the offline engine cannot do it. The weakest translations of "
           "them all.",
    GEMINI: "The best translations — it understands context and brand "
            "names. Also the slowest, by seconds, because it is reasoning "
            "about the sentence rather than looking it up.",
    GOOGLE: "Fast and good, and it ends the rate-limiting that free "
            "endpoints hit on a shared office connection.",
    DEEPL: "Fast and good, strongest on European languages.",
    GROQ: "A language model like Gemini, on a second free key with no "
          "card, and quick. It translates; reading the screen stays with "
          "this computer or Gemini.",
}

# What each one needs before it can be chosen. Offering a choice that
# cannot work and then quietly doing something else is the mistake the
# language pack list made for three releases.
NEEDS = {
    GEMINI: ("gemini_api_key", "needs the free Gemini key"),
    GOOGLE: ("google_api_key", "needs a Google key"),
    DEEPL: ("deepl_api_key", "needs a DeepL key"),
    GROQ: ("groq_api_key", "needs the free Groq key"),
}

# Jobs. Not engine names — the shape of the request.
SPEED = "speed"          # an overlay: many short lines, somebody waiting
QUALITY = "quality"      # a card: one passage, about to be read properly


def _has(setting):
    try:
        return bool(str(config.CONFIG.get(setting, "") or "").strip())
    except Exception:
        return False


def usable(key):
    """Whether this profile can do anything on this machine."""
    if key == LOCAL:
        try:
            from . import offline_model
            if offline_model.ready():
                return True
        except Exception:
            pass
        try:
            from . import local_engine
            return bool(local_engine.available())
        except Exception:
            return False
    need = NEEDS.get(key)
    return True if need is None else _has(need[0])


def why_not(key):
    """The short reason a profile is greyed, or ""."""
    if key == LOCAL and not usable(LOCAL):
        return "needs the offline engine"
    need = NEEDS.get(key)
    if need and not _has(need[0]):
        return need[1]
    return ""


def current():
    """The chosen profile, exactly as chosen.

    Availability is deliberately not consulted here, and On this computer
    is why. If the offline engine is missing, quietly resolving to
    Automatic would send the text to a web service — which is the precise
    thing that choice exists to prevent, done silently, to the person who
    asked for it least. Refusing to translate is the correct outcome and
    the settings panel says so in words.

    A keyed profile whose key has since been deleted is a different case
    and needs no special handling: the translator tries it, it cannot
    answer, and the ordinary fallback takes over — all of it within the
    cloud the user had already accepted.
    """
    value = str(config.CONFIG.get(KEY, "") or "").strip()
    if value in dict(PROFILES):
        return value
    return _migrated()


def set_profile(key):
    if key in dict(PROFILES):
        config.CONFIG.set(KEY, key)


def cloud_reading_forced():
    """The tick under the dropdown.

    "Local reading looks wrong" is a guess, and it has to be: Windows OCR
    pointed at a language it has no pack for does not fail, it returns
    plausible Latin junk. The heuristic that spots that is good and is not
    perfect, and somebody who knows their machine reads Chinese badly
    should be able to stop arguing with it.
    """
    return bool(config.CONFIG.get(CLOUD_READ_KEY, False))


def _migrated():
    """The nearest profile to whatever the two old dropdowns said.

    Nobody's setup changes silently on update. The translating choice
    decides, because that is the one people actually set; the reading
    choice only survives as the cloud-reading tick.
    """
    engine = str(config.CONFIG.get("engine", "auto") or "auto")
    reader = str(config.CONFIG.get("ocr_engine", "") or "")
    if engine == "offline" or reader == "local":
        return LOCAL
    # The switch that predates the reading dropdown. Somebody who turned
    # it off said their screen was not to be sent to Google, and there is
    # no half of the new control that means only that — so it maps to the
    # profile that keeps the promise. It may well break their translating,
    # and that is the right way round: the panel says exactly why, in
    # words, one click from fixed. Quietly resuming the uploads they had
    # switched off would say nothing at all.
    if not reader and config.CONFIG.get("use_cloud_vision", True) is False:
        return LOCAL
    if engine == "gemini" or reader == "gemini":
        return GEMINI
    if engine == "google-api-key":
        return GOOGLE
    if engine == "deepl-api-key":
        return DEEPL
    if engine == "groq":
        return GROQ
    return AUTO


# -- what it means for reading -----------------------------------------

def reading():
    """One of ocr's own choices: auto, local, cloud or gemini."""
    from . import ocr
    key = current()
    if key == LOCAL:
        return ocr.OCR_LOCAL
    if not cloud_reading_forced():
        # Read here and ask the cloud only when the reading looks wrong.
        # It is free, it is instant, and on a machine with the right
        # language pack it is as good as anything — spending a Gemini
        # request on text Windows can already read is the single easiest
        # way to exhaust a free allowance.
        return ocr.OCR_AUTO
    if key == GOOGLE and _has("google_api_key"):
        return ocr.OCR_CLOUD
    if _has("gemini_api_key"):
        return ocr.OCR_GEMINI
    if _has("google_api_key"):
        return ocr.OCR_CLOUD
    return ocr.OCR_AUTO


# -- what it means for translating -------------------------------------

# The fast ones first, then the good-but-slow one. Gemini is last here on
# purpose: it is reasoning about the sentence rather than looking it up,
# which is exactly why it is both the best and the slowest.
_FAST = ("google-api-key", "deepl-api-key", "groq", "offline", "gtx",
         "clients5", "google-www", "hymt", "gemini")
_GOOD = ("gemini", "deepl-api-key", "google-api-key", "groq", "hymt",
         "offline", "gtx", "clients5", "google-www")

_PINNED = {GEMINI: "gemini", GOOGLE: "google-api-key",
           DEEPL: "deepl-api-key", GROQ: "groq"}


def translating(job=QUALITY):
    """(ordered backend names, allow_fallback).

    An empty list means "no preference, use the standard order".
    """
    key = current()
    if key == LOCAL:
        # The whole point of the option. Nothing after it.
        return ["hymt", "offline"], False
    if key in _PINNED:
        return [_PINNED[key]], True
    order = list(_FAST if job == SPEED else _GOOD)
    # With a Gemini key, Gemini leads for a snip as well. It is raced
    # against Google with a short head start (translator._race_gemini), so
    # leading costs a snip at most that head start - and Google's answer
    # is already on its way if Gemini is slow or out of allowance.
    if job == SPEED and _has_gemini_key():
        order = ["gemini"] + [name for name in order if name != "gemini"]
    # Automatic: Hy-MT2 on this computer leads whenever it is set up, key
    # or no key - the same engine for every page, which is what keeps one
    # page's translation like the next. Groq, then Gemini, stand behind it:
    # when this computer is slow on a page they are asked as well and the
    # first whole answer is used (translator._hymt_with_help), and they
    # answer when it cannot. A Google key, if someone has one, comes after.
    if key == AUTO and not _hymt_writes_target():
        # A language the offline model does not write well: it is not
        # asked at all (see offline_model.WRITES) - the online engines
        # translate, keyless ones included.
        return [name for name in order if name != "hymt"], True
    if key == AUTO and _hymt_ready():
        helpers = ["groq", "gemini"]
        order = ["hymt"] + helpers + [name for name in order
                                      if name not in helpers + ["hymt"]]
    return order, True


def _hymt_writes_target():
    try:
        from . import config, offline_model
        return offline_model.writes(config.CONFIG.get("target_lang", "en"))
    except Exception:
        return True


def _has_any_key():
    try:
        from . import translator
        return any(translator._api_key(name)
                   for name in translator.KEY_SETTINGS.values())
    except Exception:
        return False


def _hymt_ready():
    try:
        from . import offline_model
        return offline_model.ready()
    except Exception:
        return False


def _has_gemini_key():
    try:
        from . import translator
        return bool(translator._api_key("gemini_api_key"))
    except Exception:
        return False


def summary():
    """"Reads with Windows (de, en). Translates with Gemini." — now.

    The line under the dropdown, and the reason collapsing two controls
    into one is safe. The second control is gone; what it used to show is
    not.
    """
    from . import ocr
    reads = _reading_words()
    order, _fallback = translating()
    writes = _engine_word(order[0] if order else "")
    return "Reads with %s. Translates with %s." % (reads, writes)


_ENGINE_WORDS = {
    "gemini": "Gemini", "offline": "the offline engine",
    "hymt": "Hy-MT2 on this computer",
    "google-api-key": "Google", "deepl-api-key": "DeepL", "groq": "Groq",
    "gtx": "Google (free)", "clients5": "Google (free)",
    "google-www": "Google (free)",
}


def _engine_word(name):
    if not name:
        return "whatever answers first"
    return _ENGINE_WORDS.get(name, name)


def _reading_words():
    from . import ocr
    choice = reading()
    if choice == ocr.OCR_GEMINI:
        return "Gemini"
    if choice == ocr.OCR_CLOUD:
        return "Google"
    try:
        here = ocr.local_engine_name()
    except Exception:
        here = "this computer"
    try:
        tags = ocr.readable_languages()
    except Exception:
        tags = []
    if tags:
        return "%s (%s)" % (here, ", ".join(tags[:6]))
    return here
