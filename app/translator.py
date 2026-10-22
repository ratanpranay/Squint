"""Translation with no API key, and no single point of failure.

The obvious approach — one library, one endpoint — is what produced this:

    'Guten Morgen' -> 'Error 500 (Server Error)!!1500.That's an'

Google's public translate hosts rate-limit and return HTML error pages that
arrive as a perfectly ordinary 200-with-a-string. Code that only asks "did I
get a string back?" reports success and hands the user garbage, which is worse
than an error, because nothing downstream can tell it went wrong.

So: several independent backends, each result *validated* before it is
accepted, and the one that answered remembered so the next call goes straight
to it. Only if every backend fails does this raise.
"""
import json
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import http_pool

try:
    from deep_translator import GoogleTranslator
except Exception:  # pragma: no cover
    GoogleTranslator = None

MAX_CHUNK = 4200          # Google's endpoint rejects much beyond ~5k chars
# Five seconds, not eight. On a rate-limited network three Google hosts
# refuse in turn before a working service is reached, and every second of
# each timeout is paid by the person waiting.
TIMEOUT = 5
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

_cache = {}
_cache_lock = threading.Lock()
_CACHE_LIMIT = 400

_preferred = None         # name of the backend that last worked

# A backend that just failed is rested for a while instead of being asked
# again for every following chunk. Translating a whole page splits it into
# many pieces, and without this a service that is blocked or slow was
# retried on each one — with a 20-second timeout that turns a page into
# minutes of apparently nothing happening.
_cooldown = {}            # backend name -> (resting until, why)
COOLDOWN = 60.0
# "You exceeded your current quota" is not a hiccup — a free Gemini key that
# has run out stays out for minutes or until the next day. Asking again a
# minute later just spends another timeout, so a rate-limited service is
# rested for longer.
COOLDOWN_RATE_LIMITED = 600.0
_preferred_lock = threading.Lock()


class TranslationError(RuntimeError):
    pass


class Cancelled(TranslationError):
    """The snip or hold this translation was for has been cancelled."""


def set_stop(event):
    """The stop for work done on this thread from now on: a snip's thread
    sets it, and once it is set, translating stops where it can (between
    requests, and between the offline engine's sentences). None clears it."""
    _job.stop = event


def _stop():
    return getattr(_job, "stop", None)


def _check_stop():
    stop = _stop()
    if stop is not None and stop.is_set():
        raise Cancelled("cancelled")


def set_background(flag):
    """Work on this thread is preparation nobody asked for yet (a page
    read and translated ahead): this computer's engine only - never a
    key's allowance, never the network."""
    _job.background = bool(flag)


def _background():
    return bool(getattr(_job, "background", False))


class _Either:
    """An event that also counts as set once `stop` is."""

    def __init__(self, stop=None):
        self.own = threading.Event()
        self.stop = stop

    def set(self):
        self.own.set()

    def is_set(self):
        return self.own.is_set() or bool(self.stop is not None
                                          and self.stop.is_set())


# The shape of the request, re-exported so callers do not have to reach
# into profile for a string.
SPEED, QUALITY = "speed", "quality"

# Which job the current thread is doing. A thread-local rather than an
# argument threaded through six functions: the backends all have the
# signature (text, source, target) and widening it to carry a hint would
# touch every one of them, including the eight that have no use for it.
_job = threading.local()


def current_job():
    return getattr(_job, "value", None)


# Engines where a request is a real cost rather than a lookup. Gemini's
# free allowance is small and per day; Google's is half a million
# characters a month.
EXPENSIVE = ("gemini", "groq")


# What "On this computer" says when it cannot do the job. It refuses
# rather than going online, so it has to say why and what to do.
OFFLINE_ONLY = (
    "Engine is set to On this computer only, and the offline translation "
    "engine is not installed — so there is nothing here that can "
    "translate, and Squint will not send your text to a web service after "
    "you have said not to.\n\n"
    "This is not the same thing as a Windows language pack. A pack lets "
    "this computer READ a language on screen; the offline engine is what "
    "TRANSLATES it, and it is a separate download under Offline "
    "translation in Settings.\n\n"
    "Install it, or choose another engine.")


# -- validation --------------------------------------------------------
# Fingerprints of the error pages that come back dressed as translations.
_BROKEN = (
    "error 500", "error 502", "error 503", "error 429",
    "that's an error", "that’s an error",
    "<html", "<!doctype", "server error", "rate limit",
    "our systems have detected unusual traffic",
)


def _describe(exc):
    """Turn an exception into something diagnosable.

    'HTTPError' alone cannot be acted on. 429 means rate-limited and worth
    retrying; 403 means blocked and never will be. The status code is the
    whole difference, so never throw it away.
    """
    code = getattr(exc, "code", None)
    if code:
        # And what the service said, when it said something. "HTTP 400"
        # from a key that passes the Settings test is a question; Google's
        # own sentence is usually the answer.
        said = ""
        try:
            body = exc.read()
            if isinstance(body, bytes):
                body = body.decode("utf-8", "replace")
            try:
                said = json.loads(body).get("error", {}).get("message", "")
            except Exception:
                said = ""
        except Exception:
            said = ""
        said = " ".join(str(said or "").split())[:100]
        return "HTTP %s%s" % (code, (" (%s)" % said) if said else "")
    reason = getattr(exc, "reason", None)
    if reason is not None:
        return "%s (%s)" % (type(exc).__name__, str(reason)[:48])
    # RuntimeError here is always a message this app wrote on purpose —
    # usually the service's own words. Truncating it to a phrase throws away
    # the only part that says what to do, so give it room.
    if isinstance(exc, RuntimeError):
        return str(exc)[:120]
    return "%s: %s" % (type(exc).__name__, str(exc)[:48])


# Scripts are far more reliable than statistical language detection for this
# job: a page of Chinese is unambiguously Chinese from its codepoints, while
# langdetect looks at a headline full of model numbers ("iX3", "ID.AURA T6",
# "PHEV") and can return nothing at all.
_SCRIPTS = (
    ("ko", ((0xAC00, 0xD7AF), (0x1100, 0x11FF))),          # Hangul
    ("ja", ((0x3040, 0x309F), (0x30A0, 0x30FF))),          # kana (before CJK)
    ("zh", ((0x4E00, 0x9FFF), (0x3400, 0x4DBF))),          # Han
    ("ru", ((0x0400, 0x04FF),)),                           # Cyrillic
    ("ar", ((0x0600, 0x06FF), (0x0750, 0x077F))),          # Arabic
    ("hi", ((0x0900, 0x097F),)),                           # Devanagari
    ("he", ((0x0590, 0x05FF),)),                           # Hebrew
    ("th", ((0x0E00, 0x0E7F),)),                           # Thai
    ("el", ((0x0370, 0x03FF),)),                           # Greek
)


def script_of(text):
    """Dominant non-Latin script as a language code, or '' for Latin text."""
    counts = {}
    for char in text:
        code = ord(char)
        for name, ranges in _SCRIPTS:
            if any(low <= code <= high for low, high in ranges):
                counts[name] = counts.get(name, 0) + 1
                break
    if not counts:
        return ""
    letters = sum(1 for c in text if c.isalpha()) or len(text)
    name = max(counts, key=counts.get)
    # Japanese is written with Han characters too, so any kana wins outright.
    if "ja" in counts:
        name = "ja"
    return name if counts[name] >= max(2, letters * 0.15) else ""


def guess_source(text):
    """Best source-language guess. Script first, statistics second."""
    return script_of(text) or detect_language(text) or ""


def looks_untranslated(text, result, target):
    """True if the 'translation' is really just the input handed back.

    This is how the overlay ended up drawing Chinese over Chinese: a backend
    decided the source language was already the target and returned the text
    unchanged, which passes every other check — it is not empty and contains
    no error markers. Only comparing it against the input catches it.
    """
    if result.strip() != text.strip():
        return False
    source_script = script_of(text)
    target_script = script_of(target) or ""
    # Identical output is only suspicious when the input is in a script the
    # target language does not use — "OK" translating to "OK" is fine.
    return bool(source_script) and source_script != (target_script or target)


def _is_broken(result, source_text):
    """True if this 'translation' is really an error page or empty."""
    if not result or not result.strip():
        return True
    low = result.strip().lower()
    for marker in _BROKEN:
        if marker in low:
            return True
    # A reply many times longer than the input is a page, not a translation.
    if len(result) > max(400, len(source_text) * 6):
        return True
    return False


_ssl_ctx = None
_ssl_ctx_lock = threading.Lock()


def ssl_context():
    """A TLS context that can actually verify a certificate.

    The Python installed from python.org does not use the macOS keychain and
    ships with no CA certificates of its own — it expects you to run
    "Install Certificates.command" by hand, which nobody does. Every HTTPS
    request then dies with:

        CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate

    which looks exactly like the service being down. certifi carries Mozilla's
    CA bundle and arrives as a dependency of requests, so pointing at it fixes
    this without touching the user's system or weakening verification.
    """
    global _ssl_ctx
    with _ssl_ctx_lock:
        if _ssl_ctx is not None:
            return _ssl_ctx
        context = None
        try:
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
            # And the computer's own trusted roots as well. On Windows a
            # root that is missing from certifi's list but trusted by the
            # system - an antivirus or company network that inspects
            # secure connections signs them with its own - failed every
            # connection; so did the reverse, a public root this Windows
            # had not been sent yet, with the system's list alone.
            try:
                context.load_default_certs()
            except Exception:
                pass
        except Exception:
            try:
                context = ssl.create_default_context()
            except Exception:
                context = None
        _ssl_ctx = context
        return _ssl_ctx


_keychain_ctx = None
_keychain_tried = False


def keychain_context():
    """A second context trusting the roots in the macOS keychain.

    certifi carries the public CAs, which is right for a normal connection and
    wrong on a managed Mac: a company proxy that inspects traffic re-signs it
    with a private root that exists only in that machine's keychain. certifi
    has never heard of it, so verification fails on every site.

    Exporting the keychain roots covers that case while still *verifying* —
    the alternative people reach for is turning verification off, which hands
    the connection to anyone on the network.

    Returns None if the export is unavailable; callers keep their first error.
    """
    global _keychain_ctx, _keychain_tried
    with _ssl_ctx_lock:
        if _keychain_tried:
            return _keychain_ctx
        _keychain_tried = True
        import subprocess
        import sys
        if sys.platform != "darwin":
            return None
        pem = []
        for store in ("/System/Library/Keychains/SystemRootCertificates.keychain",
                      "/Library/Keychains/System.keychain"):
            try:
                result = subprocess.run(
                    ["security", "find-certificate", "-a", "-p", store],
                    capture_output=True, timeout=30)
                if result.returncode == 0 and result.stdout:
                    pem.append(result.stdout.decode("utf-8", "replace"))
            except Exception:
                continue
        blob = "\n".join(pem)
        if "BEGIN CERTIFICATE" not in blob:
            return None
        try:
            context = ssl.create_default_context()
            context.load_verify_locations(cadata=blob)
            _keychain_ctx = context
        except Exception:
            _keychain_ctx = None
        return _keychain_ctx


def _fetch(url, data=None):
    """One request, over a connection kept open for the next one.

    The connection is the point. Opening one costs a lookup, a handshake
    and a second handshake for the encryption — three or four trips to a
    server that is usually on another continent, all of it before the
    sentence has been sent. Every translation used to pay that. See
    `http_pool`, which also stands aside for anyone behind a proxy.
    """
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if data is not None:
        data = data.encode("utf-8")
        headers["Content-Type"] = \
            "application/x-www-form-urlencoded;charset=utf-8"
    try:
        raw = http_pool.fetch(url, data=data, headers=headers,
                              timeout=TIMEOUT, context=ssl_context())
    except urllib.error.URLError as exc:
        # Only a certificate problem is worth a second attempt; a 500 or a
        # timeout would just cost another eight seconds.
        if not isinstance(getattr(exc, "reason", None),
                          ssl.SSLCertVerificationError):
            raise
        fallback = keychain_context()
        if fallback is None:
            raise
        raw = http_pool.fetch(url, data=data, headers=headers,
                              timeout=TIMEOUT, context=fallback)
    return raw.decode("utf-8", "replace")


#: The host the default engine talks to. Worth naming for one reason:
#: so the connection to it can be opened before anybody is waiting on it.
DEFAULT_HOST = "translate.googleapis.com"


def warm_connection(host=None, timeout=6):
    """Open the line to the translation service, so the first real
    translation does not have to.

    `http_pool` holds a connection between requests, which means the
    second translation onwards skips the address lookup, the connection
    and the encryption handshake — three or four trips to a server that
    is usually on another continent. The first one pays for all of it,
    and the first one is the one somebody is sitting there waiting for.

    So the app makes a throwaway request at startup and leaves the
    connection in the pool. What comes back is discarded; the point is
    what is left behind. It asks for a single character, because the
    smallest possible request is the cheapest way to finish a handshake.

    Never raises. There is no network at startup often enough — a laptop
    opened before the wifi is up — that a failure here has to be ordinary.
    """
    host = host or DEFAULT_HOST
    try:
        url = ("https://%s/translate_a/single?client=gtx&sl=en&tl=en"
               "&dt=t&q=a" % host)
        http_pool.fetch(url, timeout=timeout, context=ssl_context())
        return True
    except Exception:
        return False


# -- backends ----------------------------------------------------------
# Each takes (text, source, target) and returns a string, or raises.

def _offline(text, source, target):
    """The local model. First choice when it can do this pair.

    No account, no key, no per-character cost, no rate limit, nothing sent to
    anyone else, and it works with the network down. The only reasons not to
    prefer it are that the model has to be downloaded once and its wording is
    a little plainer than Google's.
    """
    from . import local_engine
    if not local_engine.available():
        raise RuntimeError("not installed")
    src = source
    if src in ("auto", "", None):
        src = guess_source(text)
    if not src:
        raise RuntimeError("could not identify the source language")
    if not local_engine.has_pair(src, target):
        raise RuntimeError("no offline model for %s → %s"
                           % (src.split("-")[0], target.split("-")[0]))
    # Line structure has to survive: the overlay maps each line back to the
    # box it came from.
    lines = text.split("\n")
    todo = [ln for ln in lines if ln.strip()]
    done = local_engine.translate_many(todo, src, target)
    result, position = [], 0
    for line in lines:
        if line.strip():
            result.append(done[position])
            position += 1
        else:
            result.append("")
    return "\n".join(result)


def _hymt(text, source, target):
    """Hy-MT2, Tencent's translation model, on this computer. See
    offline_model: downloaded in Settings, run by llama.cpp."""
    from . import offline_model
    lines = str(text or "").split("\n")
    if len([ln for ln in lines if ln.strip()]) > 1:
        # Several lines - copied text, a paragraph from a document: asked
        # for all of them at once, a small model merges or splits lines
        # ("returned 27 lines for 25") and the whole text failed. The
        # snip's way instead: joined into sentences, each translated whole,
        # and shared back over the lines they came from.
        return "\n".join(offline_model.translate_lines(lines, target))
    return offline_model.translate(text, target)


GEMINI_HOST = "https://generativelanguage.googleapis.com/v1beta"

# Asking a language model to translate is different from calling a
# translation endpoint: it can be told what to leave alone. That is the whole
# reason for this backend — a model knows 家家商城 is a shop's name and that a
# phone number is not a quantity, which no amount of post-processing can
# teach a small translation model.
GEMINI_PROMPT = """\
Translate the text between the <text> tags into %(language)s.

Rules:
- Reply with the translation only. No notes, no quotes, no explanation.
- Keep the line breaks exactly: your reply must have the same number of \
lines as the input, in the same order.
- Copy model codes, reference numbers, phone numbers, email and web \
addresses exactly as they appear. Do not translate or reformat them.
- A brand, marque or product name is a name, not a description. Where a \
Chinese, Japanese or Korean name has an established %(language)s name, use \
that name; where it has none, leave it as it is. Never translate the words \
a name is made of — 享界 is the marque Stelato, not "Enjoy", and 方程豹 is \
Fangchengbao, not "Formula Leopard".
- Write dates, times, amounts of money and measurements the way \
%(language)s writes them (for example its decimal separator and date \
order), not word by word. Keep every number's value exactly.
- Write natural, grammatical %(language)s in the register of the original: \
a letter stays a polite letter.
- If a line is already in %(language)s, or cannot be translated, repeat it \
unchanged.

<text>
%(text)s
</text>"""


# Generating takes as long as it takes. 20 seconds was inherited from the
# 5-second default used for short REST calls, and a model under load
# regularly takes longer than that to answer at all — which arrived as a
# socket timeout, escaped every handler here, and was printed in red as
# "The read operation timed out" beside a key that was working.
GEMINI_TIMEOUT = 45
# Reading a screenshot is a bigger request and a longer answer.
GEMINI_IMAGE_TIMEOUT = 75

# What the FIRST attempt is allowed to take, which is a different
# question from what a request may take in total.
#
# Waiting the full ceiling on the first try is what made a fresh machine
# look broken. Nobody waits seventy-five seconds for a screenshot to be
# read; they conclude it does not work, and they are not wrong to — a
# request that has not answered in twenty seconds is not about to become
# useful. The long ceiling still applies to the retry, where the caller
# has already been told what is happening.
GEMINI_FIRST_TIMEOUT = 12
GEMINI_FIRST_IMAGE_TIMEOUT = 20

# And a ceiling on the whole walk. Three models, three attempts each, at
# the old timeouts, is several minutes of a spinner — the app had no
# opinion about how long the user should be kept waiting, only about how
# long each individual request could take.
GEMINI_BUDGET = 25.0
# Reading is one request against a bigger picture, and there is nothing
# else to spend the time on.
GEMINI_IMAGE_BUDGET = 35.0
# ...and more for a bigger one. A snip of a whole 4K screen is a genuinely
# larger job than a paragraph, and holding both to the same deadline
# would fail the large one on principle rather than on evidence. Roughly
# ten seconds per megapixel over the first, up to a minute and a half.
GEMINI_IMAGE_BUDGET_MAX = 90.0
GEMINI_SECONDS_PER_MEGAPIXEL = 10.0


def image_budget(pixels=0):
    """Seconds allowed for reading a picture of `pixels` pixels."""
    megapixels = max(0.0, (pixels or 0) / 1000000.0)
    return min(GEMINI_IMAGE_BUDGET_MAX,
               GEMINI_IMAGE_BUDGET
               + max(0.0, megapixels - 1.0) * GEMINI_SECONDS_PER_MEGAPIXEL)


def _gemini_request(path, key, body=None, timeout=None):
    """Call the Gemini API, with the key in a header.

    Google has begun issuing keys that start with "AQ." instead of "AIza",
    and those are rejected when passed as a ?key= query parameter — which is
    how every older example does it. The x-goog-api-key header works for
    both kinds, so it is the only way used here.

    Errors are raised with the message Google actually sent. "The key was
    not accepted" is not something anyone can act on; "API key not valid" or
    "Generative Language API has not been used in this project" is.
    """
    url = "%s/%s" % (GEMINI_HOST, path)
    headers = {"x-goog-api-key": key, "User-Agent": UA}
    data = None
    if body is not None:
        data = body.encode("utf-8")
        headers["Content-Type"] = "application/json"
    # Counted here rather than at the call sites, because here is the only
    # place that knows a request has actually gone out. Counted before the
    # reply as well: a request that times out on this side has usually
    # still been charged on Google's, and a tally that only records
    # successes would show a small number on the day the allowance ran
    # out — which is exactly the day somebody reads it.
    if body is not None:
        try:
            note_gemini_usage()
        except Exception:
            pass
    seconds = timeout or GEMINI_TIMEOUT
    try:
        return http_pool.fetch(url, data=data, headers=headers,
                               timeout=seconds,
                               context=ssl_context()).decode("utf-8",
                                                             "replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8", "replace"))
            detail = (payload.get("error") or {}).get("message", "")
        except Exception:
            pass
        raise RuntimeError("HTTP %s%s" % (exc.code,
                                          " — " + detail if detail else ""))
    except urllib.error.URLError as exc:
        # A blocked or offline network fails here, not with a status code.
        # Said as "URLError(...)" it reads like a bug in the app; said
        # plainly it points at the network, which is where the fix is.
        raise RuntimeError("could not reach %s (%s) — the network may be "
                           "blocking it" % (_gemini_hostname(),
                                            str(exc.reason)[:60]))
    except (TimeoutError, OSError) as exc:
        # A read timeout is not wrapped in URLError — it comes back as a
        # bare socket error partway through reading the reply, which is why
        # "The read operation timed out" reached the user with no
        # explanation attached and looking like a rejected key.
        #
        # Naming the host matters. Gemini is on a different domain from the
        # Cloud APIs, so a corporate network can allow translation and
        # vision while blocking this one, and every symptom then points at
        # the key.
        raise RuntimeError(
            "timed out after %ds waiting for %s. The service may be slow "
            "at the moment, or this network may be blocking that address — "
            "the Cloud APIs are on a different one, so they can work while "
            "this does not. (%s)"
            % (seconds, _gemini_hostname(), str(exc)[:60]))


# Models that cannot translate text, or that answer in a shape this app
# does not read. Filtered out by name because the listing does not say.
_MODEL_SKIP = ("embedding", "aqa", "tts", "image", "vision", "live",
               "audio", "veo", "imagen", "learnlm", "gemma")


def _gemini_rank(name, prefer_lite=False):
    """Sort key: newest plain Flash first, aliases and Pro models last.

    Ranking rather than picking is deliberate. The listing includes models
    that are listed but refuse to run — a key made today is told
    gemini-2.5-flash "is no longer available to new users" — so the app has
    to be able to walk down a list rather than commit to one name.

    `prefer_lite` flips one term, and it is the per-job split one level
    down. An overlay is twenty short lines of headline and button label,
    where the context a full model brings is worth least and the volume of
    requests is highest; a card is one passage where that context is the
    entire reason for using Gemini at all. Free-tier allowances are listed
    per model, so the two jobs also draw on separate pots.
    """
    low = name.lower()
    match = re.search(r"gemini-(\d+(?:\.\d+)?)", low)
    version = float(match.group(1)) if match else 0.0
    lite = "lite" in low
    return (
        0 if "flash" in low else 1,        # flash is the fast, cheap tier
        1 if ("preview" in low or "-exp" in low) else 0,   # stable first
        -version,                          # newest first
        (0 if lite else 1) if prefer_lite else (1 if lite else 0),
        name,
    )


def _gemini_candidates(key, prefer_lite=False):
    """Every model this key could plausibly use, best first.

    "-latest" aliases are skipped on purpose: they point at whatever Google
    decides, and when that target is retired the alias starts failing with
    a 404 that names a model the app never asked for.
    """
    raw = _gemini_request("models", key)
    names = []
    for entry in json.loads(raw).get("models", []):
        methods = entry.get("supportedGenerationMethods") or []
        if "generateContent" not in methods:
            continue
        name = str(entry.get("name", "")).split("/")[-1]
        low = name.lower()
        if not name or low.endswith("-latest"):
            continue
        if any(word in low for word in _MODEL_SKIP):
            continue
        names.append(name)
    if not names:
        raise RuntimeError("this key has no models that can translate")
    names.sort(key=lambda name: _gemini_rank(name, prefer_lite))
    # Three, not six. Every dead name costs a round trip while the person is
    # waiting: if the three best models will not run, a fourth will not save
    # the translation, and dropping through to another service is quicker.
    return names[:3]


def _gemini_hostname():
    return GEMINI_HOST.split("//")[-1].split("/")[0]


def _model_is_gone(exc):
    """Is this the API saying "not that model" rather than a real failure?"""
    text = str(exc).lower()
    return ("http 404" in text or "no longer available" in text
            or "not found" in text or "is not supported" in text)


def _model_is_busy(exc):
    """Is this "come back in a moment" rather than anything being wrong?

    Gemini's free tier answers 503 "the model is experiencing high demand"
    often enough that treating it as a failure made the whole engine look
    broken: a valid key, tested in Settings, reported in red as though it
    had been rejected. Nothing was wrong with it and nothing the user could
    do would have helped.
    """
    text = str(exc).lower()
    # Squint's own words first.
    #
    # This is the one that bit. _gemini_generate turns a busy model into
    # RuntimeError(BUSY_MESSAGE) — a sentence written for a person, which
    # contains none of the words below. So the app raised its own message
    # and then failed to recognise it, filed a busy Gemini as a rejected
    # key, and painted a red mark beside a key while the text underneath
    # said in plain English that the key was fine.
    #
    # Anything that rewrites an error into friendlier language has to be
    # matched by whatever reads that error afterwards, or the translation
    # is one-way and the meaning is lost between two parts of the same
    # program.
    if BUSY_MESSAGE.lower()[:30] in text:
        return True
    return ("http 503" in text or "overloaded" in text
            or "high demand" in text or "unavailable" in text
            # A timeout is the same situation wearing different clothes:
            # the service is not answering now and may well answer in a
            # moment. Treating it as fatal is what put "The read operation
            # timed out" in red next to a working key.
            or "timed out" in text or "timeout" in text)


# How long to wait before asking the same model again. Two short pauses,
# because a spike is usually seconds long — and then the next model in the
# list, because "flash is busy" says nothing about flash-lite. Longer waits
# would just be a hotkey that does nothing for ten seconds.
BUSY_WAITS = (0.8, 2.5)


BUSY_MESSAGE = ("Gemini is busy at the moment — Google's side, not your "
                "key. It is usually over in a minute.")


def _seed_other_model(models, fast):
    """Fill in the other job's model from the same listing.

    Splitting the remembered model in two — one for overlays, one for
    cards — gave each its own discovery walk, so a fresh key paid for the
    listing twice on its first snip: once to read the screenshot and again
    to translate what was read. Two round trips before anything appeared,
    on the one machine where nothing is cached and the person is deciding
    whether the app works.

    One listing answers both questions. It is the same list; only the
    ordering differs.
    """
    from . import config
    other = "gemini_model" if fast else "gemini_model_fast"
    try:
        if str(config.CONFIG.get(other, "") or "").strip():
            return
        ranked = sorted(models,
                        key=lambda name: _gemini_rank(name, not fast))
        if ranked:
            config.CONFIG.set(other, ranked[0])
    except Exception:
        pass


def _attempt_timeout(timeout, index, image):
    """Short on the first try, the full ceiling afterwards.

    The ceiling is right for a model that is genuinely working hard on a
    big screenshot. It is wrong as a first guess, because the common
    reason a request has not answered is that it is not going to — and
    seventy-five seconds of that is indistinguishable from a broken app.
    """
    if timeout is not None:
        return timeout
    if index == 0:
        return GEMINI_FIRST_IMAGE_TIMEOUT if image else GEMINI_FIRST_TIMEOUT
    return GEMINI_IMAGE_TIMEOUT if image else GEMINI_TIMEOUT


# Gemini 2.5 and later think before they answer unless told not to - on by
# default, seconds of it, and counted against the allowance. Translation
# gains nothing from it. Models that refuse the setting are remembered.
_no_thinking_off = set()


def _thinking_off(body, model):
    """`body` (JSON text) asking `model` not to think, or `body` itself
    when that is not a setting this model takes."""
    low = str(model).lower()
    if model in _no_thinking_off or "gemini" not in low:
        return body
    try:
        data = json.loads(body)
    except Exception:
        return body
    config = data.setdefault("generationConfig", {})
    if "gemini-2.5" in low:
        if "pro" in low:
            return body              # Pro cannot turn it off
        config["thinkingConfig"] = {"thinkingBudget": 0}
    elif re.match(r".*gemini-[3-9]", low):
        config["thinkingConfig"] = {"thinkingLevel": "low"}
    else:
        return body
    return json.dumps(data)


def _gemini_generate(key, body, timeout=None, attempts=None,
                     fast=False, image=False, pixels=0):
    """Ask for a translation, walking down the model list past dead names.

    Returns the raw reply. The model that answered is remembered, so this
    costs one extra request the first time and none afterwards — and if
    that remembered model is retired later, the same walk happens again
    instead of the app simply breaking.
    """
    from . import config
    # Two remembered models, not one: the fast job and the careful job
    # settle on different names and each has to be able to walk past its
    # own retirements without disturbing the other.
    setting = "gemini_model_fast" if fast else "gemini_model"
    cached = str(config.CONFIG.get(setting, "") or "")
    models, listed = ([cached] if cached else []), False
    tried, last = [], None
    started = time.monotonic()
    budget = image_budget(pixels) if image else GEMINI_BUDGET

    busy = None
    while True:
        for model in models:
            if model in tried:
                continue
            tried.append(model)
            raw, gone = None, False
            # The first attempt has no wait in front of it; the others do.
            #
            # `attempts` exists because a retry is not free. A request that
            # times out on this side has usually still been counted on
            # Google's, so retrying spends the daily allowance three times
            # to answer one question. Testing a key is asked to do it once.
            waits = (0.0,) + BUSY_WAITS
            if attempts:
                waits = waits[:max(1, attempts)]
            for index, wait in enumerate(waits):
                # The budget is for the whole walk, not for each request,
                # and it is clamped rather than merely checked: starting a
                # seventy-five-second attempt with four seconds left on
                # the clock honours the letter of a deadline and none of
                # its purpose.
                left = budget - (time.monotonic() - started)
                if left < 2.0:
                    raw = None
                    break
                if wait:
                    if wait > left:
                        raw = None
                        break
                    time.sleep(wait)
                    left -= wait
                try:
                    path = ("models/%s:generateContent"
                            % urllib.parse.quote(model))
                    wait_for = min(_attempt_timeout(timeout, index, image),
                                   left)
                    quick = _thinking_off(body, model)
                    try:
                        raw = _gemini_request(path, key, quick, wait_for)
                    except RuntimeError as exc:
                        # A model that will not take the setting: once
                        # more as it was.
                        if quick is body or "400" not in str(exc) or \
                                "think" not in str(exc).lower():
                            raise
                        _no_thinking_off.add(model)
                        raw = _gemini_request(path, key, body, wait_for)
                except RuntimeError as exc:
                    if _model_is_gone(exc):
                        last, gone = exc, True
                        break
                    if _model_is_busy(exc):
                        busy = exc
                        continue      # same model, after a pause
                    raise
                busy = None
                break
            if gone or raw is None:
                # Busy after every attempt. The next model in the list is
                # a different pool of capacity, so it is worth asking
                # before giving up — and if the list runs out, the caller
                # falls through to another engine entirely.
                continue
            if model != cached:
                try:
                    config.CONFIG.set(setting, model)
                except Exception:
                    pass
            return raw
        if listed or time.monotonic() - started > budget - 2.0:
            break
        # The remembered model did not answer, or there was none. Ask what
        # exists — but only forget the remembered name if it was actually
        # retired. Busy is not evidence that a model has gone away, and
        # forgetting it there makes the next translation pay for a model
        # listing it did not need, every time Google has a busy minute.
        listed = True
        if last is not None:
            try:
                config.CONFIG.set(setting, "")
            except Exception:
                pass
        models = _gemini_candidates(key, prefer_lite=fast)
        _seed_other_model(models, fast)

    if busy is not None:
        raise RuntimeError(BUSY_MESSAGE)
    raise RuntimeError(str(last) if last else "no usable model for this key")


# The last test's verdict per key: name -> (ok, message), where ok is
# True, False, or None for "could not be judged" — busy, or out of
# allowance, neither of which says anything about the key itself.
KEY_RESULTS = {}


# Normally three tries; one while Settings is testing a key, where the
# question is "does this work" and spending nine requests to answer it is
# how a free allowance disappears before it has been used for anything.
_gemini_attempts = None


def _gemini(text, source, target):
    """Translate with Google's Gemini, which has a free API key."""
    fast = current_job() == SPEED
    key = _api_key("gemini_api_key")
    if not key:
        raise RuntimeError("no key")
    from .langs import name_for
    language = name_for(target) or target

    body = json.dumps({
        "contents": [{"parts": [{"text": GEMINI_PROMPT % {
            "language": language, "text": text}}]}],
        # Deterministic: translation is not a place for invention.
        "generationConfig": {"temperature": 0, "topP": 0.1},
    })
    raw = _gemini_generate(key, body, attempts=_gemini_attempts,
                           fast=fast)
    payload = json.loads(raw)
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("no reply (%s)" % str(payload)[:80])
    parts = (candidates[0].get("content") or {}).get("parts") or []
    out = "".join(p.get("text", "") for p in parts).strip()
    if not out:
        raise RuntimeError("empty reply")

    # Strip the tags if the model echoed them back.
    if out.startswith("<text>"):
        out = out[len("<text>"):]
    if out.endswith("</text>"):
        out = out[:-len("</text>")]
    out = out.strip("\n")

    # The overlay maps each line to the box it came from, so a reply with a
    # different number of lines cannot be used, however good it reads.
    wanted = len(text.split("\n"))
    got = len(out.split("\n"))
    if wanted > 1 and got != wanted:
        raise RuntimeError("returned %d lines for %d" % (got, wanted))
    return out


def _api_key(name):
    from . import config
    return str(config.CONFIG.get(name, "") or "").strip()


def _google_api(text, source, target):
    """The paid Google endpoint, when a key is configured.

    Worth supporting because the free hosts are rate-limited per IP address:
    on a shared office connection they answer 429 all day, and the fallbacks
    that do work are noticeably clumsier. A key removes both problems.
    """
    key = _api_key("google_api_key")
    if not key:
        raise RuntimeError("no key")
    body = "q=%s&target=%s&format=text" % (
        urllib.parse.quote(text), urllib.parse.quote(target.split("-")[0]))
    if source not in ("auto", "", None):
        body += "&source=" + urllib.parse.quote(source.split("-")[0])
    raw = _fetch("https://translation.googleapis.com/language/translate/v2"
                 "?key=" + urllib.parse.quote(key), data=body)
    payload = json.loads(raw)
    parts = payload["data"]["translations"]
    # Google bills by characters sent, and the free allowance is 500,000 a
    # month. Counting them here — at the one place they are actually spent —
    # is what lets Settings say how much is left before anything is charged.
    note_google_usage(len(text))
    return "\n".join(p.get("translatedText", "") for p in parts)


def _google_api_lines(lines, source, target):
    """Many lines through the Google key in one request, one answer each.

    The glossary is applied line by line, as `translate` would, and a
    Korean particle is joined to its word the same way.
    """
    from . import glossary
    key = _api_key("google_api_key")
    if not key:
        raise RuntimeError("no key")
    sent, kept = [], []
    for line in lines:
        text = line.strip()
        try:
            text, protected = glossary.protect(text, source=source,
                                               target=target)
        except Exception:
            protected = {}
        sent.append(text)
        kept.append(protected)
    wanted = [i for i, text in enumerate(sent) if text]
    if not wanted:
        return ["" for _ in lines]
    body = "&".join("q=" + urllib.parse.quote(sent[i]) for i in wanted)
    body += "&target=%s&format=text" % urllib.parse.quote(target.split("-")[0])
    if source not in ("auto", "", None):
        body += "&source=" + urllib.parse.quote(source.split("-")[0])
    raw = _fetch("https://translation.googleapis.com/language/translate/v2"
                 "?key=" + urllib.parse.quote(key), data=body)
    parts = json.loads(raw)["data"]["translations"]
    if len(parts) != len(wanted):
        raise RuntimeError("Google answered %d of %d lines"
                           % (len(parts), len(wanted)))
    note_google_usage(sum(len(sent[i]) for i in wanted))
    out = ["" for _ in lines]
    korean = str(target or "").lower().startswith("ko")
    for i, part in zip(wanted, parts):
        text = part.get("translatedText", "")
        if kept[i]:
            try:
                text = glossary.restore(text, kept[i])
            except Exception:
                pass
        if korean:
            text = korean_particles(text)
        out[i] = text
    _remember("google-api-key")
    return out


GOOGLE_FREE_CHARS = 500000
_usage_lock = threading.Lock()


def _this_month():
    return time.strftime("%Y-%m")


def _today():
    """Google's day, not this machine's.

    The allowance resets at midnight Pacific, so a counter on local
    midnight would reset at the wrong moment twice — once at 01:00 in
    Germany showing yesterday's spend as today's, and again nine hours
    later when Google actually rolls over.
    """
    import datetime
    # Pacific is UTC-8, or UTC-7 while daylight saving is on. Being an
    # hour out twice a year costs nothing here: this is a tally shown to
    # a person, not a billing record.
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=8)).strftime("%Y-%m-%d")


def gemini_usage():
    """(requests Squint has made today, today's date).

    A tally with no denominator, and that is the honest shape of it.
    Google does not report what is left and has stopped publishing the
    free-tier figures, so a fraction here would be a number this app
    invented. What it can say is what it spent, which is the question
    somebody asks when the allowance runs out sooner than expected — and
    it is blind to anything else using the same key, which the label says.
    """
    from . import config
    with _usage_lock:
        record = config.CONFIG.get("gemini_usage", {}) or {}
        if not isinstance(record, dict) or record.get("day") != _today():
            return 0, _today()
        try:
            return int(record.get("calls", 0)), _today()
        except Exception:
            return 0, _today()


def note_gemini_usage(count=1):
    from . import config
    day = _today()
    with _usage_lock:
        record = config.CONFIG.get("gemini_usage", {}) or {}
        if not isinstance(record, dict) or record.get("day") != day:
            record = {"day": day, "calls": 0}
        try:
            record["calls"] = int(record.get("calls", 0)) + int(count)
        except Exception:
            record["calls"] = int(count)
        try:
            config.CONFIG.set("gemini_usage", record)
        except Exception:
            pass


def google_usage():
    """(characters used this calendar month, the free allowance)."""
    from . import config
    with _usage_lock:
        record = config.CONFIG.get("google_usage", {}) or {}
        if not isinstance(record, dict) or record.get("month") != _this_month():
            return 0, GOOGLE_FREE_CHARS
        try:
            return int(record.get("chars", 0)), GOOGLE_FREE_CHARS
        except Exception:
            return 0, GOOGLE_FREE_CHARS


def note_google_usage(count):
    """Add to this month's tally, starting fresh when the month turns over."""
    from . import config
    month = _this_month()
    with _usage_lock:
        record = config.CONFIG.get("google_usage", {}) or {}
        if not isinstance(record, dict) or record.get("month") != month:
            record = {"month": month, "chars": 0}
        try:
            record["chars"] = int(record.get("chars", 0)) + max(0, int(count))
        except Exception:
            record = {"month": month, "chars": max(0, int(count))}
        try:
            config.CONFIG.set("google_usage", record)
        except Exception:
            pass


# -- Groq ----------------------------------------------------------------
#
# A second free key with no card: an account at console.groq.com and one
# button. Groq serves open models, very fast, behind the same chat API
# everyone copies from OpenAI. Its list of models changes every few months
# — four of them were retired in the three months before this was written —
# so the name is not fixed here: the key's own model list is asked once, the
# first of PREFERRED that it offers is used and remembered, and a model that
# has gone is walked past the same way Gemini's are.
GROQ_HOST = "https://api.groq.com/openai/v1"

# Best for this job first. Qwen is strongest on Chinese, Japanese and
# Korean; gpt-oss is the steadiest all-rounder; the rest are there so a key
# still works the day the first two are renamed.
GROQ_PREFERRED = ("qwen/qwen3.8-27b", "openai/gpt-oss-120b",
                  "openai/gpt-oss-20b", "llama-3.3-70b-versatile")
GROQ_FAMILIES = ("qwen", "gpt-oss", "llama", "kimi", "mistral")
GROQ_SKIP = ("whisper", "guard", "orpheus", "tts", "safeguard", "compound",
             "embed")
GROQ_TIMEOUT = 20

_THINK = re.compile(r"<think>.*?</think>", re.S)


def _groq_call(path, key, body=None, timeout=GROQ_TIMEOUT):
    """GET or POST against Groq. Raises with Groq's own words."""
    try:
        # Through the pool, so a snip reuses the connection the last one
        # opened instead of paying for a new handshake.
        return http_pool.fetch(
            GROQ_HOST + "/" + path,
            data=body.encode("utf-8") if body is not None else None,
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json",
                     "User-Agent": "Squint"},
            timeout=timeout, context=ssl_context(),
        ).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_describe(exc))


def _groq_rank(name):
    low = name.lower()
    if name in GROQ_PREFERRED:
        return (0, GROQ_PREFERRED.index(name))
    for index, family in enumerate(GROQ_FAMILIES):
        if family in low:
            # Bigger is better within a family, as far as a name says.
            size = re.findall(r"(\d+)b", low)
            return (1 + index, -int(size[-1]) if size else 0)
    return (99, 0)


def _groq_models(key):
    raw = json.loads(_groq_call("models", key))
    names = [m.get("id", "") for m in raw.get("data", [])
             if m.get("active", True) is not False]
    names = [n for n in names
             if n and not any(skip in n.lower() for skip in GROQ_SKIP)]
    names.sort(key=_groq_rank)
    return names


def _groq_body(model, prompt):
    body = {"model": model, "temperature": 0,
            "messages": [{"role": "user", "content": prompt}]}
    low = model.lower()
    # Reasoning models think out loud before answering, which costs
    # seconds and tokens and adds nothing to a translation.
    if "qwen3" in low:
        body["reasoning_effort"] = "none"
    elif "gpt-oss" in low:
        body["reasoning_effort"] = "low"
    return body


def _groq(text, source, target):
    """Translate with a free Groq key."""
    from . import config
    from .langs import name_for
    key = _api_key("groq_api_key")
    if not key:
        raise RuntimeError("no key")
    language = name_for(target) or target
    prompt = GEMINI_PROMPT % {"language": language, "text": text}

    remembered = str(config.CONFIG.get("groq_model", "") or "")
    models, listed, last = ([remembered] if remembered else []), False, None
    tried = []
    while True:
        for model in models:
            if model in tried:
                continue
            tried.append(model)
            body = _groq_body(model, prompt)
            try:
                raw = _groq_call("chat/completions", key, json.dumps(body))
            except RuntimeError as exc:
                last = exc
                said = str(exc).lower()
                if "reasoning" in said and "HTTP 400" in str(exc):
                    # This model does not take the setting; ask plainly.
                    body.pop("reasoning_effort", None)
                    try:
                        raw = _groq_call("chat/completions", key,
                                         json.dumps(body))
                    except RuntimeError as again:
                        last = again
                        continue
                elif ("model" in said and ("not found" in said
                                           or "decommissioned" in said
                                           or "does not exist" in said)):
                    continue
                else:
                    raise
            payload = json.loads(raw)
            choices = payload.get("choices") or []
            if not choices:
                raise RuntimeError("no reply (%s)" % str(payload)[:80])
            out = (choices[0].get("message") or {}).get("content") or ""
            out = _THINK.sub("", out).strip()
            if out.startswith("<text>"):
                out = out[len("<text>"):]
            if out.endswith("</text>"):
                out = out[:-len("</text>")]
            out = out.strip("\n")
            if not out:
                raise RuntimeError("empty reply")
            if model != remembered:
                try:
                    config.CONFIG.set("groq_model", model)
                except Exception:
                    pass
            wanted = len(text.split("\n"))
            got = len(out.split("\n"))
            if wanted > 1 and got != wanted:
                raise RuntimeError("returned %d lines for %d"
                                   % (got, wanted))
            return out
        if listed:
            break
        listed = True
        models = _groq_models(key)
    raise last or RuntimeError("no Groq model available for this key")


def _deepl_api(text, source, target):
    """DeepL, which many people rate above Google for European languages."""
    key = _api_key("deepl_api_key")
    if not key:
        raise RuntimeError("no key")
    # Free keys end in ':fx' and use a different host.
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
    body = "auth_key=%s&text=%s&target_lang=%s" % (
        urllib.parse.quote(key), urllib.parse.quote(text),
        urllib.parse.quote(target.split("-")[0].upper()))
    raw = _fetch("https://%s/v2/translate" % host, data=body)
    payload = json.loads(raw)
    return "\n".join(t.get("text", "") for t in payload.get("translations", []))


def _gtx(text, source, target, host="translate.googleapis.com"):
    """The endpoint the Chrome address bar uses. JSON, not scraped HTML."""
    base = ("https://%s/translate_a/single?client=gtx&sl=%s&tl=%s&dt=t"
            % (host, urllib.parse.quote(source), urllib.parse.quote(target)))
    body = "q=" + urllib.parse.quote(text)
    # Short text as a GET (one fewer round trip); long text must be POSTed
    # or the URL exceeds what the server accepts.
    if len(body) < 1500:
        raw = _fetch(base + "&" + body)
    else:
        raw = _fetch(base, data=body)
    payload = json.loads(raw)
    segments = payload[0] or []
    return "".join(part[0] for part in segments
                   if part and isinstance(part[0], str))


def _gtx_clients5(text, source, target):
    """Same protocol, different host — different infrastructure behind it,
    so it frequently answers when the first one is rate-limiting."""
    return _gtx(text, source, target, host="clients5.google.com")


def _gtx_www(text, source, target):
    """A third host for the same endpoint. Costs nothing to try and is
    sometimes the only one a corporate network has not blocked."""
    return _gtx(text, source, target, host="translate.google.com")


# Public front-ends that make the request server-side. Each is run by a
# different volunteer, so they fail independently — which is the point.
LINGVA_HOSTS = ("lingva.ml", "lingva.lunar.icu", "lingva.garudalinux.org")


def _lingva_any(text, source, target):
    last = None
    for host in LINGVA_HOSTS:
        try:
            url = "https://%s/api/v1/%s/%s/%s" % (
                host, urllib.parse.quote(source), urllib.parse.quote(target),
                urllib.parse.quote(text, safe=""))
            out = json.loads(_fetch(url)).get("translation", "")
            if out and not _is_broken(out, text):
                return out
        except Exception as exc:
            last = exc
    raise RuntimeError(_describe(last) if last else "no instance answered")


def _simplytranslate(text, source, target):
    """Another independent proxy in front of Google."""
    url = ("https://simplytranslate.org/api/translate/"
           "?engine=google&from=%s&to=%s&text=%s"
           % (urllib.parse.quote(source), urllib.parse.quote(target),
              urllib.parse.quote(text, safe="")))
    data = json.loads(_fetch(url))
    return data.get("translated-text") or data.get("translated_text") or ""


def _deep(text, source, target):
    if GoogleTranslator is None:
        raise RuntimeError("deep-translator not installed")
    return GoogleTranslator(source=source, target=target).translate(text)


def _lingva(text, source, target):
    """A public front-end to Google that does its own request server-side."""
    url = "https://lingva.ml/api/v1/%s/%s/%s" % (
        urllib.parse.quote(source), urllib.parse.quote(target),
        urllib.parse.quote(text, safe=""))
    return json.loads(_fetch(url)).get("translation", "")


def _mymemory_one(piece, src, tgt):
    url = ("https://api.mymemory.translated.net/get?q=%s&langpair=%s|%s"
           % (urllib.parse.quote(piece), src, tgt))
    data = json.loads(_fetch(url))
    translated = (data.get("responseData") or {}).get("translatedText") or ""

    # MyMemory is a translation *memory* first and a translator second: the
    # headline result can be somebody's stored segment that merely resembles
    # the input. That is how "how are you beautiful" came back as "Wieso
    # solltest du schöner sein?" — a real German sentence, and not a
    # translation of anything that was asked. The machine-translation entry
    # in `matches` is the one to trust, so prefer it when it is offered.
    best_mt = None
    for match in (data.get("matches") or []):
        created_by = str(match.get("created-by", "")).upper()
        candidate = (match.get("translation") or "").strip()
        if candidate and "MT" in created_by:
            best_mt = candidate
            break
    if best_mt:
        translated = best_mt
    else:
        try:
            quality = float((data.get("responseData") or {}).get("match", 1))
        except (TypeError, ValueError):
            quality = 1.0
        if quality < 0.85:
            raise RuntimeError("only a weak memory match (%.2f)" % quality)
    # The daily allowance is refused with a 200 and this text in the body,
    # which would otherwise be drawn on screen as if it were a translation.
    if "MYMEMORY WARNING" in translated.upper() or \
            "QUOTA" in str(data.get("responseDetails", "")).upper():
        raise RuntimeError("daily free limit reached")
    if not translated:
        raise RuntimeError("no result")
    return translated


def _mymemory(text, source, target):
    """Independent of Google entirely — often the only one a corporate
    network allows through.

    Two constraints shape this: each request is capped near 500 characters,
    and it needs a real source language rather than 'auto'.

    Line breaks are translated one line at a time on purpose. MyMemory
    collapses newlines, and the overlay positions each translated line over
    the line it came from — losing the breaks means the count no longer
    matches and every line lands in the wrong place.
    """
    src = source
    if src in ("auto", "", None):
        src = guess_source(text)
    src = (src or "").split("-")[0]
    tgt = target.split("-")[0]
    if not src:
        # Guessing wrong here is worse than not guessing: an unknown source
        # became "en", which equalled the target, which returned the input.
        raise RuntimeError("could not identify the source language")
    if src == tgt:
        raise RuntimeError("source and target are both %s" % tgt)

    # One request per line, but run together. Sequentially, a 20-line snip
    # meant 20 round trips end to end — which is why a bigger selection felt
    # so much slower. The requests do not depend on each other, so the whole
    # snip costs about as long as its slowest line.
    jobs = []
    for line in text.split("\n"):
        jobs.append(_hard_split(line, 480) if line.strip() else [])

    flat = [(i, j, piece)
            for i, pieces in enumerate(jobs)
            for j, piece in enumerate(pieces)]
    results = {}
    if flat:
        from concurrent.futures import ThreadPoolExecutor
        # Modest: this is a free service, and hammering it earns a 429.
        workers = min(6, len(flat))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_mymemory_one, piece, src, tgt): (i, j)
                       for i, j, piece in flat}
            for future in futures:
                results[futures[future]] = future
        for key, future in results.items():
            results[key] = future.result()      # re-raises the first failure

    out_lines = []
    for i, pieces in enumerate(jobs):
        if not pieces:
            out_lines.append("")
            continue
        out_lines.append(" ".join(results[(i, j)]
                                  for j in range(len(pieces))))
    return "\n".join(out_lines)


# Keyed services first: if the user has configured one, it is both faster
# (no walking down a list of rate-limited hosts) and better. They raise
# immediately when no key is set, which costs nothing.
BACKENDS = (
    # A language model first when a key is set: it is the only engine that
    # understands what a brand name is, which is where the others fail.
    ("gemini", _gemini),
    # A second free key, and quick: behind Gemini, raced against it with
    # the rest (see `_race_gemini`).
    ("groq", _groq),
    # Then the local model: free, private, no rate limit, works offline.
    ("offline", _offline),
    ("google-api-key", _google_api),
    ("deepl-api-key", _deepl_api),
    # Hy-MT2 on this computer, when it has been downloaded: behind every
    # online engine that answers in under a second, ahead of the free web
    # services for a card, and the whole of "On this computer only".
    ("hymt", _hymt),
    ("gtx", _gtx),
    ("clients5", _gtx_clients5),
    ("google-www", _gtx_www),
    ("deep-translator", _deep),
    ("simplytranslate", _simplytranslate),
    ("lingva", _lingva_any),
    ("mymemory", _mymemory),
)


def _ordered_backends():
    _load_preferred()
    with _preferred_lock:
        first = _preferred
    # Hy-MT2 answered last only because "On this computer only" was chosen.
    # Under Automatic it must not lead: it takes seconds a snip, and it led
    # every snip after the choice was switched back.
    if not first or first == "hymt":
        return list(BACKENDS)
    rest = [b for b in BACKENDS if b[0] != first]
    head = [b for b in BACKENDS if b[0] == first]
    ordered = head + rest
    # With a Gemini key, Gemini stays first whoever answered last time: it
    # is raced against Google on every request (see `_race_gemini`), and a
    # Google win must not quietly take Gemini out of the race for good.
    if first != "gemini" and _api_key("gemini_api_key"):
        ordered = ([b for b in ordered if b[0] == "gemini"]
                   + [b for b in ordered if b[0] != "gemini"])
    return ordered


def _remember(name):
    """Remember the winner, and keep it across restarts.

    Held only in memory, this was relearned on every launch: three
    rate-limited hosts timing out before the first translation of each
    session. Saved, the very first request goes straight to what worked
    last time.
    """
    global _preferred
    with _preferred_lock:
        if _preferred == name:
            return
        _preferred = name
    try:
        from . import config
        if config.CONFIG.get("last_backend") != name:
            config.CONFIG.set("last_backend", name)
    except Exception:
        pass


def _load_preferred():
    global _preferred
    if _preferred:
        return _preferred
    try:
        from . import config
        saved = str(config.CONFIG.get("last_backend", "") or "")
        if saved in dict(BACKENDS):
            _preferred = saved
    except Exception:
        pass
    return _preferred


def active_backend():
    """Which backend answered last — for the self-test and the log."""
    with _preferred_lock:
        return _preferred or "(none yet)"


# What to call each backend on screen. The internal names are for the log.
ENGINE_NAMES = {
    "gemini": "Gemini",
    "groq": "Groq",
    "google-api-key": "Google",
    "deepl-api-key": "DeepL",
    "offline": "offline, on this computer",
    "hymt": "Hy-MT2, on this computer",
    "gtx": "Google (free)",
    "clients5": "Google (free)",
    "google-www": "Google (free)",
    "deep-translator": "Google (free)",
    "simplytranslate": "SimplyTranslate",
    "lingva": "Lingva",
    "mymemory": "MyMemory",
}


def engine_label(name=None):
    """A short, plain name for whichever engine produced a translation.

    Worth showing next to the result: the engines available here differ
    visibly in quality, so "was this Google or the offline model?" is a
    fair question to have answered without digging through a log.
    """
    name = name or active_backend()
    if name == "(none yet)":
        # Nothing has answered yet in this session: say nothing rather
        # than put "(none yet)" on a page that is about to be translated.
        return ""
    return ENGINE_NAMES.get(name, name)


# Which setting holds each key shown in Settings, by the name on its row.
KEY_SETTINGS = {"Gemini": "gemini_api_key", "Groq": "groq_api_key",
                "Google": "google_api_key", "DeepL": "deepl_api_key"}


def _key_tail(name):
    return _api_key(KEY_SETTINGS.get(name, ""))[-6:]


def _save_key_checks(results):
    """Keep each key's last verdict, so its dot is there next time Settings
    opens — against the key it was about, by its last six characters, and
    never a key's value."""
    try:
        from . import config
        kept = {name: [good, why, _key_tail(name)]
                for name, (good, why) in results.items()}
        config.CONFIG.set("key_checks", kept)
    except Exception:
        pass


def load_key_checks():
    """Fill KEY_RESULTS from the last check, for keys that have not changed
    since. A key that has changed has no verdict until it is tested."""
    try:
        from . import config
        kept = config.CONFIG.get("key_checks", {}) or {}
    except Exception:
        kept = {}
    KEY_RESULTS.clear()
    for name, entry in kept.items():
        try:
            good, why, tail = entry
        except Exception:
            continue
        if tail and tail == _key_tail(name):
            KEY_RESULTS[name] = (good, why)
    return dict(KEY_RESULTS)


def check_keys():
    """Try each saved key on its own service. Return (ok, message).

    Deliberately not routed through translate(): translate() catches a
    failing backend, quietly falls back to a free service and returns a
    perfectly good translation. Settings would then say everything worked
    while the key sat there rejected. Calling each backend directly means
    the message the service sent is the message shown — "API key not
    valid" and "the API is not enabled for this project" need different
    things done about them, and the user cannot do either one if the app
    just says "not accepted".
    """
    global _gemini_attempts
    _cooldown.clear()
    _gemini_attempts = 1
    tests = (("Gemini", "gemini_api_key", _gemini),
             ("Groq", "groq_api_key", _groq),
             ("Google", "google_api_key", _google_api),
             ("DeepL", "deepl_api_key", _deepl_api))
    good, bad = [], []
    # Per key as well as joined. One line with one colour said Google was
    # broken because Gemini's allowance had run out — three working keys
    # painted red by the fourth. A verdict about four things is not a
    # verdict.
    results = {}
    for name, key_name, backend in tests:
        if not _api_key(key_name):
            continue
        try:
            out = backend("Guten Morgen", "de", "en")
            good.append("%s ok → %s" % (name, out.strip()[:24]))
            results[name] = (True, "ok → %s" % out.strip()[:24])
        except Exception as exc:
            detail = str(exc)
            if _model_is_busy(exc):
                # Not a bad key, and not something to show in red. The
                # test could not be run, which is a different answer from
                # "the key was rejected" and has to read like one.
                good.append("%s: %s" % (name, BUSY_MESSAGE))
                results[name] = (True, BUSY_MESSAGE)
                continue
            if "429" in detail or "quota" in detail.lower():
                # The key is fine; there is simply none of the free
                # allowance left. Saying so saves the user hunting for a
                # fault in a key that works.
                detail = ("out of free quota for now — the key is valid. "
                          "It resets; meanwhile the app uses the other "
                          "engines.")
            bad.append("%s: %s" % (name, detail[:150]))
            # Out of allowance is not a rejected key, and colouring it the
            # same teaches people to distrust a key that is perfectly
            # good. It is a warning, which is a third answer.
            spent = "out of free quota" in detail
            results[name] = (None if spent else False, detail[:150])
    _gemini_attempts = None
    KEY_RESULTS.clear()
    KEY_RESULTS.update(results)
    _save_key_checks(results)
    if not good and not bad:
        try:
            out = translate("Guten Morgen", target="en")
            return True, "no keys set; using %s → %s" % (active_backend(),
                                                         out.strip()[:24])
        except Exception as exc:
            return False, str(exc)[:110]
    return (not bad), "   ·   ".join(bad or good)


def _translate_once(text, source, target, job=None, avoid=()):
    """One chunk, through whichever backend can actually do it.

    Names are masked before any engine sees the text and put back after, so
    brands and model codes survive whichever backend answers rather than
    being reinvented by each one differently.
    """
    from . import glossary
    try:
        # The source language, when it is known, so a rule written for one
        # language cannot rewrite another's words.
        text, protected = glossary.protect(text, source=source,
                                           target=target)
    except Exception:
        protected = {}

    backends = _ordered_backends()

    # An explicit choice in Settings goes first, but the others stay behind
    # it as a fallback.
    #
    # They used to be dropped entirely, on the reasoning that someone who
    # picked a service wants that service. That turned an ordinary hiccup
    # into a dead app: Gemini's free tier ran out of quota, answered 429,
    # and because it was the only backend left there was nothing to fall
    # back to — every translation simply failed. A preference is not worth
    # that. The chosen engine is tried first every time; if it cannot
    # answer, something else does and the status line says which.
    _job.value = job
    try:
        from . import profile
        wanted, may_fall_back = profile.translating(job)
    except Exception:
        wanted, may_fall_back = [], True
    if _background():
        wanted, may_fall_back = ["hymt"], False
    if avoid:
        wanted = [name for name in wanted if name not in avoid]
        backends = [b for b in backends if b[0] not in avoid]
        # Asked again without Gemini, because its answer could not be
        # used. Google was asked the same question during the race.
        kept = _hedged.pop((text, source, target), None)
        if "gemini" in avoid and kept \
                and time.monotonic() - kept[0] < _HEDGE_KEEP:
            name, result = kept[1]
            _remember(name)
            if protected:
                try:
                    result = glossary.restore(result, protected)
                except Exception:
                    pass
            if str(target or "").lower().startswith("ko"):
                result = korean_particles(result)
            return result

    if wanted and not may_fall_back:
        # "On this computer" and nothing behind it.
        #
        # Every other choice keeps the rest as a fallback, and that is
        # right — a preference is not worth a dead app, which is what
        # happened when Gemini's quota ran out and the pinned backend
        # answered 429 to everything. This one is different in kind.
        # Somebody who picked it may have picked it so that nothing
        # leaves the machine, and posting their text to a free web
        # service instead is not a smaller failure than refusing. It is a
        # worse one, and they would never know it had happened.
        only = [b for b in BACKENDS if b[0] in wanted]
        if not only:
            raise TranslationError(OFFLINE_ONLY)
        try:
            return _run_backends(only, text, source, target, protected,
                                 glossary)
        except TranslationError as exc:
            # Hy-MT2 is set up and still could not answer: say what it
            # said, not that nothing is installed.
            try:
                from . import offline_model
                if offline_model.ready():
                    raise TranslationError(
                        "Hy-MT2 on this computer could not translate this: "
                        "%s" % (offline_model.last_error() or exc))
            except TranslationError:
                raise
            except Exception:
                pass
            # Not the tally of what was tried. With one backend that tally
            # reads "Tried 1 — offline: not installed", which is true,
            # internal, and lands in front of somebody who has just
            # installed a Windows language pack called Chinese and cannot
            # see why Chinese will not translate. Those are two different
            # downloads that happen to share a language name, and the
            # message has to say so.
            raise TranslationError(OFFLINE_ONLY)

    if wanted:
        first = [b for b in BACKENDS if b[0] in wanted]
        first.sort(key=lambda b: wanted.index(b[0]))
        rest = [b for b in backends
                if b[0] not in wanted and b[0] not in LAST_RESORT]
        # Hy-MT2 on this computer is the last thing Automatic asks: for
        # when nothing online answers, not for when one engine is slow.
        local = [b for b in first + rest if b[0] == "hymt"]
        if wanted[0] != "hymt":
            first = [b for b in first if b[0] != "hymt"]
            rest = [b for b in rest if b[0] != "hymt"]
        else:
            local = []
        try:
            from . import offline_model
            if not offline_model.writes(target):
                local = []             # it would write the wrong language
        except Exception:
            pass
        if getattr(_job, "no_hymt", False):
            # Hy-MT2 is already translating this snip beside the online
            # engines; asking it again here would only queue behind that.
            first = [b for b in first if b[0] != "hymt"]
            rest = [b for b in rest if b[0] != "hymt"]
            local = []
        if first:
            return _run_backends(first + rest + local, text, source, target,
                                 protected, glossary)

    try:
        from . import local_engine
        source_code = source
        if source_code in ("auto", "", None):
            source_code = guess_source(text)
        if source_code and local_engine.available() \
                and local_engine.has_pair(source_code, target):
            # A local model can do this pair, so do not spend timeouts on
            # remote services that may be rate-limited.
            backends = [b for b in BACKENDS if b[0] == "offline"]
    except Exception:
        pass

    # The plainest services only when asked for by name. See LAST_RESORT.
    trimmed = [b for b in backends if b[0] not in LAST_RESORT]
    if trimmed:
        backends = trimmed
    return _run_backends(backends, text, source, target, protected, glossary)


# How long Gemini has to answer before Google's answer is used instead.
#
# Gemini is tried first when there is a key, because it is the better
# translator. But it can take many seconds, and waiting for it and then
# starting Google from cold added the two together: a snip could take ten
# seconds and still end with the plainest engine of all. So Google is asked
# at the same moment, in the background. Gemini gets this long to answer;
# after that, whichever answer is in hand is used.
GEMINI_HEAD_START = 3.0

# Services used only when they are asked for by name. Their wording is the
# plainest, and one of them turned a Chinese headline into "without juice".
# A clear "could not translate" is better than that, and much better than a
# wrong answer the reader cannot tell is wrong.
LAST_RESORT = ("simplytranslate", "lingva", "mymemory")


class _Rejected(Exception):
    pass


# Google's answer from a race Gemini won, kept briefly. When Gemini's
# answer then turns out unusable for the caller — it merged two lines of a
# snip into one — the caller asks again without Gemini, and Google has
# already answered that exact question.
_hedged = {}
_HEDGE_KEEP = 30.0


def _attempt(name, backend, text, source, target, many):
    """One backend, with the same checks the chain applies. Raises
    `_Rejected` with the reason if the answer cannot be used."""
    now = time.monotonic()
    resting = _cooldown.get(name)
    if resting and resting[0] > now and many:
        raise _Rejected("%s: rested after %s" % (name, resting[1]))
    try:
        result = backend(text, source, target)
    except Exception as exc:
        reason = _describe(exc)
        if name.startswith("google-api"):
            _note_google(reason)
        # A 400 is about this request - its length, its language pair -
        # not about the service. Resting the service for it turned one bad
        # request into a minute of every snip failing with "rested".
        if not reason.startswith("HTTP 400"):
            rest = (COOLDOWN_RATE_LIMITED
                    if ("429" in reason or "quota" in reason.lower())
                    else COOLDOWN)
            _cooldown[name] = (now + rest, reason)
        raise _Rejected("%s: %s" % (name, reason))
    if not isinstance(result, str):
        result = str(result or "")
    if _is_broken(result, text):
        raise _Rejected("%s: returned an error page" % name)
    if looks_untranslated(text, result, target):
        _cooldown[name] = (now + COOLDOWN, "returned the text unchanged")
        raise _Rejected("%s: handed the text back untranslated" % name)
    _cooldown.pop(name, None)
    if name.startswith("google-api"):
        _note_google(None)
    return result


def _note_google(reason):
    """Tell google_billing how a Google request went: a refusal naming
    billing becomes a notice with the page that fixes it."""
    try:
        from . import google_billing
        if reason is None:
            google_billing.note_working()
        else:
            google_billing.note_refusal(reason)
    except Exception:
        pass


def _race_gemini(backends, text, source, target):
    """Gemini first, with Google already asked in the background.

    Returns `(name, result)`, or raises `_Rejected` with every reason.
    Gemini's answer is used if it arrives within GEMINI_HEAD_START, or if
    it is the first usable answer after that; otherwise the rest of the
    chain's.
    """
    import concurrent.futures as futures
    gemini, rest = backends[0], backends[1:]

    def run_rest():
        errors = []
        for name, backend in rest:
            try:
                return name, _attempt(name, backend, text, source, target,
                                      True)
            except _Rejected as exc:
                errors.append(str(exc))
        raise _Rejected("; ".join(errors) or "nothing else to try")

    pool = futures.ThreadPoolExecutor(max_workers=2,
                                      thread_name_prefix="translate")
    try:
        first = pool.submit(lambda: (gemini[0], _attempt(
            gemini[0], gemini[1], text, source, target, True)))
        second = pool.submit(run_rest)

        def keep(future, key=(text, source, target)):
            try:
                _hedged[key] = (time.monotonic(), future.result())
            except Exception:
                pass
        errors = []
        try:
            won = first.result(timeout=GEMINI_HEAD_START)
            second.add_done_callback(keep)
            return won
        except futures.TimeoutError:
            pass
        except _Rejected as exc:
            errors.append(str(exc))
        # Gemini has had its head start. Whatever it has not said yet, it
        # can still say — but so can Google, and the first to answer wins.
        pending = {second}
        if not first.done():
            pending.add(first)
        while pending:
            done, pending = futures.wait(pending,
                                         return_when=futures.FIRST_COMPLETED)
            for future in done:
                try:
                    won = future.result()
                    if future is first:
                        second.add_done_callback(keep)
                    return won
                except _Rejected as exc:
                    errors.append(str(exc))
        raise _Rejected("; ".join(errors))
    finally:
        pool.shutdown(wait=False)


def _run_backends(backends, text, source, target, protected, glossary):
    """Try each backend in turn; the first believable answer wins."""
    errors = []
    result = None
    if len(backends) > 1 and backends[0][0] == "gemini" \
            and _api_key("gemini_api_key"):
        try:
            name, result = _race_gemini(backends, text, source, target)
        except _Rejected as exc:
            errors.append(str(exc))
            backends = ()
    for candidate, backend in backends if result is None else ():
        try:
            result = _attempt(candidate, backend, text, source, target,
                              len(backends) > 1)
            name = candidate
            break
        except _Rejected as exc:
            errors.append(str(exc))
    if result is None and backends and errors \
            and any(": rested after " in e for e in errors):
        # Everything was resting, so nothing was actually asked. Resting
        # saves timeouts on a service that is down; it must not become a
        # snip that fails without trying anything. Ask once anyway.
        tried = [e for e in errors if ": rested after " not in e]
        errors = list(tried)
        for candidate, backend in backends:
            if any(e.startswith(candidate + ":") for e in tried):
                continue                    # already asked just now
            try:
                result = _attempt(candidate, backend, text, source, target,
                                  False)
                name = candidate
                break
            except _Rejected as exc:
                errors.append(str(exc))
    if result is not None:
        _remember(name)
        if protected:
            try:
                result = glossary.restore(result, protected)
            except Exception:
                pass
        if str(target or "").lower().startswith("ko"):
            result = korean_particles(result)
        return result
    raise TranslationError(
        "No translation service could be reached. Tried %d — %s"
        % (len(errors), "; ".join(errors)))


# A Korean particle is part of the word before it and is never written as
# a word of its own. Only particles that cannot also be words are listed:
# 이 is also "this" and 도 is also "degree", so neither is touched.
_KO_PARTICLE = re.compile(
    r"(?<=[A-Za-z0-9)\]%])[ \t]+"
    r"(은|는|을|를|의|에서|에게|에|으로|로|와|과|까지|부터|보다|처럼)"
    r"(?=[\s.,!?;:)\]」』\"'…]|$)")


def korean_particles(text):
    """Join a Korean particle back onto the code or number in front of it.

    "N90 는" should be "N90는": a particle belongs to the word before it,
    and a reader of Korean sees the space as a mistake immediately — the
    kind that makes a whole translation look machine-made. Engines put it
    there after anything written in Latin letters or digits, a model code
    or a figure, because the tokens on either side of that seam come from
    different alphabets.

    Only the space goes. Which particle is right — 은 or 는 — depends on
    how the code is read aloud, and N90 is 엔구십 to one reader and
    엔나인티 to another; that is not a thing to guess at.
    """
    try:
        return _KO_PARTICLE.sub(lambda m: m.group(1), str(text))
    except Exception:
        return text


# -- chunking ----------------------------------------------------------
def _hard_split(text, limit):
    if len(text) <= limit:
        return [text]
    out, rest = [], text
    while len(rest) > limit:
        cut = rest.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        out.append(rest[:cut])
        rest = rest[cut:].lstrip()
    if rest:
        out.append(rest)
    return out


def split_chunks(text, limit=MAX_CHUNK):
    """Split on paragraph, then sentence, then hard-wrap. Never mid-word."""
    if len(text) <= limit:
        return [text]
    chunks, current = [], ""
    for para in text.split("\n\n"):
        piece = para if not current else "\n\n" + para
        if len(current) + len(piece) <= limit:
            current += piece
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(para) <= limit:
            current = para
            continue
        for sentence in re.split(r"(?<=[.!?。！？؟۔])\s+", para):
            piece = sentence if not current else " " + sentence
            if len(current) + len(piece) <= limit:
                current += piece
            else:
                if current:
                    chunks.append(current)
                    current = ""
                for part in _hard_split(sentence, limit):
                    chunks.append(part)
                current = chunks.pop() if chunks else ""
    if current:
        chunks.append(current)
    return [c for c in chunks if c.strip()]


def memory_tag():
    """What a remembered translation depends on besides its text: the
    engine choice and whether this is background work. A translation kept
    under one engine is never handed out under another."""
    try:
        from . import profile
        chosen = profile.current()
    except Exception:
        chosen = ""
    return (chosen, _background())


def _cache_get(key):
    with _cache_lock:
        return _cache.get((memory_tag(), key))


def _cache_put(key, value):
    with _cache_lock:
        if len(_cache) >= _CACHE_LIMIT:
            _cache.clear()
        _cache[(memory_tag(), key)] = value


def forget():
    """Drop every remembered translation - when a setting that changes
    translations changes."""
    with _cache_lock:
        _cache.clear()
    with _blocks_lock:
        _blocks.clear()


def translate(text, target="en", source="auto", progress=None,
              job=None, avoid=()):
    """Translate text, chunking as needed. progress(done, total) is optional."""
    _check_stop()
    text = (text or "").strip()
    if not text:
        return ""

    key = (source, target, text, tuple(avoid))
    cached = _cache_get(key)
    if cached is not None:
        return cached

    chunks = split_chunks(text)
    out = []
    for i, chunk in enumerate(chunks):
        out.append(_translate_once(chunk, source, target, job, avoid))
        if progress:
            try:
                progress(i + 1, len(chunks))
            except Exception:
                pass

    joined = "\n\n".join(out) if len(out) > 1 else (out[0] if out else "")
    _cache_put(key, joined)
    return joined


LINE_SEP = "\n"


def _expensive_first(job):
    """Whether the engine about to be asked charges per request.

    Only worth knowing in one place — the per-line fallback below, which
    is cheap against a lookup and ruinous against a language model.
    """
    try:
        from . import profile
        order, _fallback = profile.translating(job)
    except Exception:
        return False
    return bool(order) and order[0] in EXPENSIVE


def _after_llm_miscount():
    """What to leave out when Gemini's answer had the wrong number of lines.

    Both language models used to be left out, and with no Google key the
    snip went to whatever was left — the free services when they were not
    resting, Hy-MT2 on this computer when they were: ten seconds for a
    snip Groq answers in one. Groq is asked instead when it has a key; its
    allowance is per minute and generous."""
    if _api_key("groq_api_key"):
        return ("gemini",)
    return EXPENSIVE


# How many lines of one snip may be asked again on their own. Each is a
# request, and against a language model a request is allowance.
RETRY_LEFT_BEHIND = 4


def _left_behind(line, answer, target):
    """A line the engine handed back in its own language, or dropped.

    A language model given a headline and a paragraph together translated
    the headline and returned the paragraph word for word — the same
    paragraph snipped alone came back in English. Same script both sides
    (German to English), so `looks_untranslated` cannot see it: it only
    catches Chinese over Chinese.
    """
    text = line.strip()
    if not text:
        return False
    same = " ".join(answer.split()).lower() == " ".join(text.split()).lower()
    if answer.strip() and not same:
        # Nearly the same is the same: a model that "translates" a German
        # line into German changes a hyphen or a space ("CNC gefräste" /
        # "CNC-gefräste"), and the line was drawn over the page in German
        # as if it were the translation.
        import difflib
        near = difflib.SequenceMatcher(
            None, " ".join(answer.split()).lower(),
            " ".join(text.split()).lower()).ratio()
        if near < 0.85:
            return False
    words = re.findall(r"[^\W\d_]{2,}", text)
    if len(words) < 3:
        return False                       # a name, a code, a heading word
    language = (detect_language(text) or "").split("-")[0].lower()
    wanted = str(target or "").split("-")[0].lower()
    if not language:
        # No detector to ask. A sentence of three words or more coming
        # back identical from an engine told to translate it has, far more
        # often than not, not been translated.
        return True
    return language != wanted


def _retry_left_behind(lines, parts, target, source, job):
    """Ask again for lines that came back untranslated - side by side.

    They were asked one after the other, each a full round trip: four of
    them added two to four seconds to a snip, and which pages had them
    decided which snips were slow."""
    behind = [i for i, (line, part) in enumerate(zip(lines, parts))
              if _left_behind(line, part, target)][:RETRY_LEFT_BEHIND]
    if not behind:
        return parts
    started = time.time()

    def ask(index):
        try:
            return index, translate(lines[index].strip(), target=target,
                                    source=source, job=job)
        except Exception:
            return index, None
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=len(behind)) as pool:
        answers = list(pool.map(ask, behind))
    for index, again in answers:
        if again and again.strip() and not _left_behind(
                lines[index], again, target):
            parts[index] = again.strip()
    _note_timing("asked again for %d lines left untranslated: %.0fms"
                 % (len(behind), 1000 * (time.time() - started)))
    return parts


def _hymt_lines(lines, target, job, whole=False):
    """A snip under "On this computer only", when Hy-MT2 is ready: its lines
    in small groups side by side (offline_model.translate_lines), instead of
    one long request that a small model often answers with the wrong
    number of lines, followed by every line again one after the other.
    None when this is not the route, or when it failed and the old one
    should have its turn."""
    try:
        from . import offline_model, profile
        order, may_fall_back = profile.translating(job)
        if not order or order[0] != "hymt" or not offline_model.ready():
            return None
        key = ("lines", target, tuple(lines), whole)
        cached = _cache_get(key)
        if cached is not None:
            return list(cached)
        out = offline_model.translate_lines(
            lines, target,
            left_behind=lambda line, answer: _left_behind(line, answer,
                                                          target),
            cancel=_stop(), whole=whole, progress=_progress(),
            context=_context())
    except Exception:
        _check_stop()
        return None
    _check_stop()
    _remember("hymt")
    _cache_put(key, tuple(out))
    return out


# Automatic with the offline engine set up: one engine per page, chosen
# before anything is sent (see _hymt_with_help and ONLINE_ABOVE). The two
# below are kept for callers that still name them.
HELP_AFTER = 1.5
HELP_FROM = 2.0
# A laptop without a graphics chip the engine can use (most Windows laptops
# with an i5) writes a few items a second: a page this full takes it well
# past HELP_FROM even before its speed is known, so help is asked at once.
DENSE_ITEMS = 30
HELPERS = ("groq_api_key", "gemini_api_key")
_hymt_speed = {"per_item": None,      # seconds per item, recent snips
               "per_char": None}      # seconds per character, the same
# The offline model translates a page unless its recent speed says it would
# take longer than this; then an online engine does (_hymt_with_help).
ONLINE_ABOVE = 3.0
# How long an online engine chosen for speed is waited for.
ONLINE_WAIT = 3.0
# The fewest characters a page translated offline must have to count
# towards its speed.
SPEED_FROM_CHARS = 150


_speed_seen = []


def _learn_speed(rate):
    """The offline model's speed from its last few pages: the middle of
    the last five, or the faster of two. One slow page - 12 s for a page
    the model does in under one, the graphics chip busy or waking up -
    sent every page after it online, where each waited for an engine
    that did not answer."""
    _speed_seen.append(rate)
    del _speed_seen[:-5]
    seen = sorted(_speed_seen)
    _hymt_speed["per_char"] = seen[len(seen) // 2] if len(seen) >= 3 \
        else seen[0]


def _fast_online_ready():
    """Groq, set up and not resting."""
    if not _api_key("groq_api_key"):
        return False
    resting = _cooldown.get("groq")
    return not (resting and resting[0] > time.monotonic())


def _helpers_ready():
    names = {"groq_api_key": "groq", "gemini_api_key": "gemini"}
    now = time.monotonic()
    for setting in HELPERS:
        if not _api_key(setting):
            continue
        resting = _cooldown.get(names[setting])
        if resting and resting[0] > now:
            continue                   # out of quota for now
        return True
    return False


def _hymt_with_help(lines, target, source, job, whole=False):
    """The page through Hy-MT2, with Groq/Gemini asked too when it is slow.
    None when this is not the route (then the older routes decide)."""
    try:
        from . import offline_model, profile
        if profile.current() != profile.AUTO:
            return None
        order, _fallback = profile.translating(job)
        if not order or order[0] != "hymt" or not offline_model.ready():
            return None
        if not _helpers_ready():
            return None                # _hymt_lines, then the fallbacks
    except Exception:
        return None
    import concurrent.futures as futures
    wanted = sum(1 for ln in lines if ln.strip())
    key = ("lines", target, tuple(lines), whole)
    cached = _cache_get(key)
    if cached is not None:
        return list(cached)
    started = time.monotonic()
    stop = _stop()
    cancel = _Either(stop)
    pool = futures.ThreadPoolExecutor(max_workers=2,
                                      thread_name_prefix="hymt-help")

    told, context = _progress(), _context()

    def offline():
        return offline_model.translate_lines(
            lines, target,
            left_behind=lambda line, answer: _left_behind(line, answer,
                                                          target),
            cancel=cancel, whole=whole, progress=told, context=context)

    online_quit = _Either(stop)
    carried = {k: getattr(_job, k, None) for k in ("value", "background")}

    def online():
        # Not told item by item: the page shows the offline engine's
        # answers as they come, and this one replaces them whole if it
        # wins - one engine's translation, never a mix.
        for name, value in carried.items():
            setattr(_job, name, value)
        _job.no_hymt = True
        _job.stop = online_quit
        try:
            return _online_lines(lines, target, source, job)
        finally:
            _job.no_hymt = False
            _job.stop = None

    # One engine per page, chosen before anything is sent. The two used to
    # race - the offline model, and an online engine asked as well once it
    # was slow - and whichever finished first was shown. The same page then
    # came back from a different engine from one snip to the next, at a
    # different speed, with that engine's mistakes. Now: the offline model,
    # unless its own recent speed says this page will take it past the
    # three seconds a snip may take (app/budget.py), when an online engine
    # translates it instead. Either one failing hands the page to the other.
    chars = sum(len(ln) for ln in lines if ln.strip())
    rate = _hymt_speed.get("per_char")
    expected = rate * chars if rate else None
    if expected is None and wanted >= DENSE_ITEMS and \
            not offline_model.on_graphics_chip():
        expected = ONLINE_ABOVE + 1.0      # a slow processor, a full page
    # Only an engine that is fast is chosen for speed: Groq answers a page
    # in under a second; Gemini took six to eight, slower than the offline
    # model it was chosen to save time over.
    online_first = expected is not None and expected > ONLINE_ABOVE and \
        _fast_online_ready()
    try:
        out, used = None, None
        if online_first:
            # Chosen to be quicker, so given only the time it was chosen
            # to save: an online engine that has not answered by then is
            # left, and the offline model translates the page. Waited for
            # to the end, a failing engine tried line by line took 54 s
            # and 105 s for pages the offline model then did in under two.
            asked = pool.submit(online)
            try:
                out = asked.result(timeout=ONLINE_WAIT)
                used = "online"
            except futures.TimeoutError:
                online_quit.set()
                out = None
                _note_timing("online engine not back in %.0f s - "
                             "translated on this computer" % ONLINE_WAIT)
            except Exception:
                out = None
            if stop is not None and stop.is_set():
                raise Cancelled("cancelled")
        if out is None:
            try:
                out = pool.submit(offline).result(timeout=HYMT_WAIT)
                used = "offline"
            except Cancelled:
                raise
            except Exception:
                out = None
            if stop is not None and stop.is_set():
                raise Cancelled("cancelled")
        if out is None and not online_first:
            out = online()
            used = "online"
        if out is None:
            raise TranslationError("no engine answered")
    except (Cancelled, TranslationError):
        cancel.set()
        _check_stop()
        return None
    except Exception:
        cancel.set()
        _check_stop()
        return None
    finally:
        pool.shutdown(wait=False)
    _check_stop()
    took = time.monotonic() - started
    from . import config
    if used == "offline":
        # Learned from the translating alone, never the model starting up
        # (6.6 s once per start, which made a five-letter warm-up look like
        # a second a letter and sent every page online from then on), and
        # only from pages long enough to say anything.
        work = (getattr(offline_model, "last_run", {}) or {}).get("work")
        if chars >= SPEED_FROM_CHARS and work:
            _learn_speed(work / chars)
        if wanted:
            _hymt_speed["per_item"] = took / wanted
        _remember("hymt")
        _cache_put(key, tuple(out))
        _note_timing("offline on %d items (%d characters): %.0fms"
                     % (wanted, chars, 1000 * took))
    else:
        _note_timing("%s chosen for %d items (%d characters, offline "
                     "expected %s): %.0fms"
                     % (config.CONFIG.get("last_backend", "") or "online",
                        wanted, chars,
                        "%.1fs" % expected if expected else "?",
                        1000 * took))
    return out


def _local_lines(lines, target, source, job):
    """Line by line, on this computer only; an error rather than Google."""
    out, done, last = [], False, None
    for line in lines:
        if not line.strip():
            out.append("")
            continue
        try:
            out.append(translate(line, target=target, source=source,
                                 job=job))
            done = True
        except Exception as exc:
            last = exc
            out.append("")
    if not done:
        raise TranslationError(str(last) if last else OFFLINE_ONLY)
    return out


# Paragraphs and cells translated in the last few minutes, each on its own
# (blocks=True). Not a memory of words or phrases: a whole paragraph, the
# same text, translated the same way it would be again - kept so that
# snipping round the same text again, or a snip after the page was prepared
# ahead, does not wait for it twice. Short-lived on purpose.
BLOCK_KEEP = 600.0
BLOCK_MAX = 4000
_blocks = {}
_blocks_lock = threading.Lock()


# Only whole sentences are reused. A short label ("Bank", a two-character
# Chinese label) can mean something else on the next page; a sentence
# carries its own meaning.
BLOCK_MIN_WORDS = 6
BLOCK_MIN_CJK = 15
_CJK = re.compile(u"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\uf900-\ufaff]")


def _reusable(text):
    return len(text.split()) >= BLOCK_MIN_WORDS or \
        len(_CJK.findall(text)) >= BLOCK_MIN_CJK


def _lead_engine(job=None):
    """The engine expected to translate this page: kept answers are used
    only if that engine gave them, so a page stays one engine's work."""
    if _background():
        return "hymt"
    try:
        from . import profile
        order, _fallback = profile.translating(job)
        return order[0] if order else ""
    except Exception:
        return ""


def _block_get(target, text, engine=None):
    with _blocks_lock:
        hit = _blocks.get((target, text))
        if hit is None:
            return None
        if time.monotonic() - hit[0] > BLOCK_KEEP:
            _blocks.pop((target, text), None)
            return None
        if engine is not None and hit[2] != engine:
            return None
        return hit[1]


def _block_put(target, pairs, engine=""):
    now = time.monotonic()
    with _blocks_lock:
        for text, answer in pairs:
            if text.strip() and str(answer or "").strip() and \
                    _reusable(text):
                _blocks[(target, text)] = (now, answer, engine)
        if len(_blocks) > BLOCK_MAX:
            for key in sorted(_blocks, key=lambda k: _blocks[k][0])[
                    :len(_blocks) - BLOCK_MAX]:
                _blocks.pop(key, None)


# Items that need no translation: they are the same in every language, and
# sending them costs time and invites the engine to "translate" them -
# a price reformatted, a code respelled.
_UNITS = set("""mg g kg t ml l cl dl km m cm mm µm nm w kw mw kwh wh v a mah
    mb gb tb kb hz khz mhz ghz db dba mmhg bar psi ppm °c °f °
    h min s ms sec x px pt dpi fps k m² m³ m³/h km/h l/100km""".split())
_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
_URL = re.compile(r"^(https?://|www\.)\S+$", re.I)
_CODE = re.compile(r"^[A-Z0-9][A-Z0-9._/#:+-]*$")


def needs_no_translation(text):
    """True for a number, price, date, time, measurement, code, email or
    web address: text that reads the same in any language."""
    text = str(text or "").strip()
    if not text:
        return True
    if not any(c.isalpha() for c in text):
        return True                   # numbers, prices, dates, times
    if _EMAIL.match(text) or _URL.match(text):
        return True
    tokens = text.replace(",", " ").split()
    has_digit = any(c.isdigit() for c in text)
    for token in tokens:
        bare = token.strip("()[]{}.;:!?\"'")
        if not bare or not any(c.isalpha() for c in bare):
            continue
        if has_digit and bare.lower() in _UNITS:
            continue                  # 500 mg, 38 W, 15 h - with a number
        if has_digit and _CODE.match(bare) and any(c.isdigit() for c in bare):
            continue                  # E-104, XC60, NR-48213, DE12
        if bare in ("€", "$", "£", "¥", "₩", "%"):
            continue
        return False
    return True


def set_progress(fn):
    """`fn(index, text)` is told each item of a blocks translation as it
    is done, on this thread's calls from now on. None clears it."""
    _job.progress = fn


def _progress():
    return getattr(_job, "progress", None)


def _context():
    return getattr(_job, "context", None)


def translate_lines(lines, target="en", source="auto", job=None,
                    blocks=False, progress=None):
    """See _translate_lines. With `blocks` (each item a paragraph or a cell
    of one page):

    - numbers, prices, codes and the like are kept as they are;
    - an item that appears several times is translated once;
    - paragraphs translated in the last few minutes are taken as they were;
    - `progress(index, text)` hears each item as soon as it is done, so the
      page can be shown as it fills in;
    - short items are sent with the items beside them as context.
    """
    lines = [ln or "" for ln in lines]
    if not blocks:
        return _translate_lines(lines, target, source, job, blocks)
    _check_stop()
    out = [""] * len(lines)

    def tell(index, text):
        if progress is not None:
            try:
                progress(index, text)
            except Exception:
                pass
    engine = _lead_engine(job)
    todo = {}                         # text -> indexes that have it
    kept = reused = 0
    # Text already in the language asked for is left as it is: a model
    # asked to translate German into German rewrites it (see langid).
    try:
        from . import langid
        home_page = langid.page_in_language(
            [ln.strip() for ln in lines if ln.strip()], target)
    except Exception:
        langid, home_page = None, False

    def at_home(text):
        if langid is None:
            return False
        try:
            verdict = langid.in_language(text, target)
            if verdict is None:
                return home_page and langid.same_script(text, target)
            return verdict
        except Exception:
            return False
    for i, line in enumerate(lines):
        text = line.strip()
        if not text:
            continue
        if needs_no_translation(text) or at_home(text):
            out[i] = text
            kept += 1
            tell(i, text)
            continue
        known = _block_get(target, text, engine) if _reusable(text) else None
        if known is not None:
            out[i] = known
            reused += 1
            tell(i, known)
            continue
        todo.setdefault(text, []).append(i)
    sent = list(todo)
    total = sum(1 for ln in lines if ln.strip())
    repeats = sum(len(v) for v in todo.values()) - len(sent)
    if kept or reused or repeats:
        _note_timing("%d items: %d kept as they are, %d already translated, "
                     "%d repeats, %d sent" % (total, kept, reused, repeats,
                                               len(sent)))
    if not sent:
        return out
    # No context for short items. The items beside a label depend on how
    # much of the page was taken, so with them a snip and hold-to-see of
    # the same page translated the same label differently (11 labels in
    # 50 on seven test pages: "Summary" and "Overview", "town" and
    # "city"). The same label now gets the same answer wherever it is.
    context = {}

    def sub_progress(index, text):
        for i in todo[sent[index]]:
            out[i] = text
            tell(i, text)
    before = (_progress(), _context())
    _job.progress, _job.context = sub_progress, context
    try:
        got = _translate_lines(sent, target, source, job, blocks)
    finally:
        _job.progress, _job.context = before
    for text, answer in zip(sent, got):
        for i in todo[text]:
            out[i] = answer
    try:
        from . import config
        answered = str(config.CONFIG.get("last_backend", "") or "")
    except Exception:
        answered = ""
    if _background():
        answered = "hymt"
    _block_put(target, [(t, a) for t, a in zip(sent, got)], answered)
    return out


def _background_lines(lines, target, whole):
    from . import offline_model
    if not offline_model.ready():
        raise Cancelled("the offline engine is not ready")
    out = offline_model.translate_lines(
        lines, target,
        left_behind=lambda line, answer: _left_behind(line, answer, target),
        cancel=_stop(), workers=3, whole=whole, progress=_progress(),
        context=_context())
    _check_stop()
    return out


def _translate_lines(lines, target="en", source="auto", job=None,
                     blocks=False):
    """Translate many short lines in ONE request.

    A request per line would be the obvious approach and is unusably slow —
    each one pays a fresh round trip. Joining with newlines costs a single
    request; if the service does not give back the same number of lines, the
    result is unusable for positioning, so it falls back to translating
    individually rather than mismatching text to boxes.
    """
    lines = [ln or "" for ln in lines]
    if not any(ln.strip() for ln in lines):
        return list(lines)
    _check_stop()
    if _background():
        return _background_lines(lines, target, blocks)

    # `blocks`: the items are paragraphs and cells already (overlay's
    # translate_grouped), to be translated each on its own.
    helped = _hymt_with_help(lines, target, source, job, whole=blocks)
    if helped is not None:
        return helped
    local = _hymt_lines(lines, target, job, whole=blocks)
    if local is not None:
        return local

    beside = _hymt_beside(lines, target, job, whole=blocks)
    if beside is None:
        return _online_lines(lines, target, source, job)
    future, cancel = beside
    _job.no_hymt = True
    try:
        out = _online_lines(lines, target, source, job)
    except Exception:
        # Online could not do it; Hy-MT2 has been at it since the start.
        try:
            out = future.result(timeout=HYMT_WAIT)
        except Exception:
            cancel.set()
            raise
        _remember("hymt")
        _note_beside("used")
        return out
    finally:
        _job.no_hymt = False
    # Online answered. Lines it left empty are filled from Hy-MT2 if it
    # has them within a moment; otherwise it is stopped.
    missing = [i for i, line in enumerate(lines)
               if line.strip() and not str(out[i] or "").strip()]
    if missing:
        out = list(out)
        local = None
        if future.done():
            try:
                local = future.result(timeout=0)
            except Exception:
                local = None
        if local is not None:
            for i in missing:
                if local[i]:
                    out[i] = local[i]
            _note_beside("filled %d lines" % len(missing))
            cancel.set()
            return out
        # The whole page beside is not finished. Waiting for it cost a
        # dense page 6 seconds for a single empty line (a model code), so
        # it is stopped and only the missing lines are asked for, briefly.
        cancel.set()
        started = time.time()
        try:
            filled = _hymt_few([lines[i] for i in missing], target, blocks)
            for i, text in zip(missing, filled or []):
                if text:
                    out[i] = text
            _note_beside("filled %d lines in %.0fms"
                         % (len(missing), 1000 * (time.time() - started)))
        except Exception:
            pass
        return out
    cancel.set()
    return out


def _hymt_few(lines, target, whole):
    """A handful of lines through Hy-MT2, given up after HYMT_FILL_WAIT."""
    import concurrent.futures as futures
    from . import offline_model
    stop = threading.Event()
    pool = futures.ThreadPoolExecutor(max_workers=1,
                                      thread_name_prefix="hymt-fill")
    future = pool.submit(offline_model.translate_lines, lines, target,
                         None, stop, None, whole)
    pool.shutdown(wait=False)
    try:
        return future.result(timeout=HYMT_FILL_WAIT)
    except Exception:
        stop.set()
        return None


# How long a snip waits for Hy-MT2 once the online engines have failed,
# and how long for the few lines they left out.
HYMT_WAIT = 60
HYMT_FILL_WAIT = 2.5


def translate_best(text, target="en", source="auto", job=None):
    """Typed or copied text, the way a snip is done: online first and
    shown, Hy-MT2 on this computer translating the same text alongside
    under Automatic with a key, and used if the online answer does not
    come. With no key it leads anyway (profile.translating)."""
    text = (text or "").strip()
    if not text:
        return ""
    lines = text.split("\n")
    beside = _hymt_beside(lines, target, job)
    if beside is None:
        return translate(text, target=target, source=source, job=job)
    future, cancel = beside
    _job.no_hymt = True
    try:
        return translate(text, target=target, source=source, job=job)
    except Exception as online_error:
        try:
            out = future.result(timeout=HYMT_WAIT)
        except Exception:
            raise online_error
        _remember("hymt")
        _note_beside("used for text")
        return "\n".join(out)
    finally:
        _job.no_hymt = False
        cancel.set()


def _hymt_beside(lines, target, job, whole=False):
    """Start Hy-MT2 on this snip in the background, under Automatic with a
    key: online answers first, and if it cannot, the local translation is
    already under way instead of starting from nothing. (future, cancel),
    or None when this is not the case."""
    try:
        from . import offline_model, profile
        if profile.current() != profile.AUTO or not offline_model.ready() \
                or not profile._has_any_key() \
                or not offline_model.writes(target):
            return None
        order, _fallback = profile.translating(job)
        if order and order[0] == "hymt":
            return None      # it leads; nothing to run beside
    except Exception:
        return None
    import concurrent.futures as futures
    cancel = threading.Event()
    pool = futures.ThreadPoolExecutor(max_workers=1,
                                      thread_name_prefix="hymt-beside")
    # Three at a time, as before 1.48.34: this is a fallback running
    # beside an online engine,
    # and it has to stop when the online answer comes. See
    # offline_model.translate_lines.
    future = pool.submit(
        offline_model.translate_lines, lines, target,
        lambda line, answer: _left_behind(line, answer, target), cancel, 3,
        whole)
    pool.shutdown(wait=False)
    return future, cancel


def _note_beside(what):
    try:
        from .main import log
        log("hymt beside online: %s" % what)
    except Exception:
        pass


def _note_timing(what):
    try:
        from .main import log
        log("translate  : %s" % what)
    except Exception:
        pass


# A dense page to an online engine goes as several requests at once rather
# than one long one: a language model writes its answer word by word, so
# four answers of 50 items arrive in about the time of one - not of one of
# 200. Kept to a few at a time for the free allowances (Groq: 30 requests a
# minute).
CHUNK_ITEMS = 40
CHUNK_CHARS = 1500
CHUNKS_AT_ONCE = 4


def _chunks_of(lines):
    chunks, current, size = [], [], 0
    for i, line in enumerate(lines):
        length = len(line.strip()) + 1
        if current and (len(current) >= CHUNK_ITEMS
                        or size + length > CHUNK_CHARS):
            chunks.append(current)
            current, size = [], 0
        current.append(i)
        size += length
    if current:
        chunks.append(current)
    return chunks


def _online_lines(lines, target, source, job):
    """Many items to the online engines: in chunks side by side when there
    are many, each chunk's answers told (progress) as it lands."""
    told = _progress()
    chunks = _chunks_of(lines)
    if len(chunks) <= 1:
        out = _online_lines_one(lines, target, source, job)
        if told is not None:
            for i, text in enumerate(out):
                try:
                    told(i, text)
                except Exception:
                    pass
        return out
    from concurrent.futures import ThreadPoolExecutor
    state = {k: getattr(_job, k, None)
             for k in ("value", "no_hymt", "stop", "background")}
    out = [""] * len(lines)
    started = time.time()

    def one(indexes):
        for key, value in state.items():
            setattr(_job, key, value)
        _check_stop()
        got = _online_lines_one([lines[i] for i in indexes], target,
                                source, job)
        for i, text in zip(indexes, got):
            out[i] = text
            if told is not None:
                try:
                    told(i, text)
                except Exception:
                    pass
        return True
    errors = []
    with ThreadPoolExecutor(max_workers=CHUNKS_AT_ONCE) as pool:
        for future in [pool.submit(one, c) for c in chunks]:
            try:
                future.result()
            except Exception as exc:
                errors.append(exc)
    if errors and len(errors) == len(chunks):
        raise errors[0]
    _note_timing("%d lines in %d requests side by side: %.0fms"
                 % (len(lines), len(chunks), 1000 * (time.time() - started)))
    return out


def _misaligned(lines, parts):
    """Whether answers came back in the right number but against the wrong
    lines: a language model merged three short items into one line and
    split a long one in two, the count came out even, and every answer
    below that point was drawn over the line above or below its own -
    "- Fulcrum Racing 7 wheels, fully serviced incl. new tires" over one
    item, a half sentence over the next.

    Told by length: an answer is a translation of its own line only if it
    is roughly as long. Two lines far out of proportion (a quarter or four
    times the length) in one batch is a shift, not a terse language."""
    def size(text):
        # A Chinese, Japanese or Korean character says about as much as
        # three Latin letters.
        return sum(3 if 0x3040 <= ord(c) <= 0x9FFF or
                   0xAC00 <= ord(c) <= 0xD7AF else 1
                   for c in str(text or "").strip())
    # Words of another line's original turning up in this answer, two or
    # more in a row, that its own original does not have: a piece of one
    # line carried into another ("…as quickly as possible! OHNE
    # POWERMETER FUNKTION", from three paragraphs up).
    def words(text):
        return [w.lower() for w in re.findall(r"[^\W\d_]{4,}",
                                               str(text or ""))]
    own = [set(words(line)) for line in lines]
    for i, part in enumerate(parts):
        others = set()
        for j, seen in enumerate(own):
            if j != i:
                others |= seen
        run = 0
        for word in words(part):
            if word in others and word not in own[i]:
                run += 1
                if run >= 2:
                    return True
            else:
                run = 0
    odd = 0
    for line, part in zip(lines, parts):
        a, b = size(line), size(part)
        if a < 8 and b < 8:
            continue
        if not a or not b:
            if max(a, b) >= 12:
                odd += 1
            continue
        ratio = b / float(a)
        if ratio > 4.0 or ratio < 0.25:
            odd += 1
    return odd >= (1 if len(lines) <= 3 else 2)


def _online_lines_one(lines, target, source, job):
    joined = LINE_SEP.join(ln.strip() or " " for ln in lines)
    try:
        started = time.time()
        out = translate(joined, target=target, source=source,
                        job=job)
        from . import config as _config
        _note_timing("%d lines in one request: %.0fms via %s"
                     % (len(lines), 1000 * (time.time() - started),
                        _config.CONFIG.get("last_backend", "") or "?"))
        parts = [p.strip() for p in out.split("\n")]
        parts = [p for p in parts if p != ""] if len(parts) != len(lines) \
            else parts
        if len(parts) == len(lines) and _misaligned(lines, parts):
            _note_timing("%d lines came back out of step - asked again"
                         % len(lines))
        elif len(parts) == len(lines):
            # A blank line was sent as a space placeholder to keep the line
            # count aligned; whatever came back for it is not text to draw.
            parts = [p if lines[i].strip() else ""
                     for i, p in enumerate(parts)]
            return _retry_left_behind(lines, parts, target, source, job)
    except Exception:
        # Including TranslationError. The single joined request is an
        # optimisation, not the only route — if it fails, the per-line pass
        # below still has a chance, and only that decides success or failure.
        pass

    # One request per line, and the reason it is now guarded.
    #
    # Against a lookup service this is merely slow. Against Gemini it is
    # twenty separate calls off one snip, and Gemini is the engine most
    # likely to reach here: a language model reflows text, merging two
    # short headlines or splitting a long one, so the line count comes
    # back wrong and this path fires. A day's free allowance went on a
    # handful of screenshots that way, with nothing on screen to say
    # where it had gone.
    #
    # So when the expensive engine is the one that failed to keep its
    # lines straight, the whole batch goes to a different engine in one
    # request instead. A plainer translation of everything beats an
    # excellent translation of the first four lines and a spent
    # allowance.
    if len(lines) > 2 and _expensive_first(job):
        try:
            out = translate(joined, target=target, source=source, job=job,
                            avoid=_after_llm_miscount())
            parts = [p.strip() for p in out.split("\n")]
            parts = [p for p in parts if p != ""] \
                if len(parts) != len(lines) else parts
            if len(parts) == len(lines) and not _misaligned(lines, parts):
                return [p if lines[i].strip() else ""
                        for i, p in enumerate(parts)]
        except Exception:
            pass

    # "On this computer only" means it here too. The two routes below go
    # to whatever else is set up — Google's key, then line by line through
    # the chain — and under that choice a failed local answer was quietly
    # handed to Google instead.
    try:
        from . import profile as _profile
        _wanted, may_fall_back = _profile.translating(job)
    except Exception:
        _wanted, may_fall_back = [], True
    if not may_fall_back:
        return _local_lines(lines, target, source, job)

    # A Google key can take every line as its own item in one request and
    # hands back exactly as many — nothing to split, nothing to miscount.
    # Measured on a snip of 14 lines before this: 14 separate requests.
    if len(lines) > 1 and _api_key("google_api_key"):
        try:
            out = _google_api_lines(lines, source, target)
            _note_google(None)
            return out
        except Exception as exc:
            _note_google(_describe(exc))

    results = []
    translated_any = False
    last_error = None
    # Even one at a time, the expensive engine is kept out of a long list.
    per_line_avoid = EXPENSIVE if len(lines) > 2 else ()
    for line in lines:
        if not line.strip():
            results.append("")
            continue
        try:
            results.append(translate(line, target=target, source=source,
                                     job=job, avoid=per_line_avoid))
            translated_any = True
        except Exception as exc:
            last_error = exc
            # Empty, not the original.
            #
            # Putting the source back looks harmless and is the reason
            # "the snip did nothing" was so hard to pin down. The overlay
            # draws whatever it is given, so a failed line came out as the
            # original text painted over the original text: pixel-perfect,
            # indistinguishable from a line the app chose not to touch,
            # and indistinguishable from success. A page half translated
            # and half not looked like a page the app had finished with.
            # Empty means nothing is drawn there, so the real text shows
            # through and the gap is visible as a gap.
            results.append("")

    # Returning the originals when nothing could be translated is the worst
    # possible outcome: the overlay draws the source text back over itself,
    # so the app looks like it worked and quietly did nothing. If not one
    # line made it through, that is a failure and must be reported.
    if not translated_any:
        raise TranslationError(
            "Nothing could be translated. %s" % (last_error or ""))
    return results


def warm_up(target="en"):
    """Find a working backend before the user needs one.

    The first translation of a session pays DNS, TCP and TLS setup on top of
    the request itself — and, now, possibly a walk down the backend list.
    Doing that at launch takes it off the critical path of the first snip.
    """
    try:
        translate("ok", target=target if target != "en" else "de")
    except Exception:
        pass


def detect_language(text):
    """Best-effort source-language label. Returns a code or ''. Never raises."""
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        return ""
