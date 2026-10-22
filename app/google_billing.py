"""Keeping a Google key working after the free trial.

Google's free trial billing account closes itself after 90 days unless it
is upgraded, and every project on it stops. The key does not change and
nothing on this side is wrong — Google just refuses with a sentence about
billing, and the app used to show that as a vague failure while it quietly
fell back to the free services.

The upgrade is one button in the console, it can be pressed on the first
day, and it changes nothing about the free monthly allowance. So:

  * the setup checklist ends with it,
  * a refusal that mentions billing is recognised here and turned into one
    plain notice with a button to the page that fixes it,
  * and a key that was saved a while ago and never marked as upgraded gets
    one reminder before the 90 days are up.

Everything here is a flag and a date. Worker threads note what Google said;
the window polls `pending()` on its own thread and shows the notice.
"""
import datetime
import threading

from . import config

CFG = config.CONFIG

BILLING_URL = "https://console.cloud.google.com/billing"

TRIAL_DAYS = 90
REMIND_AFTER_DAYS = 75

# At most one "billing is off" notice a day. Every snip fails the same way
# until it is fixed, and a window per snip would be worse than the error.
_NOTICE_EVERY = datetime.timedelta(days=1)

_lock = threading.Lock()
_pending = {"kind": None}


def _today():
    return datetime.date.today()


def _parse(day):
    try:
        return datetime.date.fromisoformat(str(day or ""))
    except Exception:
        return None


def is_billing_refusal(message):
    """Whether Google's words say the project has no working billing.

    Covers the three ways it is written: "requires billing to be enabled",
    "BILLING_DISABLED", and "billing account … is disabled / closed /
    absent". A restricted key or a switched-off API is not this, and says
    so without the word billing.
    """
    low = str(message or "").lower()
    return "billing" in low


def note_refusal(message):
    """Called wherever a Google request fails. Remembers a billing refusal
    so the window can say what to do; anything else is left alone."""
    if not is_billing_refusal(message):
        return False
    with _lock:
        last = CFG.get("google_billing_notice_at", "")
        now = datetime.datetime.now()
        try:
            shown = datetime.datetime.fromisoformat(last) if last else None
        except Exception:
            shown = None
        if shown is None or now - shown >= _NOTICE_EVERY:
            _pending["kind"] = "billing_off"
    return True


def note_working():
    """A Google request succeeded, so billing is on. A notice that was
    waiting no longer has anything to say."""
    with _lock:
        if _pending["kind"] == "billing_off":
            _pending["kind"] = None


def key_saved(key):
    """Remember when this key was first set up, for the reminder. A
    different key starts the count again; the same key does not."""
    key = str(key or "").strip()
    if not key:
        return
    fingerprint = key[-6:]
    if CFG.get("google_key_tail", "") == fingerprint \
            and CFG.get("google_key_since", ""):
        return
    CFG["google_key_tail"] = fingerprint
    CFG["google_key_since"] = _today().isoformat()
    CFG["google_upgrade_reminded"] = False
    CFG.save()


def mark_upgraded(value=True):
    CFG.set("google_upgraded", bool(value))
    if value:
        with _lock:
            if _pending["kind"] == "remind":
                _pending["kind"] = None


def is_upgraded():
    return bool(CFG.get("google_upgraded", False))


def reminder_due(today=None):
    """True once, some time after day 75, for a key never marked upgraded."""
    if not str(CFG.get("google_api_key", "") or "").strip():
        return False
    if is_upgraded() or CFG.get("google_upgrade_reminded", False):
        return False
    since = _parse(CFG.get("google_key_since", ""))
    if since is None:
        return False
    today = today or _today()
    return (today - since).days >= REMIND_AFTER_DAYS


def days_left(today=None):
    since = _parse(CFG.get("google_key_since", ""))
    if since is None:
        return None
    today = today or _today()
    return max(0, TRIAL_DAYS - (today - since).days)


def check_reminder(today=None):
    """Queue the reminder if it is due. Called from the window's thread.

    The key's start date is taken here rather than at every place a key
    can be saved (Settings, first run, the checklist): whichever saved it,
    the first check after that sees a key it has no date for.
    """
    key_saved(CFG.get("google_api_key", ""))
    if reminder_due(today):
        with _lock:
            if _pending["kind"] is None:
                _pending["kind"] = "remind"


def pending():
    """Take the notice waiting to be shown, if any: "billing_off",
    "remind" or None. Taking it marks it as shown."""
    with _lock:
        kind, _pending["kind"] = _pending["kind"], None
    if kind == "billing_off":
        CFG.set("google_billing_notice_at",
                datetime.datetime.now().isoformat(timespec="seconds"))
    elif kind == "remind":
        CFG.set("google_upgrade_reminded", True)
    return kind


TEXT = {
    "billing_off": (
        "Your Google trial has ended",
        "Google has paused your key because the free trial billing "
        "account closed. Press Upgrade on Google's Billing page and the "
        "same key works again — nothing to change in Squint.\n\n"
        "The free monthly allowance stays the same: 500,000 characters "
        "and 1,000 screenshots. Until then Squint translates with Gemini "
        "or the free services."),
    "remind": (
        "Keep your Google key working",
        "Google's free trial ends 90 days after it started, and the key "
        "stops unless the account is upgraded. It is one button on the "
        "Billing page, and the free monthly allowance stays the same: "
        "500,000 characters and 1,000 screenshots. Nothing is charged "
        "below that."),
}
