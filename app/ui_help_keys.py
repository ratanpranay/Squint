"""A plain-language guide to getting API keys, inside the app.

The setup checklist next door tests a key you already have and tells you
what is still switched off. This answers the question that comes before
that one: what is a key, which one do I want, and what do I click.

It lives in the app rather than as a link to a web page for two reasons.
The people this is for are reading it because they are stuck, and a link
that opens a browser on a locked-down office PC is one more thing that can
fail. And a page on the internet drifts out of step with the app; this
ships with the build it describes.

Nothing here is required. The app translates with no keys at all — that is
worth saying first and plainly, because a wall of setup instructions
implies the opposite.
"""
import tkinter as tk
import webbrowser

from . import theme as theme_mod
from .ui_kit import PillButton, ScrollArea, Surface, label


# Each section: heading, one line on why you would want it, then the steps.
# Steps are (text, optional link). Kept short on purpose — the failure mode
# of a guide like this is that nobody reads it.
GUIDE = [
    {
        "title": "You may not need any of this",
        "cost": "",
        "why": "Squint works with no keys at all. It uses free public "
               "translation services, and on a Mac it reads the screen "
               "with Apple's own text recognition. Add a key when you hit "
               "one of the two problems below — not before.",
        "steps": [],
    },
    {
        "title": "Google — the usual choice",
        "cost": "Free for 500,000 characters and 1,000 screenshots a month. "
                "Needs a card on file, but nothing is charged inside those "
                "limits.",
        "why": "Two problems it solves. The free services are shared by "
               "everyone on your office network, so they start refusing "
               "(\"rate limited\") by mid-morning. And on Windows, reading "
               "Chinese, Japanese, Korean, Russian or Arabic off the screen "
               "needs either a Windows language pack or Google.",
        "steps": [
            ("Go to Google Cloud and sign in with any Google account. If "
               "you have used it before you land straight in the console; "
               "only a brand-new account is asked to set one up.",
             "https://console.cloud.google.com/"),
            ("Setting one up asks for a payment method. Google wants one "
               "on any project using these two services, and charges "
               "nothing inside the free limits above.", None),
            ("Switch on the two services Squint uses. Open each page and "
               "press Enable:", None),
            ("      Cloud Translation — turns the text into English.",
             "https://console.cloud.google.com/apis/library/"
             "translate.googleapis.com"),
            ("      Cloud Vision — reads the text off the screen. Only "
               "needed for snipping; translating from the clipboard works "
               "without it.",
             "https://console.cloud.google.com/apis/library/"
             "vision.googleapis.com"),
            ("Make a key: APIs & Services → Credentials → Create "
               "credentials → API key. Copy it.",
             "https://console.cloud.google.com/apis/credentials"),
            ("If you restrict the key — under API restrictions — do it "
               "after the step above and not before. A service that is "
               "not switched on yet is not in the list to tick, and a key "
               "restricted without them fails exactly like a key that was "
               "never made.", None),
            ("Paste it into Squint's Settings and press Save & test. Or "
               "use Set up Google, which checks all of the above for you "
               "and says which part is missing.", None),
        ],
    },
    {
        "title": "DeepL — better German, French, Japanese",
        "cost": "Free for 500,000 characters a month. No card needed for "
                "the free plan.",
        "why": "Noticeably more natural than Google on European languages "
               "and Japanese. It does not read screenshots, so it handles "
               "the translating only — something else still does the "
               "reading.",
        "steps": [
            ("Sign up for DeepL API Free — the *API* plan, not DeepL Pro. "
               "They are different products and only the API one gives you "
               "a key.", "https://www.deepl.com/pro-api"),
            ("Open your account page and find Authentication Key for "
               "DeepL API.", "https://www.deepl.com/your-account/keys"),
            ("Copy it — a free key ends in :fx, and that part matters, so "
               "copy the whole thing.", None),
            ("Paste it into Settings → DeepL key, press Save & test, then "
               "set Translating to DeepL.", None),
        ],
    },
    {
        "title": "Gemini — understands context",
        "cost": "Free tier, no card. The allowance is per day rather than "
                "per month, and it resets at midnight in California — not "
                "at yours.",
        "why": "A language model rather than a translator, so it can tell "
               "a brand name from a word. Slower than the others, and the "
               "free tier can run out mid-afternoon.",
        "steps": [
            ("Open Google AI Studio and sign in.",
             "https://aistudio.google.com/app/apikey"),
            ("Press Create API key and copy it.", None),
            ("Paste it into Settings → Gemini key and press Save & test.",
             None),
            ("Reading a screenshot spends one request and translating "
               "spends another. Leaving Reading text on Automatic reads on "
               "this computer first and asks Gemini only when that looks "
               "wrong, which makes the allowance last about twice as "
               "long.", None),
            ("The allowance belongs to your Google account rather than to "
               "Squint, so anything else using the same key is spending "
               "the same allowance. Your own current limits are here.",
             "https://aistudio.google.com/rate-limit"),
        ],
    },
    {
        "title": "Where your key is kept",
        "cost": "",
        "why": "In your own settings file on this computer, not in the app "
               "folder — so it is not in any copy of Squint you pass on, "
               "and an update never touches it. It is sent only to the "
               "service it belongs to. If you ever paste a key into a "
               "screenshot or a chat, delete it in the console and make a "
               "new one; that costs nothing.",
        "steps": [],
    },
]


class KeyHelp(tk.Toplevel):
    """Read-only. Every link opens in the browser."""

    def __init__(self, master, palette=None):
        super().__init__(master)
        self.palette = palette or theme_mod.resolve("light")
        p = self.palette
        self.title("How to add API keys")
        self.configure(bg=p["window"])
        # Only ever up. The type in here follows the page's
        # scale, and a page drawn small leaves these windows
        # with more room than they need — which is fine. Taking
        # the window down with it is not: the rows inside have
        # widths of their own and they stop fitting.
        scale = max(1.0, min(1.4, theme_mod.PAGE_SCALE))
        self.geometry("%dx%d" % (740 * scale, 700 * scale))
        self.minsize(int(620 * scale), int(500 * scale))

        root = tk.Frame(self, bg=p["window"])
        root.pack(fill="both", expand=True, padx=24, pady=(20, 18))

        label(root, p, "How to add API keys", size=17, weight="bold",
              display=True).pack(anchor="w")
        label(root, p,
              "A key is a password that lets Squint use a translation "
              "service under your own account. Each service gives you a "
              "monthly allowance for nothing.",
              size=9, dim=True, wraplength=640,
              justify="left").pack(anchor="w", pady=(6, 14))

        footer = tk.Frame(root, bg=p["window"])
        footer.pack(side="bottom", fill="x", pady=(14, 0))
        PillButton(footer, "Close", command=self.destroy, palette=p,
                   kind="secondary", height=38).pack(side="right")

        area = ScrollArea(root, p)
        area.pack(fill="both", expand=True)
        for section in GUIDE:
            self._section(area.body, section)
        self.transient(master)
        self.after(120, area.bind_wheel_recursive)

    def _section(self, parent, section):
        p = self.palette
        card = Surface(parent, p, radius=16, padding=20, bg=p["window"])
        card.pack(fill="x", pady=(0, 12), padx=(0, 4))
        body = card.body

        label(body, p, section["title"], size=12, weight="bold",
              bg=p["surface"]).pack(anchor="w")
        if section["cost"]:
            cost = label(body, p, section["cost"], size=9, wraplength=560,
                         justify="left", bg=p["surface"])
            cost.configure(fg=p["success"])
            cost.pack(anchor="w", pady=(4, 0))
        label(body, p, section["why"], size=10, dim=True, wraplength=560,
              justify="left", bg=p["surface"]).pack(
                  anchor="w", pady=(8, 0))

        if not section["steps"]:
            return
        steps = tk.Frame(body, bg=p["surface"])
        steps.pack(fill="x", pady=(14, 0))
        number = 0
        for text, link in section["steps"]:
            row = tk.Frame(steps, bg=p["surface"])
            row.pack(fill="x", pady=(0, 8))
            # Indented lines are continuations of the step above, so they
            # are not numbered again — the two API pages under step 3.
            indented = text.startswith("   ")
            if not indented:
                number += 1
            label(row, p, "" if indented else "%d." % number, size=10,
                  dim=True, bg=p["surface"], width=3,
                  anchor="nw").pack(side="left", anchor="n")
            label(row, p, text.strip(), size=10, wraplength=430,
                  justify="left", bg=p["surface"]).pack(
                      side="left", anchor="n")
            if link:
                PillButton(row, "Open", command=self._opener(link),
                           palette=p, kind="ghost", height=30, font_size=9,
                           bg=p["surface"]).pack(side="right", anchor="n")

    def _opener(self, url):
        def go():
            try:
                webbrowser.open(url)
            except Exception:
                pass
        return go
