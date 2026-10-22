"""Translate what is selected, without being asked to copy it first.

The clipboard shortcut used to translate whatever you had already copied,
which meant three actions to read one sentence: select, Ctrl+C, then the
shortcut. Miss the middle one and the app said "copy something first" —
technically correct and completely beside the point. Nobody wants to copy
anything. They want to select a sentence, press one key, read it, and get
on with their day.

So the app does the copying. Press the shortcut with text selected and it
sends Ctrl+C to whatever window is in front, waits for the clipboard to
change, and translates what arrives.

Two things make this harder than it sounds.

The shortcut itself is Ctrl+Alt+C, so at the moment it fires those
modifiers are physically held down. Sending Ctrl+C right then means the
foreground app sees Ctrl+Alt+C again — the very shortcut it did not
handle. So this waits for the keys to come up first.

And the clipboard may already contain something. Comparing before and
after is the only way to know whether the copy actually did anything: a
picture, a locked-down PDF viewer or a window with nothing selected all
leave it untouched, and translating the last thing the user copied an hour
ago would be worse than saying nothing.
"""
import re
import sys
import time
import unicodedata

# Virtual key codes. Only needed on Windows.
VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN = 0x11, 0x12, 0x10, 0x5B, 0x5C
VK_C = 0x43
KEYEVENTF_KEYUP = 0x0002

# How long to wait for the user to let go of the shortcut before sending a
# copy, and then for the application to put something on the clipboard.
#
# Both are give-up times, not waits. The loops below exit the moment the
# modifiers come up and the moment the clipboard changes, so a quick press
# on a responsive window is no slower for these being generous — the only
# thing a longer deadline costs is the failure case, and the failure case
# is what they exist to prevent.
#
# 0.6s was too short for the first and it failed in the worst way it
# could. Hold the shortcut a moment longer than that and the copy goes out
# with Alt still down: the other program receives Ctrl+Alt+C, copies
# nothing, and the clipboard still holds whatever was there before. The
# app then translates *that*, labels it "clipboard" rather than
# "selection" — which is honest, and much too quiet — and hands back a
# fluent translation of a paragraph the user read ten minutes ago. There
# is nothing in the result that looks wrong.
#
# 0.5s was too short for the second for a duller reason: a browser copying
# a large selection out of a heavy page does not always manage it inside
# half a second.
RELEASE_TIMEOUT = 2.0
CLIPBOARD_TIMEOUT = 1.2
POLL = 0.02


def available():
    return sys.platform in ("win32", "darwin")


def permitted():
    """Whether the OS will let this app press keys for the user.

    macOS refuses synthetic keystrokes to any process that has not been
    ticked under Privacy & Security › Accessibility, and it refuses them
    *silently* — CGEventPost returns no error, the keystroke simply never
    arrives. Everything downstream then behaves as though the user had
    selected nothing, which is indistinguishable from the truth and leads
    to the worst possible outcome: falling back to whatever was on the
    clipboard from earlier and presenting it as the selection.

    Asking first is the only way to tell those two apart.

    This goes through ctypes rather than pyobjc on purpose. AXIsProcessTrusted
    lives in the ApplicationServices framework, and pyobjc ships that as a
    separate package from the Quartz one Squint installs — so
    `from ApplicationServices import ...` raises ImportError on the very Macs
    this is meant to help, and an exception here means "assume permission",
    which would leave the check doing nothing at all. The framework itself is
    part of macOS and is always there.
    """
    if sys.platform != "darwin":
        return True
    try:
        import ctypes
        import ctypes.util
        path = ctypes.util.find_library("ApplicationServices")
        lib = ctypes.cdll.LoadLibrary(path or
                                      "/System/Library/Frameworks/"
                                      "ApplicationServices.framework/"
                                      "ApplicationServices")
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        lib.AXIsProcessTrusted.argtypes = []
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        pass
    try:
        from ApplicationServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except Exception:
        # Cannot tell. Assume yes and let the before/after clipboard
        # comparison catch a failure — better than refusing to try on a Mac
        # where it would have worked. The label stays honest either way.
        return True


def request_permission():
    """Ask macOS to put up its own Accessibility prompt.

    This matters more than it looks. Without it the instruction is "open
    Accessibility and switch on the entry for Squint" — and there is no
    entry, because macOS only lists an app once it has asked. The user is
    left pressing + and hunting for a Python binary inside a .venv, which
    is not a reasonable thing to ask of anyone.

    AXIsProcessTrustedWithOptions with the prompt option adds the entry and
    shows the system dialog with a button that opens the right pane. It
    returns immediately with the *current* state, which is False — the
    dialog is not modal and the answer comes later, after a restart. So the
    return value says whether permission was already there, never whether
    the user granted it just now.
    """
    if sys.platform != "darwin":
        return True
    try:
        import ctypes
        import ctypes.util
        from ctypes import byref, c_bool, c_long, c_void_p, POINTER

        app_services = ctypes.cdll.LoadLibrary(
            ctypes.util.find_library("ApplicationServices"))
        core = ctypes.cdll.LoadLibrary(
            ctypes.util.find_library("CoreFoundation"))

        prompt_key = c_void_p.in_dll(app_services,
                                     "kAXTrustedCheckOptionPrompt")
        true_value = c_void_p.in_dll(core, "kCFBooleanTrue")
        core.CFDictionaryCreate.restype = c_void_p
        core.CFDictionaryCreate.argtypes = [c_void_p, POINTER(c_void_p),
                                            POINTER(c_void_p), c_long,
                                            c_void_p, c_void_p]
        keys = (c_void_p * 1)(prompt_key)
        values = (c_void_p * 1)(true_value)
        options = core.CFDictionaryCreate(
            None, keys, values, 1,
            byref(c_void_p.in_dll(core, "kCFTypeDictionaryKeyCallBacks")),
            byref(c_void_p.in_dll(core, "kCFTypeDictionaryValueCallBacks")))

        app_services.AXIsProcessTrustedWithOptions.restype = c_bool
        app_services.AXIsProcessTrustedWithOptions.argtypes = [c_void_p]
        return bool(app_services.AXIsProcessTrustedWithOptions(options))
    except Exception:
        return permitted()


PERMISSION_HELP = (
    "macOS will not let Squint press ⌘C for you until you allow it, and it "
    "refuses without saying so — which is why this shows what you last "
    "copied instead of what you selected.\n\n"
    "In Squint, open Settings and press Enable next to \"Copy selected "
    "text\". Squint opens Privacy & Security › Accessibility for you: switch "
    "Squint on there. If it still does not work, quit and reopen Squint.\n\n"
    "Until then, copy the text yourself and press the shortcut."
)


# -- Windows --------------------------------------------------------------

def _win_user32():
    import ctypes
    return ctypes.WinDLL("user32", use_last_error=True)


def _win_modifiers_down(user32):
    for key in (VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN):
        if user32.GetAsyncKeyState(key) & 0x8000:
            return True
    return False


def _win_send_copy():
    """Ctrl+C, as though it had been typed."""
    user32 = _win_user32()

    # Wait for the shortcut's own modifiers to come up. Sending Ctrl+C
    # while Alt is still held delivers Ctrl+Alt+C to the other program —
    # which is the shortcut it just ignored.
    deadline = time.time() + RELEASE_TIMEOUT
    while _win_modifiers_down(user32) and time.time() < deadline:
        time.sleep(POLL)
    # Even once they are up, the key-up events are still travelling; a
    # copy sent in the same instant can be swallowed.
    time.sleep(0.04)

    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_C, 0, 0, 0)
    user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


# -- macOS ----------------------------------------------------------------

def _mac_send_copy():
    """Cmd+C through Quartz. Needs Accessibility permission, and says so
    by simply not working — macOS gives no error for a refused event."""
    from Quartz import (CGEventCreateKeyboardEvent, CGEventPost,
                        CGEventSetFlags, kCGHIDEventTap,
                        kCGEventFlagMaskCommand, CGEventSourceKeyState,
                        kCGEventSourceStateCombinedSessionState)

    deadline = time.time() + RELEASE_TIMEOUT
    # 55 = Command, 58/61 = Option, 59/62 = Control, 56/60 = Shift.
    watched = (55, 54, 58, 61, 59, 62, 56, 60)
    while time.time() < deadline:
        if not any(CGEventSourceKeyState(
                kCGEventSourceStateCombinedSessionState, key)
                for key in watched):
            break
        time.sleep(POLL)
    time.sleep(0.04)

    down = CGEventCreateKeyboardEvent(None, 8, True)      # 8 = "c"
    up = CGEventCreateKeyboardEvent(None, 8, False)
    CGEventSetFlags(down, kCGEventFlagMaskCommand)
    CGEventSetFlags(up, kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, down)
    time.sleep(0.01)
    CGEventPost(kCGHIDEventTap, up)


def send_copy():
    """Ask the foreground window to copy. True if the attempt was made."""
    try:
        if sys.platform == "win32":
            _win_send_copy()
            return True
        if sys.platform == "darwin":
            _mac_send_copy()
            return True
    except Exception:
        return False
    return False


# Whether the last grab() saw the clipboard actually change. Windows has a
# change counter, so there this is a fact rather than an inference; nowhere
# else, and the caller is told which by copy_was_observed() returning None.
_copy_observed = None


def copy_was_observed():
    """True, False, or None where this platform cannot say.

    The caller needs the difference. Falling back to whatever is already on
    the clipboard is a real feature — somebody who copied something by hand
    and pressed the shortcut means it — but it is a guess, and a guess
    dressed as an answer is how a translation of a paragraph from ten
    minutes ago gets presented as a translation of the sentence on screen.
    Knowing the copy definitely did not happen is what lets the card say so.
    """
    return _copy_observed


# How near the longest line in a block a line has to reach before its
# break is treated as the edge of a column rather than a decision. A line
# that stops well short of the others stopped because somebody meant it
# to — a heading, a list item, the last line of a paragraph, a line of a
# poem — and joining it to the next would run two thoughts together.
WRAPPED_AT = 0.72

# And it has to be a long line in absolute terms. A wrapped column is
# wide; a poem, a list of names, a menu and a stanza are not, and their
# short lines can easily reach three quarters of their own longest one.
# Below this much line a break is left exactly where it is.
#
# The unit is display width, not characters — see `width` below for why
# counting characters got this wrong for half the languages the app
# supports.
#
# 40 columns is about seven English words, or twenty Han characters. No
# running column of text is narrower than that; the three-column Korean
# newsletter this was measured against runs 44. A list item, a line of
# verse and a heading are all well under it.
WRAPPED_MIN = 40

# Characters written without spaces between words. Chinese and Japanese
# use no word spaces at all, and a narrow Korean column breaks wherever
# the line runs out — mid-word as readily as between words — so a break
# between two of these is joined with nothing in between.
#
# Korean is the one that costs something, because Korean does space its
# words and the break sometimes did fall between two of them. Both errors
# are possible and they are not equally bad. A space inside a word makes
# "시행한" into "시 행한": two fragments that mean nothing where one word
# meant something. A missing space between two words leaves them run
# together, which is a spacing mistake Korean writers make constantly and
# every engine is built to absorb — the reading path has been handing it
# unspaced Korean since the beginning (see `ocr.strip_cjk_spaces`) and it
# translates fine. So the run-together is the mistake to prefer.
_UNSPACED = (
    (0x3040, 0x30FF),   # kana
    (0x3400, 0x4DBF),   # CJK extension A
    (0x4E00, 0x9FFF),   # CJK unified
    (0xF900, 0xFAFF),   # compatibility
    (0xAC00, 0xD7AF),   # hangul syllables
    (0x3000, 0x303F),   # CJK punctuation
)

# A line that opens a list item is never a continuation of the line above,
# however long that line was. Items in a list are often all about the same
# length, which is exactly the shape the ratio test cannot tell from a
# wrapped column.
_ITEM_START = re.compile(r"^\s*(?:[-*•·—–▪◦]|\(?\d{1,3}[.)]|\(?[a-zA-Z][.)])\s")


def width(line):
    """How much line a line takes up, not how many characters it has.

    Counting characters is a Latin habit and it quietly broke every
    language that does not write in Latin. A full-width column of Korean
    or Chinese holds around 25 characters, because each one occupies two
    columns of the page and carries about as much meaning as an English
    word. Measured in characters that line is 25 — short, by the rule
    above — so its break was never a candidate for joining, and every
    paragraph in a Korean document reached the translation engine
    pre-chopped into fragments:

        The researchers selected pairs of
        buildings
        with similar structures and
        floors across three cities.

    The same paragraph in French measures 85 and joined perfectly. The
    text was not the difference; the ruler was.

    Unicode already records this. A character marked Wide or Fullwidth —
    Hangul, Han, kana, fullwidth punctuation — occupies two columns; a
    combining mark occupies none, since it is drawn on top of the letter
    before it. Everything else counts as one.
    """
    total = 0
    for ch in str(line or ""):
        if unicodedata.combining(ch):
            continue
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


def unspaced(ch):
    """Whether this character belongs to a script written without spaces."""
    if not ch:
        return False
    code = ord(ch)
    return any(low <= code <= high for low, high in _UNSPACED)


def unwrap(text):
    """Join the lines a document wrapped, keep the ones it meant.

    Text copied out of a PDF, a page of a book, or most email clients
    carries a line break at the end of every *rendered* line — not at the
    end of every sentence. Those breaks are an artefact of the column it
    was set in, and sending them to a translation engine hands it a
    paragraph pre-chopped into fragments. What comes back is chopped in
    the same places, and the places no longer fall between words:

        ALLERGENS — Our dis
        hes may contain: gluten, eggs, milk, nuts, celery, must
        ard, sulphites, fish and crust
        a
        ceans.

    The translation there is perfect. Every word in it is cut in half.

    The reading path has always joined these — it is what `ocr.clean`
    does with a page of recognised lines — and the clipboard path never
    did, which is why one looked broken and the other did not.

    A break is a wrap when the line before it reaches nearly as far as the
    longest line around it, and did not end in something that finishes a
    sentence. A blank line always ends a paragraph. A line ending in a
    hyphen is a word split across the break and is rejoined without it.
    """
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not raw.strip():
        return raw

    out, current = [], []
    for block in raw.split("\n\n"):
        lines = [ln.rstrip() for ln in block.split("\n")]
        lines = [ln for ln in lines if ln.strip() != ""] or []
        if not lines:
            continue
        # The block's own measure, so a narrow column and a wide one are
        # each judged against themselves.
        longest = max(width(ln) for ln in lines)
        current = []
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not current:
                current.append(stripped)
                continue
            previous = current[-1]
            joined_before = (
                width(previous) >= WRAPPED_MIN
                and width(previous) >= longest * WRAPPED_AT
                and not previous.endswith((".", "!", "?", ":", ";", "•"))
                and not _ITEM_START.match(line)
            )
            if previous.endswith("-") and len(previous) > 1 and joined_before:
                # A word broken across the break — and the hyphen stays.
                # It cannot be told from a real one: "Établissement non-"
                # ends a line in a French menu and the word is genuinely
                # "non-fumeur". Dropping it makes "nonfumeur", which is
                # not a word in any language and cannot be translated;
                # keeping it makes "Ver-brauch" out of a hyphenation,
                # which is ugly and still reads. The cheaper mistake wins.
                current[-1] = previous + stripped
            elif joined_before:
                gap = "" if (unspaced(previous[-1:])
                             and unspaced(stripped[:1])) else " "
                current[-1] = previous + gap + stripped
            else:
                current.append(stripped)
        out.append("\n".join(current))
    return "\n\n".join(out)


def grab(widget, previous=None):
    """The selected text, or None if nothing was selected.

    Two ways to tell whether the copy did anything, and they are not
    equally good.

    Windows keeps a clipboard change counter, and that is the honest
    answer: it moves when something is put on the clipboard and does not
    move when nothing is. Comparing the text cannot tell "the copy did
    nothing" from "the copy copied the same thing again", and it fails
    badly in one specific way — if the read of the previous contents
    happens to come back empty, whatever was already on the clipboard then
    looks like a fresh selection. That is how a paragraph of German on a
    classifieds page produced the release notes the user had copied ten
    minutes earlier, labelled "selection".

    Elsewhere, comparing is all there is, and it is still much better than
    assuming the copy worked.
    """
    from . import clipboard

    global _copy_observed
    _copy_observed = None
    before_count = clipboard.sequence()
    if previous is None:
        previous = clipboard.get_text(widget)
    if not send_copy():
        return None

    deadline = time.time() + CLIPBOARD_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL)
        if before_count is not None:
            if clipboard.sequence() == before_count:
                continue          # nothing has been copied yet
            _copy_observed = True
            current = clipboard.get_text(widget)
            # The counter moved, so a copy happened. Empty means the app
            # put something on the clipboard that is not text.
            return current or None
        current = clipboard.get_text(widget)
        if current and current != previous:
            _copy_observed = True
            return current
    if before_count is not None:
        # The counter never moved, and the counter does not lie: nothing
        # was put on the clipboard by anybody during the wait.
        _copy_observed = False
    return None
