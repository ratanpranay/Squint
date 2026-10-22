"""The one notice about Google billing: trial ended, or about to.

A small window rather than a line in an error card, because the fix is on
a web page and the only useful thing to offer is the button to that page.
"""
import tkinter as tk
import webbrowser

from . import google_billing, platform_util, theme as theme_mod
from .ui_kit import PillButton, label


class BillingNotice(tk.Toplevel):

    def __init__(self, master, kind, palette=None):
        super().__init__(master)
        self.palette = palette or theme_mod.resolve("light")
        p = self.palette
        title, words = google_billing.TEXT[kind]
        self.title(title)
        self.configure(bg=p["window"])
        self.resizable(False, False)

        root = tk.Frame(self, bg=p["window"])
        root.pack(fill="both", expand=True, padx=26, pady=(22, 20))
        label(root, p, title, size=15, weight="bold",
              display=True).pack(anchor="w")
        label(root, p, words, size=10, dim=True, wraplength=440,
              justify="left").pack(anchor="w", pady=(8, 18))

        buttons = tk.Frame(root, bg=p["window"])
        buttons.pack(fill="x")
        PillButton(buttons, "Open Google Billing", command=self.open_billing,
                   palette=p, kind="primary", height=38).pack(side="left")
        PillButton(buttons, "I've upgraded", command=self.upgraded,
                   palette=p, kind="secondary",
                   height=38).pack(side="left", padx=(8, 0))
        PillButton(buttons, "Later", command=self.destroy, palette=p,
                   kind="ghost", height=38).pack(side="right")
        try:
            self.attributes("-topmost", True)
            platform_util.raise_to_front(self)
        except Exception:
            pass

    def open_billing(self):
        webbrowser.open(google_billing.BILLING_URL)

    def upgraded(self):
        google_billing.mark_upgraded(True)
        self.destroy()


def show(master, kind, palette=None):
    try:
        return BillingNotice(master, kind, palette=palette)
    except Exception:
        return None
