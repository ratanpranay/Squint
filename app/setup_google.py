"""Work out what is missing from a Google setup, and say what to do.

Getting Google translation and reading working takes three things done in
two different corners of the Cloud console: a key, one API switched on, and
a second API switched on. Miss any of them and every one comes back to the
app as a bare 403, so the user goes and looks at their key — which is the
one thing that was never wrong.

This module does not walk anyone through a wizard. It asks Google what is
actually true right now and reports it a step at a time, because a checklist
that inspects the real state is worth more than instructions that cannot
tell whether they worked. Each failing step carries the page that fixes it.

Nothing here changes anything on the user's Google account. It cannot: an
app can neither create a project nor add a card on someone's behalf. It can
only test, and be specific.
"""
import re

CREDENTIALS_URL = "https://console.cloud.google.com/apis/credentials"
TRANSLATE_URL = ("https://console.cloud.google.com/apis/library/"
                 "translate.googleapis.com")
VISION_URL = ("https://console.cloud.google.com/apis/library/"
              "vision.googleapis.com")
BILLING_URL = "https://console.cloud.google.com/billing"
PROJECT_URL = "https://console.cloud.google.com/projectcreate"

# Google's browser keys have looked like this for years. Used only to catch
# an obvious paste error — a wrong-looking key is still sent and tested,
# because a format guess is not evidence.
KEY_SHAPE = re.compile(r"^AIza[0-9A-Za-z_\-]{20,}$")


class Step:
    """One thing that has to be true, and what to do when it is not."""

    def __init__(self, name, why, url, action):
        self.name = name
        self.why = why
        self.url = url
        self.action = action
        self.state = "waiting"        # waiting | ok | failed
        self.detail = ""

    def succeed(self, detail=""):
        self.state, self.detail = "ok", detail
        return self

    def fail(self, detail=""):
        self.state, self.detail = "failed", detail
        return self

    @property
    def ok(self):
        return self.state == "ok"

    def __repr__(self):
        return "<Step %s %s>" % (self.name, self.state)


def steps():
    """The checklist, in the order it has to be done."""
    return [
        Step("An API key",
             "One key does both jobs. Create credentials › API key, tick "
             "Cloud Translation and Cloud Vision under API restrictions, "
             "then copy it and paste it below.",
             CREDENTIALS_URL, "Open Credentials"),
        Step("Cloud Translation API",
             "Translates the text once it has been read. 500,000 "
             "characters a month are free.",
             TRANSLATE_URL, "Open and press Enable"),
        Step("Cloud Vision API",
             "Reads text off the screen, including Chinese, Japanese, "
             "Korean, Russian and Arabic. 1,000 screenshots a month are "
             "free. Only needed for snipping — clipboard translation "
             "works without it.",
             VISION_URL, "Open and press Enable"),
    ]


# Two steps that are shown but cannot be tested with a key: the project
# and card come first and are only visible through what the APIs say; the
# upgrade comes last and is the user's to tick.
PROJECT = Step("A project and a card — first time only",
               "Create a project, then press Enable on Cloud Translation "
               "below: Google asks for a card the first time. It is how "
               "Google checks you are a real person — the free trial "
               "charges nothing.",
               PROJECT_URL, "Create project")

UPGRADE = Step("Keep it working after 90 days",
               "Google's free trial closes after 90 days unless the account "
               "is upgraded — one button on the Billing page, and it can be "
               "done today. The key stays the same and the free monthly "
               "allowance still applies; nothing is charged below it.",
               BILLING_URL, "Open Billing")


def project_state(results):
    """The project step, judged from what the APIs said."""
    step = Step(PROJECT.name, PROJECT.why, PROJECT.url, PROJECT.action)
    _key, translate, vision = results
    if translate.ok or vision.ok:
        return step.succeed()
    if any(ADVICE["billing"] in (s.detail or "") for s in results):
        return step.fail(ADVICE["billing"] + " Open Billing and link one, "
                         "or finish the card step Google offers when you "
                         "press Enable.")
    return step


def _diagnose(message):
    """Turn Google's reply into the thing the user has to go and do.

    All three of these arrive as a 403 with different prose, and they need
    completely different actions — enable an API, widen a key restriction,
    or add a card. Reporting "403" would be true and useless.
    """
    low = (message or "").lower()
    if ("has not been used" in low or "is disabled" in low
            or "not enabled" in low):
        return "not_enabled"
    if "restrict" in low:
        return "restricted"
    if "billing" in low:
        return "billing"
    if "api key not valid" in low or "invalid" in low and "key" in low:
        return "bad_key"
    if "429" in low or "quota" in low:
        return "quota"
    return "unknown"


ADVICE = {
    "not_enabled": "This API is not switched on for the project yet. "
                   "Open the page and press Enable, then check again.",
    "restricted": "The key is restricted and does not include this API. "
                  "Open Credentials, click the key, and add it under "
                  "API restrictions.",
    "billing": "The project needs a billing account before this API will "
               "answer, even inside the free allowance.",
    "bad_key": "Google does not recognise this key. Check it was copied "
               "whole, with no spaces.",
    "quota": "The key works — there is just none of the free allowance "
             "left this month.",
    "unknown": "",
}


def check(key, want_vision=True):
    """Test a key against both APIs. Returns the checklist, filled in.

    Everything is tested even when an earlier step fails, so the user sees
    the whole picture at once rather than fixing one thing, checking, and
    discovering the next.
    """
    from . import config, translator

    key = "".join(str(key or "").split())
    found, translate_step, vision_step = steps()

    if not key:
        found.fail("No key yet.")
    elif not KEY_SHAPE.match(key):
        # Tested anyway — this only softens the message if it then fails.
        found.succeed("Saved, though it does not look like a Google key.")
    else:
        found.succeed("Saved.")

    if not key:
        translate_step.fail("Needs a key first.")
        vision_step.fail("Needs a key first.")
        return [found, translate_step, vision_step]

    saved = config.CONFIG.get("google_api_key", "")
    try:
        config.CONFIG.set("google_api_key", key)
        try:
            out = translator._google_api("Guten Morgen", "de", "en")
            translate_step.succeed("Working — “Guten Morgen” → "
                                   "“%s”." % out.strip()[:28])
        except Exception as exc:
            reason = _diagnose(str(exc))
            if reason == "quota":
                translate_step.succeed(ADVICE["quota"])
            else:
                translate_step.fail(ADVICE.get(reason) or str(exc)[:160])
            if reason == "bad_key":
                found.fail(ADVICE["bad_key"])

        if want_vision:
            _check_vision(vision_step, found)
        else:
            vision_step.state = "waiting"
            vision_step.detail = "Not checked."
    finally:
        config.CONFIG.set("google_api_key", saved)

    return [found, translate_step, vision_step]


def _check_vision(step, key_step):
    from PIL import Image
    from . import ocr_google
    try:
        ocr_google._annotate(Image.new("RGB", (32, 32), "white"), [])
        step.succeed("Working — Google can read screenshots.")
    except Exception as exc:
        reason = _diagnose(str(exc))
        if reason == "quota":
            step.succeed(ADVICE["quota"])
            return
        step.fail(ADVICE.get(reason) or str(exc)[:160])
        if reason == "bad_key" and key_step.ok:
            key_step.fail(ADVICE["bad_key"])


def summary(results):
    """One line for the status bar."""
    done = [s for s in results if s.ok]
    if len(done) == len(results):
        return True, "All set — Google is doing both the reading and the "\
                     "translating."
    stuck = [s for s in results if s.state == "failed"]
    if not stuck:
        return False, "Not checked yet."
    if len(stuck) == 1:
        return False, "One thing left: %s." % stuck[0].name
    return False, "%d things left: %s." % (
        len(stuck), ", ".join(s.name for s in stuck))
