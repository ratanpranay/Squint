# Squint
Yet another snap translate app that let's you translate anything on your screen, in place.
Drag a box around text — a website, a PDF, a photo, a menu, an app with no translate button — and Squint reads it and draws the translation back over the original, keeping the layout, the colours and the position.

Free, works on Windows and macOS, and needs no account to start.

What it's for

Squint is for text you can see but can't easily translate:

Foreign-language websites where the browser's translate button mangles the layout or isn't offered at all.
PDFs, invoices and datasheets — anything where the text is really a picture and you can't select it.
Screenshots somebody sent you.
Software in another language — a control panel, an installer, an error message.
Photos of signs, packaging, forms, handwriting on a whiteboard.

The idea is to avoid the extra step of opening Google Translate or your phone's camera. Just press the shortcut (you set your own shortcut) and it translates the text to your preferred language. 


How you use it

Snip and translate — press Ctrl + Alt + T (Windows) or ⌃ + ⌘ + T (macOS) anywhere, drag a box, and the translation appears over what you selected. Scroll with Ctrl held to make it bigger. Press Esc or click to dismiss it.

Translate what you've selected — highlight some text anywhere, press Ctrl + Alt + C (Windows) or ⌃ + ⌘ + C (macOS). Squint copies it for you and shows the translation on a card.

Open a file — drag a JPG, PNG, TIFF, BMP, WEBP or PDF onto the window.

Both shortcuts can be changed in Settings if they clash with something else.


Install — Windows
Download the zip from Releases and unzip it anywhere.
Double-click setup.bat. If Windows says "Windows protected your PC": click More info ▸ Run anyway (or simply run as admin). The file isn't signed, so this appears for everyone.
Wait 3–10 minutes. It installs Python if you don't have it, then the packages and the text-recognition engine.
Say Y when it offers to start the app.

Then press Ctrl + Alt + T anywhere.


Install — macOS
Download the zip from Releases and unzip it anywhere.
Open Terminal, type bash  — with a space after it — then drag setup.command into the Terminal window and press Enter.
Wait a few minutes while it sets up Python and the packages.
Say y when it offers to start the app.

Then press ⌃ + ⌘ + T (control-command-T) anywhere.

Why not just double-click it? A zip downloaded through a browser is quarantined by macOS, and double-clicking setup.command gets refused with "cannot be opened because it is from an unidentified developer." Typing bash in front of it avoids that. If you prefer clicking, right-click ▸ Open ▸ Open works too.

Setup builds Squint.app and offers to put it in your Applications folder.

macOS will ask for two permissions the first time: Screen Recording (to read the part of the screen you select) and Accessibility (so the selection shortcut can copy for you). Both are in System Settings ▸ Privacy & Security.


Do I need an API key?

No. It works out of the box using free services.

A free Gemini key makes it noticeably better — a Google account, no credit card, about a minute — and it both reads screenshots and translates, understanding context and brand names rather than translating word by word. Settings ▸ Translation quality has a Get a free key… button that walks you through it.

There's a daily limit on the free tier, and Squint tells you when it runs out and carries on with the free services until it resets.

Updating

Squint checks once a day and says so in the window when there's a new build. Settings ▸ Updates ▸ Install and restart does the rest.

Removing it

Windows: run uninstall.bat. macOS: delete the folder and Squint.app.

Nothing is installed system-wide.



Enjoy =)
