# Changelog

Every release, what changed in it, split into **Fixed**, **Added**,
**Changed** and **Removed**. Newest first.

`VERSION.txt` explains the same changes at length — why each one happened
and what was actually wrong. This file is the short version: what to expect
when you update.

Versions are **MAJOR.MINOR.PATCH**. MAJOR when the app works differently
enough that a habit has to change, MINOR for something that was not there
before, PATCH for something that was broken and is not any more.

Nothing ships without an entry here. `tools/make_release.py` refuses to
build a release whose version has no section below, because "I will write
it up after publishing" is how a version goes out that nobody, six months
later, can say anything about. It also reads this file to produce the
release notes — the GitHub description and the panel in Settings both quote
it, so there is exactly one copy to keep true.

---

## Unreleased

### Changed

- **Mouse only**: tools and actions are picked by clicking; the number
  and letter keys no longer pick anything (Esc still goes back/closes).
- **Panels match the ring**: light or dark with the system, in the tone
  of the frosted glass, with rounded corners. Calendar days are round.
- **Pill-shaped buttons and choices** in every panel.

---

## 1.58.1 — 2026-10-24

### Fixed

- **Mac: the ring showed only text** (no glass, buttons, icons or action
  pills). Its pictures are now handed to the Mac in a way every Mac
  reads, and plain shapes are drawn underneath as a backup.

---

## 1.58.0 — 2026-10-24

### Changed

- **Frosted-glass ring** that follows your system: white glass in light
  mode, dark glass in dark mode. What is behind it shows through, blurred.
- **A colour for each tool**: Capture blue, Record red, Translate teal,
  PDF orange, Zip purple, Transfers green, Calendar yellow, Extract pink.
  The picked tool and its lit action fill with that colour.
- **No disc in the middle**: the heart, time and text float on the glass.
- **Actions bloom out of the ring**: picking a tool shows its actions as
  pills right beside it (click, or press the letter). The panel now only
  opens for settings, progress, the calendar and the QR code. Each tool's
  note (where files are saved and so on) shows in one place, under the
  ring. Transfers
  shows your name as a pill; click it to change it.
- **Live centre**: when nothing is picked, the middle shows the time, the
  date, the week number and your next appointment. The ♥ stays on top.
- The key hint under the ring sits on a dark card, so it reads on white
  pages too.

### Fixed

- **Mac: the Selfie check closed Squint when installed from the disk
  image** (the app did not say why it uses the camera).

### Added

- **Mac disk image built automatically** with every release (Apple
  Silicon Macs).
- **Week numbers in the calendar**: a "Wk" column beside every week, and
  the week number next to the chosen day.

---

## 1.57.0 — 2026-10-23

### Changed

- **Eight tools in the ring, evenly spaced.** Convert is gone; what it did
  moved where you would look for it.
- **PDF → Convert to PDF** takes Word, PowerPoint, Excel, pictures and PDFs
  together. With several files, choose one PDF or a PDF for each. On a Mac
  it uses Pages, Keynote or Numbers.
- **Record → Video to MP4** takes every common video: MOV, MKV, AVI, WMV,
  WebM, FLV, MTS, 3GP, MPEG and more. Saved with the recordings. The Mac
  now fetches the same video tools as Windows the first time (it could
  only do MOV before).
- **Transfers:** "Receive" is now "Receive from nearby device"; Phone via
  QR offers "From phone to this PC" and "From this PC to phone".

### Removed

- Image format / resize.

---

## 1.56.0 — 2026-10-22

### Fixed

- **Mac: the file window for choosing files was stuck in a corner** and
  could not be moved. Squint now uses the Mac's own file window, centred
  and movable, and hides the ring while it is open.
- **Mac: panel notes said "Explorer"**; they say Finder now, with Mac-style
  folder paths.
- **Mac: number and letter keys did nothing in the ring.** 1–9 pick a tool
  and letters pick an action, as on Windows, while the mouse is over the
  ring or its panel.

### Changed

- **Smooth, matching icons in the ring** on both Windows and Mac (the Mac
  used to show numbers instead).
- **One text scale everywhere**: the smallest text in the panels is a
  little bigger, buttons are the same size in every panel, and the
  recording bar and the little pop-up messages now match the panel's look
  and sharpen on high-resolution screens.
- The key hint under the ring hides when a panel covers it.
- The frame around a screenshot area is blue; red is kept for recording.

### Removed

- Old pop-up dialog code the panel replaced.

### Added

- Automatic checks of every tool (zip, PDF, media, convert, stitch, GIF,
  calendar, world clock, QR, transfers) run before each release is built;
  a failing check stops the release.

---

## 1.55.3 — 2026-10-22

### Fixed

- **Mac: "Restart Squint" in Selfie check closed Squint but did not open
  it again.** It now follows the same steps as check.command: waits for
  Squint to close, rebuilds the app with the camera permission, puts it
  back where yours is (Applications included), and opens that copy.

---

## 1.55.2 — 2026-10-22

### Changed

- **Selfie check in the middle of the ring.** The camera shows as a round,
  mirrored picture where the QR codes appear, with Save photo and Close in
  the panel beside it.

### Fixed

- **Mac: Squint closed when Selfie check opened the camera.** macOS ends an
  app that touches the camera before its app package says why it needs it,
  and an in-app update does not refresh the package. Selfie check now
  checks first, and if the package is behind it offers "Restart Squint":
  Squint closes, updates its app with the camera permission, and opens
  again by itself. After that macOS asks once to allow the camera.

---

## 1.55.1 — 2026-10-22

### Fixed

- **Mac: Squint's window came up with the tools menu**, even when it was
  minimized or behind other windows. The ring now opens on its own, and
  the app you were in stays in front.
- **Mac: pointing at a tool did nothing**; each one had to be clicked.
  Pointing works now, as on Windows.
- **Mac: buttons in the panel were unreadable** (white on white). They are
  drawn the same as on Windows now.

### Changed

- **Mac: Selfie check shows the camera in the panel**, like on Windows,
  instead of opening Photo Booth. The first time it downloads camera
  support (about 40 MB) and macOS asks once to allow the camera.

---

## 1.55.0 — 2026-10-22

### Added

- **The tools menu on Mac.** Option + Space opens the same ring as on
  Windows (Control + Option + Space if another app such as Alfred already
  uses it). Screenshots, scrolling capture, GIFs, translate, PDF, zip,
  Transfers, calendar and world clock, convert and extract all work.
  Files selected in Finder are used the way Explorer's are on Windows.
  Selfie check opens Photo Booth. Region video stays Windows-only for now;
  on a Mac, Shift + Command + 5 records the screen.

---

## 1.54.1 — 2026-10-22

### Changed

- **Support line on a white background**, readable over anything behind
  the ring.
- **Round QR codes.** The PayPal code and the Transfers code are drawn as
  dots on a white circle that fits the middle of the ring.

### Fixed

- **The ring could not be closed by clicking outside it while the support
  code was showing.**

---

## 1.54.0 — 2026-10-22

### Changed

- **The ring opens on its own.** No tool's list is open until the mouse
  points at a tool.
- **Send is now called Transfers.**
- **Support line above the ring.** The ♥ shows the PayPal code in the
  middle of the ring and one line above it: "Support Squint if it saves you
  time". Clicking the code brings the ♥ back; clicking the line opens
  PayPal.
- **Bigger calendar.** Wider, with larger dates, agenda and world clocks.

---

## 1.53.0 — 2026-10-22

### Changed

- **Alt + Space opens the tools menu.** Quicker than Ctrl + Alt + Space.
  If another program already uses Alt + Space (PowerToys Run does), Squint
  falls back to Ctrl + Alt + Space by itself. The middle of the ring shows
  which one is active.
- **♥ shows the PayPal code in the ring.** Scan it with a phone to support
  Squint, or press Open PayPal.

### Added

- **Your name for sending.** Send shows the name others see (the computer's
  name to start with); click Change to set your own. It is what appears on
  other computers and on the phone page.

### Fixed

- **Phones and other computers could not connect.** Windows Firewall
  blocked them, and its "Allow access?" question could end up hidden behind
  the ring. Receive and Phone via QR now notice this and offer a one-time
  Allow button (Windows asks to confirm). They also say what to check when
  the phone and computer are on different or guest Wi-Fi.

---

## 1.52.0 — 2026-10-22

### Changed

- **Everything happens inside the ring.** Every tool now uses the same
  panel beside the ring for its actions, settings, progress and results.
  No tool opens a window of its own any more while the ring is up.
- **Send in the ring.** Send, Receive and Phone via QR show in the panel,
  and the QR code appears in the middle of the ring. Incoming files from
  another computer are accepted or declined right there.
- **Calendar on hover.** Point at Calendar and the month appears; it stays
  while the mouse is on it and goes away when the mouse leaves. Each agenda
  item can be deleted.

### Added

- **World clock** in the calendar: California, Frankfurt, India and
  Shanghai to start with. Click a clock to pick another city. Summer and
  winter time are followed automatically.
- **Selfie check** under Capture: the laptop camera, live and mirrored, to
  see how you look before a call. Nothing is recorded unless you press
  Save photo.
- **♥ Support Squint** in the middle of the ring opens a PayPal donation
  page.

---

## 1.51.0 — 2026-10-22

### Changed

- **One small card per action.** Picking an action in the tools menu now
  opens a small card where the menu was, instead of separate pop-up
  windows. The card shows that action's settings (a password, a format, a
  size), a Start button, then a progress bar in the same place, and ends
  with Done and Open folder. Actions with nothing to set go straight to the
  progress bar. Hide keeps the work going in the background and says when
  it is finished.

### Fixed

- **Scrolling screenshot often kept only the first screen.** On pages with
  a menu bar or header that stays put while the page scrolls (most
  websites), the scrolled parts were not recognised. They are now, and if
  the page really did not move, the message says so and how to do it.
- **Zip and Send ignored the files selected in Explorer** and asked for
  files instead.

---

## 1.50.2 — 2026-10-22

### Changed

- **One folder per tool, all in Downloads\\Squint.** Everything the tools
  menu makes now goes into its own folder there: Screenshots, Recordings,
  PDF, Zip, Received, Converted and Extracted media. Each tool's panel says
  where, and so does the message when it finishes.

### Fixed

- **Tools menu panel over the hint line.** For the tools at the bottom of
  the ring the panel was drawn under the "1–9 picks a tool" line, and a
  long note could run past the panel's edge.

---

## 1.50.1 — 2026-10-22

### Changed

- **Extract media saves to Downloads\\Squint.** Pictures, videos and sounds
  pulled out of a PowerPoint, Word or PDF now go into their own folder in
  Downloads\\Squint (named after the file), with a progress bar while it
  works, and the folder opens by itself when it is done.

### Fixed

- **Progress windows could stay open or freeze.** The bar shown while the
  video tools or 7-Zip download, or while files are sent to another
  computer, was closed from the wrong place; it now always closes when the
  work ends, whether it worked or not.

---

## 1.50.0 — 2026-10-22

### Added

- **Tools menu on Ctrl + Alt + Space (Windows).** A ring of nine everyday
  tools opens around the mouse: screenshot (region or a long scrolling
  page), screen recording (video, or a GIF of up to six seconds), translate
  and copy text, PDF tools, zip, sending files to a phone or another
  computer on the same Wi-Fi, a calendar, file conversion, and pulling the
  pictures and videos out of PowerPoint, Word and PDF files. Press 1–9 for
  a tool and a letter for what to do with it. Squint's own shortcuts work
  exactly as before.
- **Passwords for PDFs and zips.** Every PDF action can lock the result
  with a password (AES-256). Zips can be locked too, with a compatible mode
  for people who will open them without 7-Zip.
- **Phone via QR.** Scan the code with a phone's camera to download files
  from the computer or send photos to it. Nothing to install on the phone.
- **Calendar.** A month view with an agenda kept on this computer; items
  with a time pop up as reminders.

The video tools (about 140 MB) and 7-Zip are downloaded the first time
something needs them, not with the update.

---

## 1.49.3 — 2026-10-21

### Fixed

- **Pages with a watermark stamped all over them.** A name and date
  repeated across a document in rows were read as text: lines that crossed
  it came out broken or half untranslated, and pieces of the watermark were
  translated and drawn on the page. The watermark is now recognised by how
  it repeats, and taken out before the page is read.
- **Snips taking up to a minute or more.** After one slow translation,
  later pages were sent to an online service first and waited for it however
  long it took. It now gets three seconds; after that the page is translated
  on this computer.
- **"Could not reach the update server: certificate verify failed".** On
  some Windows computers the update check could not confirm the server's
  certificate and failed every time, while translating worked. The update
  check now trusts the same certificates translating does, plus the
  computer's own.

---

## 1.49.2 — 2026-10-13

### Fixed

- **Text on photos.** Headlines written in capitals are translated; short
  labels the engine handed back unchanged ("Motorrad", "Auto") are asked
  again; letters the reader imagined in a photo are left out; a page of
  labels with figures such as "25-40PSI" is shown as an overlay, not a card.
- **Labels on pictures** no longer cover the figures under them, and the
  cover behind a translation is the picture softened instead of a grey box.
- **Squint getting slower and stuck the longer it ran.** A leftover
  background reader went over the whole screen every few seconds, all day,
  and again at every snip - making snips take 2-3 s instead of a fraction
  of a second. Nothing used it any more; it is gone, along with its switch
  in Settings.
- **Windows: the panel from the tray icon** was cut off at the bottom of
  the screen. It is now placed on the monitor the pointer is on, above
  the taskbar.

---

## 1.49.1 — 2026-10-10

### Fixed

- **Every page went to an online engine after the first start.** The
  offline model's speed was learned from a one-word warm-up that included
  the model starting up (6.6 s), which made it look a thousand times
  slower than it is; from then on every page was sent online, and Gemini
  took 7-8 s for each. Speed is now learned from translating alone, on
  pages long enough to say anything, and only Groq - which answers in
  under a second - is chosen for speed. Found by Run check.
- **A piece of one paragraph showing up at the end of another**
  ("…as quickly as possible! OHNE POWERMETER FUNKTION"). An online
  answer like that is now noticed and asked again.

---

## 1.49.0 — 2026-10-10

A release about the basics: every snip read in full, translated by one
engine, and checked on your own computer.

### Added

- **Run check** (Settings › Support). Three test pages go through the
  whole snip on your computer - your reader, your engine - and are
  checked: every line read, every paragraph translated, the translation
  drawn over every line, all within three seconds. The result is shown,
  and written to selfcheck.txt beside the log to send in.

### Changed

- **A snip always reads its own area.** It no longer takes over an
  earlier reading of the screen (made when the shortcut was pressed, or
  by a cancelled snip) - the source of paragraphs left untranslated - and
  never waits for other work: anything else under way is stopped.
- **One engine per page, chosen before anything is sent.** The offline
  model and an online engine no longer race each other: the same page
  now comes back the same way, from the same engine, every time. An
  online engine translates a page only when the offline model's own
  recent speed says it would go over three seconds, or when it fails.
- **The Squint icon on selected text follows one rule:** a drag or a
  double click that began on text shows it. The selected text is asked
  for when you click the icon, when every app has settled it.

### Fixed

- **Paragraphs left in the original between translated ones.** A snip
  can use the reading of the page made when the shortcut was pressed; at
  the size of a whole window the reader sometimes passed over a paragraph,
  and the snip took that reading as it was. Rows of text the reading has
  no line on are now read again before translating.
- **Slow paragraphs written with dots and no spaces**
  ("verkaufen....Das Rad"). They were taken for one long sentence and
  translated in one go; they are now cut at those dots like any other
  sentence end.

### Changed

- The log says what became of each selection - icon shown, or why not -
  without the text itself, to find out why the Squint icon sometimes does
  not appear.

---

## 1.48.52 — 2026-10-10

### Fixed

- **The Squint icon often did not appear on a Mac** after selecting text
  in a browser. The browser was asked what was selected the instant the
  mouse came up, before it had settled its selection, and answered
  "nothing". It is now asked again over half a second; and where an app
  will not say what is selected, a selection made on text still gets the
  icon (clicking it then copies the text, as Ctrl+Cmd+C does).

### Changed

- **Faster offline translation of long paragraphs.** A paragraph is cut
  into shorter runs of whole sentences, and the longest pieces of the page
  are started first instead of waiting behind short labels.

---

## 1.48.51 — 2026-10-09

### Added

- **The Squint icon beside selected text.** Select text in any app - drag
  across it, or double- or triple-click - and a small Squint logo appears
  by the end of the selection. Click it and the selection is translated,
  in the same card as Ctrl+Alt+C. It never takes the keyboard from the
  app you are in, and goes after a few seconds or when you click
  elsewhere. On a Mac the text is read straight from the app, so your
  clipboard is not touched. Turn it off in Settings › Behaviour ("Squint
  icon on selected text").

### Fixed

- **A quick tap of the shortcut opened hold-to-see.** With Ctrl and Cmd
  still resting on the keys for a moment after X, the tap was taken for
  a hold: the screen was frozen, the whole page translated, and the snip
  waited behind it - slow, and with the screen behind turned over. On a
  Mac, Squint is now told by the system when the shortcut is let go,
  which settles a tap from a hold for certain.
- **A snip could wait 30-45 seconds to be read** behind a reading of the
  whole screen done ahead of time. A snip's own reading now goes first.
- **A paragraph ending in a price was cut short** ("…lag bei etwa" /
  "2.500-3000€."): the figures were left out of the sentence and the
  translation ended in "…". They stay with their sentence now.
- **Prices lost their currency sign** in translation ("2.500-3000").
  It is put back.
- **Lists lost their dashes** part way down ("- New cables", then
  "The rear brake…"). A dash at the start of a list item is kept.
- **A line could be left in German** when an online engine handed it
  back nearly unchanged; it is now asked again, like a line handed back
  exactly unchanged.
- **Answers drawn against the wrong lines.** When an online engine
  merged some lines and split others, the count came out right and
  everything below was shifted by a line. That is now noticed and the
  page asked again.
- **"(none yet)" on a finished page.** The engine tag now names the
  engine that translated it.
- The log no longer fills with the same error thousands of times while
  the screen is asleep.

---

## 1.48.50 — 2026-10-06

### Added

- **Text at an angle is translated in place, at its angle.** A diagonal
  column heading over a table, a title set on a slant, a label running
  up a poster: each is now translated on its own and drawn back over
  itself at the same angle, in its own colours. A translation longer
  than the original runs further along the same slant, set a little
  smaller where it would leave the snipped area.

### Fixed

- **Slanted labels were joined into one sentence.** Neighbouring
  diagonal headings were read as one paragraph and translated as
  nonsense, in the wrong order, in a card beside the page. Each is now
  translated as a label of its own.
- **A large slanted title could be thrown away as a watermark.** Being
  big and at an angle is no longer enough; a watermark also has to be
  pale or repeated.
- **A snip of a table of numbers under a row of headings showed a card**
  instead of the translated page: the numbers, which are left as they
  are on purpose, were counted as lines the translation had missed.

---

## 1.48.49 — 2026-10-02

### Added

- **A small panel on the menu-bar icon (Mac) and the tray icon
  (Windows).** One click opens it: **Snip** and **Text** as two big
  buttons with their shortcuts on them, the language translations go
  into, and whether offline translation is ready (or how far its download
  has got). The gear opens Squint's window. Click anywhere else, press
  Esc or click the icon again to close it. The old menu is still there on
  a right click (Control-click on a Mac).
- **Sharp at every size.** The panel's icons are smoothed on both
  systems and follow the display's scaling on Windows (125%, 150%, 200%);
  on a Mac they are drawn at Retina resolution. Windows 11 rounds the
  panel's corners itself.
- **Text from the panel copies from the app you were in**, not from
  Squint: the keyboard is handed back to that app before the copy.

### Fixed

- A sentence pattern was written in a form newer Python versions warn
  about; it is now written the way they expect, with the same meaning.

---

## 1.48.48 — 2026-09-30

### Fixed

- **A paragraph whose first line mentioned a web address kept that line
  in the original** ("…der über shop.example, die App…"), and
  the rest was translated without its beginning ("It was damaged…"). A
  line is now left as it is only when it *is* an address (with a few
  words at most); a sentence that mentions one is translated, and the
  address in it is kept exactly.
- **Long lines ran off the right edge on the Mac.** The layout measured
  text in the system font and the overlay drew it in Helvetica Neue,
  which is wider. Both now use the same face, and no line is ever drawn
  wider than the space it was given.

- **Translate-selection showed an earlier translation instead of the text
  just selected** (on the Mac especially). When the shortcut's own copy
  did not go through, Squint fell back to whatever was on the clipboard -
  often the paragraph selected the time before - and translated that as if
  it were new. Now, if nothing new has been put on the clipboard since the
  last time the shortcut was used, it says the copy did not work and asks
  to select again, instead of showing old text. On the Mac it now also
  knows for certain whether the copy happened (as Windows already did).

## 1.48.47 — 2026-09-30

### Changed

- **Translate-selection (Ctrl+Alt+C) is back to the card**, and the card
  now fits its text: a short phrase gets a small card, a paragraph a larger
  one, nothing is cut off, and only a translation taller than two thirds
  of the screen scrolls. Drawing over the selection (1.48.46) took its
  colours from the selection highlight and broke paragraphs into lines;
  it is switched off.

### Fixed

- **The card cut off long Korean, Chinese and Japanese translations**
  after three lines: it counted each of those characters as one letter's
  width when it is drawn about two wide. It now measures the text as
  laid out.

## 1.48.46 — 2026-09-30

### Fixed

- **Translating into Chinese or Japanese left most of a paragraph
  untranslated.** Only the first line was covered with the translation;
  the rest stayed on the page in the original language. A paragraph's
  translation is shared over its lines, and it was shared by words -
  Chinese and Japanese have no spaces, so the first line took all of it and
  the others were taken for lines left as they were. Now shared by
  characters, and a line of a translated paragraph is never left showing.
- **Buttons, menu items and headings translated like dictionary words**
  ("Accueil" as "Welcome", "Home" as "Zuhause", "Buscar" as "Search for",
  "Verbergen" as "Whisper"). Short items are now translated as the labels
  they are - "Home", "Startseite", "Search", "Hide". Tested on 27 labels
  from seven languages into the other six.

### Changed

- **Translate-selection (Ctrl+Alt+C) draws the translation over the
  selected text**, the way a snip does, instead of in a card beside it.
  The card did not fit the text - a paragraph was cut off at three lines.
  Squint finds the selected text on the screen under the pointer and
  translates that area as if it had been snipped: same layout, same size
  as the original, Esc or a click away closes it. Where the text cannot be
  found on screen (it is in another window, or only on the clipboard),
  the card is shown as before.

## 1.48.45 — 2026-09-30

### Fixed

- **Snips took 6-9 seconds on some pages since 1.48.44** (the Italian and
  Japanese pages, Russian and Korean ones). The log showed why: reading the
  screen, not translating (translating took about 1.3 s). 1.48.44 asked the
  slower built-in reader for a second opinion on every small doubt about
  Windows' reading - 5-9 s on a 4K screen each time - and the read-ahead
  in the background did the same for every page you stopped on, keeping
  the processor busy. Now the built-in reader is asked only when Windows'
  reading is plainly rubbish, or when Windows may not have read the page
  at all (Chinese, Japanese or Korean with no pack for it) - never for a
  small doubt about an English, German or Italian page, on any PC. And the
  read-ahead never runs it: a page that needs it is read when you snip.
- **A time limit every snip is held to: 3 seconds at most**, on the laptops
  Squint is made for - the snipped area read in 0.8 s, the first words on
  screen in 1 s, all of it in 3 s. Each snip writes one line to the log
  with its times against these limits, marked OVER where one was missed,
  so a slow snip on any computer says at once which step was slow. The
  same limits are checked before every release.
- **Online help comes sooner:** when the offline model is still working
  after 1.5 s (it was 2.5 s), or will clearly take more than 2 s, Groq or
  Gemini are asked too, if you have a key.
- **Laying the translation out on the page is 3-5 times faster** (a dense
  page: 1.7 s to 0.3 s on the test machine), with exactly the same result.
- **Very long sentences** are split after a semicolon as well, so no single
  piece keeps the whole page waiting.
- **6-15 seconds a snip on a PC with several 4K screens** (a friend's
  PC, English pages into Korean). Its log: the reading started at the key
  press read all three screens with the slow built-in reader - 15-28 s -
  and every snip waited up to 6 s for it; an English page beside photos
  was taken for a page Windows had not read, because photos look like
  rows of text to that test; and a page prepared in the background after a
  cancelled snip (86 s of reading, 33 s of translating) shared the graphics
  chip with the snips after it. Now nothing read in the background uses
  the slow reader - a snip that needs it reads just its own area; the
  "not read" test only applies to readings with almost nothing in them;
  and a snip stops a page being prepared somewhere else.
- **A word before a footnote mark was kept back as a "code"**: "1 code
  could not be placed: Hausarrest." - "Hausarrest.[15]" looked like a code
  because of the mark's digits, and the word was held out of the
  translation. Footnote marks no longer do that.
- **Paragraphs with footnote marks in the middle of a line** ("…Professorin.[11]
  Bereits…") were cut into pieces at those lines and each piece translated
  on its own, in a different size.
- **Italian read by the Russian language pack** ("11 corso" for "Il
  corso", "Ilesonero" for "l'esonero"): where two packs read a line
  equally well, the pack of the page's language now wins, then one whose
  own alphabet is Latin - instead of whichever sorts last by name.
- **"い。", "す。" left under a translated paragraph**: the last line of a
  Japanese paragraph, a character or two long, was shorter than the lines
  above and so was not joined to them.
- **Long paragraphs were slow offline** (8-11 s for a page of three
  paragraphs). A paragraph went to the offline model as one request, and
  it writes one word after another, so the longest paragraph was the whole
  wait. Long paragraphs are now translated a few sentences at a time, side
  by side, and put back together - each piece still whole sentences, cut
  the same way every time, so a snip and hold-to-see still agree. On the
  test machine a page like that went from 112 s to 53 s; with a graphics
  chip, which writes more pieces at once, the gain is larger.
- **Zooming with the mouse wheel was laggy and jumpy.** The page was laid
  out again at every step of the wheel, on the thread that listens to the
  wheel, so each step froze the window while the next ones piled up. Now
  the wheel only sets the size; the page is laid out once, when the wheel
  stops, in the background, and swapped in.
- **The last line of a paragraph with a footnote mark ("…Kulturen.[6]")**
  was translated on its own, because the raised mark made that line look
  taller than the rest.

## 1.48.44 — 2026-09-30

### Fixed

- **Offline translation sets itself up.** It used to wait for someone to
  find Settings › Offline translation and press Download. Now Squint
  downloads it in the background the first time it starts (or the first
  time after this update), and switches it on once it has arrived and
  passed a test translation. Online translation covers the wait. Switching
  it off, pausing or removing it in Settings is respected, and nothing is
  downloaded on a disk with less than 3 GB free.
- **Text already in your language is left alone.** Asked to translate
  German into German, the offline model rewrote it - sometimes changing the
  meaning - and took as long as a real translation. Now the parts of a page
  already in the language you read are kept exactly as they are, at no cost
  (a German page into German: 17 s → under 1 s on the test machine).
- **Languages the offline model does not write well** (Swedish, Norwegian,
  Danish, Finnish, Hungarian, Slovak, Greek and others) are translated
  online instead. Asked for them, the offline model wrote the wrong
  language or the wrong meaning. Its 30-odd languages - English, Chinese,
  Japanese, Korean, German, French, Spanish, Italian, Portuguese, Russian,
  Arabic, Hindi and more - stay offline, into and out of each other.
- **Chinese, Japanese or Korean on a PC without that Windows language pack
  came back as rubbish** ("L-i*4Dfi7,", "fifi A fifi") when no online key was
  set. The reader built into Squint for these languages was only asked when
  an online reader was also set up. It is now asked whenever Windows cannot
  read the page, with or without a key.
- **The first Korean page on Windows waited for a download** of the reader's
  Korean model. It is now fetched in the background when Squint starts, so
  Korean reads offline like Chinese and Japanese.
- **Single words and short labels left untranslated on German (and other
  Latin-script) pages** - "Postleitzahl", "Gesellschaftsform",
  "Fahrradhändler", "Datenschutzerklärung". Long compound words and words
  with umlauts were mistaken for misread rubbish and thrown away before
  translation. They are now kept and translated.
- **Umlauts read as digits or plain letters** ("0ber uns", "pers6nlich",
  "fur"): where two language packs read a line equally well, the reading
  with the right letters now wins, instead of the English one.
- **Specks of "text" read off photos** (a few quote marks and strokes) are
  no longer translated and drawn over the picture.

## 1.48.43 — 2026-09-30

### Fixed

- **Tested on 20 real websites in seven languages** (news, encyclopedia,
  shopping, government) with the offline model, and fixed what they showed:
  - **Lines read straight across two columns or panels** (a sidebar item
    joined to the article beside it, a caption joined to the text next to
    it) are cut apart, so they are no longer translated as one nonsense
    sentence and drawn across both.
  - **Menus and tab bars** read as one line are cut into their items,
    instead of being translated as one sentence ("Care for Ukraine: Inside
    and Outside. Economy, Knowledge, ...").
  - **Bulleted headline lists** ("・..." on Japanese and Chinese pages) and
    **menus of short items** are no longer joined into one paragraph.
  - **A heading in another colour and size** is no longer taken for the
    first line of the paragraph under it.
  - **A translation never paints over the rest of the page**: it stops at
    the edge of a panel or infobox and at a picture, icon or button below
    it, and takes a smaller size instead. On the test pages, covers
    painting over other content went from 113 cases to 29.
  - **Text on the same page comes back at one size per column**: a sidebar
    menu is no longer made smaller because the article beside it had to
    shrink. A single line is never made smaller just because its box is
    tight.
  - **Text written top to bottom** (rotated labels) is left as it is
    instead of being set one letter to a line.
- **Tables:** a cell's translation now uses the empty space beside it, up
  to the next cell, instead of being squeezed into the original's width -
  no more "Facili / ty", "Tim / e", and no rows pushed out of line.
- **Words are never cut in two;** the text gets a little smaller instead.
- **A character left showing at the edge of a translation** (the first
  character of a line the reader's box missed, or the tails of g, j, p
  under a line) is now covered.
- **Grey bars reaching out past the edge of a card or panel** are gone:
  thin borders now stop the cover.
- **Numbers, times and codes kept as they are** are left exactly as on the
  page instead of being redrawn in another typeface.
- **Paragraphs with long words** (German especially) stay one paragraph
  instead of being translated line by line; a two-line heading beside
  another column is no longer split into two "table cells"; the first line
  of a paragraph is no longer translated on its own.
- **The same label came back differently in a snip and in hold-to-see**
  ("Building" and "East", "Summary" and "Overview"): labels are now
  translated one at a time, on their own, so the same label gets the same
  answer however much of the page is taken. Checked on seven pages: every
  paragraph and label in a snip now reads exactly as in the whole page.
- **The offline model could take most of the computer's memory** as it
  kept earlier requests to reuse - up to 8 GB, enough to freeze an 8 GB
  laptop. The whole engine now stays under 4 GB. Speed is unchanged.
- **Full pages on laptops without a graphics chip the offline model can
  use** (most Windows laptops): Groq or Gemini are now asked straight away
  on a full page, instead of after 2.5 s. Macs, and short snips everywhere,
  are unchanged.
- **The page appears faster:** arranging the translations on the page takes
  about a third of the time it did, and showing translations as they finish
  no longer slows the translating down.
- **The first hold on a new page snipped instead of showing the page
  translated.** The letter of the shortcut could read as let go while it
  was held; a snip now needs X to have been seen down and then let go.

## 1.48.42 — 2026-09-29

### Added

- **The translation appears as it is done**, from the top left of the snip
  or page down to the bottom right, instead of all at once at the end - in
  a snip and in hold-to-see.

### Changed

- **Faster:** numbers, prices, dates, codes, emails and web addresses are
  kept as they are instead of being sent to the engine; text that appears
  several times on a page is translated once; short labels go to the
  offline engine several at a time; dense pages go to Groq and Gemini as
  several requests at once; Gemini no longer "thinks" before answering;
  on Windows a 4K screen is read at half size when its text is large
  enough.
- **Better:** a short label is translated with the items around it on the
  page as context, and very small text is read enlarged.
- The offline engine no longer asks twice for an answer left in the
  original language - it now answers the same text the same way, so the
  second try only cost time.

### Fixed

- **Pages in several languages were only partly translated.** The screen
  was read in each installed language and one reading won for the whole
  page, so the other languages were misread into nonsense or skipped. Now
  each part of the page is taken from the language that reads it in its own
  script - on Windows and on the Mac.
- **The shortcut:** let go of X within 0.3 s and it snips, even with Ctrl and
  Alt (Cmd) still held. Hold X for hold-to-see; let go of X and it closes;
  tap X again straight away, still holding Ctrl and Alt, to keep it.
- **Remembered translations never outlive a settings change**, and are kept
  separately for each engine choice.

- **Snip and hold-to-see could translate the same page differently.** Two
  causes, both fixed at the root:
  - They read the screen separately, so a word could be read two ways
    (one letter mistaken for another) and was then translated two ways. A
    snip now waits for the reading of the page begun at the key press, the
    same one hold-to-see uses, and reads only the lines its box cuts.
  - The offline engine picked words with a little randomness, so the same
    sentence could come back worded differently. It now always gives the
    same answer for the same text.

## 1.48.41 — 2026-09-28

### Added

- **Cancel a snip any time with Esc** - while it reads or translates, in
  whichever app you are - or click the "Translating… ×" label, or press the
  snip shortcut again (which starts a new snip).
- **Nothing cancelled is wasted.** A cancelled snip finishes in the
  background: snip the same area again and it appears at once; snip much
  the same area and it waits for that work instead of starting over. A snip
  dismissed with Esc before drawing a box reads and translates the page in
  front quietly, on this computer only, so holding the key or snipping there
  next is quick. Hold-to-see let go early also finishes and is kept.
- **Snips reuse more of what was already read**: the last snip's reading,
  and the page read ahead even when the box cuts a few lines (only those
  rows are read again). Whole sentences translated in the last 10 minutes
  by the same engine are not sent again; short labels are always
  translated fresh with their page.

### Changed

- **Automatic now translates on this computer first** whenever the offline
  engine is set up, with or without keys, so every page is translated by the
  same engine. When the offline engine is slow on a page (still busy after
  2.5 s, or slow on recent pages), Groq, then Gemini, is asked as well and
  the first complete answer is shown. They also take over when it cannot
  answer. An engine out of quota is skipped.

### Fixed

- **Pages with a moving banner were read over and over.** Read ahead read a
  busy page whole again every few seconds (6 seconds of work each time), and
  a snip could never use it because the banner had moved on. Now only the
  rows that changed are read again, in the background and at the snip.
- **One empty line cost a snip 6 seconds.** When the online engine left a
  line out, the snip waited for the offline engine to finish the whole page.
  Now only the missing lines are asked for, for at most 2.5 seconds.
- **Hold-to-see let go before it was ready** now says so in the log, with
  how long it would have taken.
- **Copied text failed with the offline engine** ("Hy-MT2 on this computer
  could not translate this: returned 24 lines for 27"). Several lines are
  now translated sentence by sentence, the way a snip is.
- **Chinese and Japanese list items were run together.** Each item ending
  in 。 or ； was merged with the next and the translation spread over the
  lines by width, so "1." carried the end of one item and the start of the
  next. Each item now stays on its own line.
- **A heading could come back holding the paragraph under it**, drawn at
  heading size over the page, with the paragraph translated again below
  it. An answer far longer than its text, or empty, is now asked for
  again on its own.
- **Notes the engine wrote into a translation** ("[unclear - possibly
  referring to …]") are taken out.
- **Edges of large, bold headings showed round the translation.** The
  cover over the original now grows with the size of the text.
- **Some snips took 3–6 seconds to translate** while others of the same
  size took under one. Lines the engine handed back untranslated (names,
  short English phrases) were asked for again one after another; they are
  now asked for together.
- **Busy pages came out garbled with the offline engine** - menus and
  labels merged, "Quot ation" / "Foru m", model names lost. The offline
  engine joined separate labels into one "sentence" and spread the answer
  back over the wrong boxes. Each paragraph, label and cell is now
  translated on its own, as with Google.
- **German pages were sent to the cloud reader about one snip in ten** -
  a long compound word ("Rechtsschutzversicherung") looked like a
  misreading. That snip was over a second slower and was read differently
  from the same page read on this computer, so snip and hold to see
  disagreed. One odd word in a page of ordinary ones no longer counts.

### Changed

- **Snip and hold to see start reading the page the moment the shortcut
  goes down**, before it is known whether it is a tap or a hold. By the
  time you have dragged a box, or held for a moment, the page is mostly
  read already. On this computer only, whether read ahead is on or not.
- **Read ahead reads only the page in front**, not the whole screen: on a
  4K screen that took several seconds each time, and slowed the snip it
  overlapped.

## 1.48.40 — 2026-09-28

### Fixed

- **Read ahead sent pages to the cloud reader** on Windows when Windows'
  own reader was unsure of a page. It now reads on this computer only,
  as promised.
- **Hold to see did not use what read ahead had read.** It now does.
- **Read ahead no longer starts a new reading while you snip or hold**,
  so the reading you asked for has the computer to itself.
- **Read ahead read Squint's own translations as a new page** on Windows,
  where a translation drawn over the page does not always take the front.
  It now waits while anything of Squint's is on screen.
- **A snip could wait 1.5 s for a background reading that had only just
  begun.** On a large screen those take seconds; the snip now reads for
  itself instead of waiting.

## 1.48.39 — 2026-09-28

### Added

- **Read ahead** (Settings › Behaviour, off until switched on). When you
  stop on a page, Squint reads its text in the background. When you then
  snip or hold, the reading is already done and only the translation is
  left to do. Used only when the screen there is exactly what was read;
  otherwise it reads as before. Nothing is translated ahead and nothing
  leaves the computer.

## 1.48.38 — 2026-09-27

### Changed

- **Hold to see now gives exactly the snip's result.** It picks the area
  you would have snipped: the page or document of the window in front on
  the monitor your pointer is on, without its tabs, toolbars and
  bookmarks. Then it does precisely what a snip of that area does: the
  same reading, the same translation and the same layout and sizes. The page appears in
  one go, like a snip. Looking again at an unchanged page is instant.

### Fixed

- **Hold to see translated only part of some documents**, such as a PDF
  preview, and translated lines in halves.

## 1.48.37 — 2026-09-27

### Changed

- **The snip shortcut is now Ctrl+Cmd+X on a Mac and Ctrl+Alt+X on
  Windows.**
  - Tap it to snip.
  - Hold it to see the whole screen translated; let go to hide it.
  - Tap X again while holding to keep it up, until Esc or a click.
  If you had changed the shortcut yourself, yours is kept.

### Fixed

- **Holding the shortcut snipped instead of showing the page translated**
  on a Mac, the first time on every page. It now shows the translation
  on the first hold.
- **Hold to see keeps the translation inside the original lines.** Each
  paragraph is set in the width it had, instead of running across the
  empty part of the page and off the edge of the screen.
- **The bookmarks bar and tabs of Chrome, Brave and Edge** are recognised
  as part of the browser, not the page, and left alone.
- **Lines cut off by the top or bottom of the window** are left as they
  are instead of coming out as nonsense.

## 1.48.36 — 2026-09-27

### Changed

- **One shortcut for snip and hold to see** (then Ctrl+Cmd+T on a Mac,
  Ctrl+Alt+T on Windows):
  - tap it to snip, as before;
  - hold it to see the whole screen translated, and let go to hide it;
  - press T twice while holding to keep it up, until Esc or a click.
  Ctrl+Alt+X is no longer used.

### Fixed

- **Hold to see now draws exactly like a snip.** It lays out at the
  screen's full resolution and draws the text sharp, as the snip does.
  Small print no longer comes out tiny, and the original no longer shows
  through beside the translation.

## 1.48.35 — 2026-09-27

### Fixed

- **Squint's window flashed for a moment on every Ctrl+Alt+X** on a Mac.
  It now stays out of sight while hold to see is up and goes back behind
  the app you were in afterwards.
- **Hold to see now looks like a snip of the same page.** Text stays
  within its own column at the same size, instead of spreading across
  the empty part of the window.
- **Hold to see translated the tabs and bookmarks after a snip.** It now
  always works on the window under the pointer, even when Squint was the
  last app used.
- **Offline translation became slow in 1.48.34.** Running 16 texts at
  once overloaded the graphics chip: now 8 (6 on less memory). The offline
  engine running in the background beside an online one takes two at a
  time, so it stops as soon as the online answer arrives.

## 1.48.34 — 2026-09-27

### Changed

- **Hold to see translates only the content.** The page in a browser, the
  document in a viewer or editor. Tabs, address bar, bookmarks, the menu
  bar, the Dock and the taskbar are left as they are, and the content
  comes first.
- **Tables keep their rows.** Each cell is translated and placed on its
  own row; labels no longer slide down a row or run below the table.
- **Text stays inside the window.** Where a translation is longer, the
  size steps down instead of running past the bottom of the window.
- **The app you were in stays active.** After hold to see closes, the app
  underneath is in front again.

- **Hold to see is much faster on busy pages.** Only the content is
  read, the page is laid out at screen size instead of Retina size, and
  it fills in in at most four steps. A page that took nine seconds should
  now take two or three.
- **The offline engine translates up to 16 pieces of text at once instead
  of three**, using the graphics chip: 16 on computers with 16 GB of
  memory or more, 10 on less, 4 without a usable graphics chip. Snips and
  hold to see both get faster offline.
- **Lines already in English are left alone** by hold to see when
  translating into English, and are not sent to the engine.

### Fixed

- **Pressing Ctrl+Alt+X could open Squint's main window.**

## 1.48.33 — 2026-09-27

### Added

- **Hold to see (Ctrl+Alt+X).** Hold it and the whole screen the pointer
  is on shows in your language, in place, filling in top to bottom and
  column by column. Let go and it is gone. Press X twice while holding
  Ctrl+Alt (Ctrl+Alt+X X) to keep it up until Esc, a click or Ctrl+Alt+X
  again. Looking again at the same screen is
  instant. Works with every engine, offline included. Change the shortcut
  in Settings › Shortcuts.

### Fixed

- **Squint showed a blank page icon in the Mac Dock.** It now always shows
  its own icon.

### Removed

- **"Welcome screens · Show again"** in Settings. Language and key are set
  in Settings directly.

## 1.48.32 — 2026-09-27

### Fixed

- **macOS could list Squint as "python3.12" in its permission lists**, so
  switching on "Squint" did nothing until the app was restarted several
  times. The Mac app now always starts as Squint. Takes effect with the
  next Mac installer.

## 1.48.31 — 2026-09-27

### Fixed

- **After the 1.48.30 stability fix, the Mac app could not start**
  ("bad argument type for built-in operation"). Pictures were handed to
  the new toolkit in a way it does not support; they now go a way every
  version reads.
- **If a toolkit change ever stops Squint from starting again**, Squint
  undoes it by itself and starts normally the next time.

## 1.48.30 — 2026-09-27

### Fixed

- **The Mac app could quit when a screen was plugged in or out**, the
  resolution changed, or the Mac woke with a monitor attached. This came
  from the newer window toolkit the Mac app was built with. The update
  replaces it with the stable version Windows already uses, in the
  background (about 20 MB), checks it works, and says "Stability fix
  installed · Restart Squint →" at the top of the window. If anything goes
  wrong, the old toolkit stays and Squint carries on as before.
- **A pointing-hand cursor sometimes stayed on screen** after leaving the
  "Advanced translation" and "More reading languages" rows.

### Changed

- **Future Mac installers are built with the stable toolkit.**

## 1.48.29 — 2026-09-26

### Fixed

- **Pages would not scroll with a Mac trackpad** in the Mac app — Settings,
  Updates, Support, the result card and the guides. The app's newer
  window toolkit reports a trackpad differently, and Squint was not
  listening for it.
- **The snip's "Reading text…" area turned black on a Mac.** The same
  toolkit draws see-through windows as black; the frame is now drawn
  from solid edges instead.
- **Offline translations of wrapped text read badly.** A sentence that ran
  over several lines was translated a line at a time — "also in" and "a
  perfect condition" apart came back as "a completely bad state". Lines
  are now joined into their sentences, translated whole and spread back.
- **"Codes could not be placed: 10-fach, 1990er"** — ordinary words with a
  number in them are no longer treated as reference codes.
- **Check now in Updates was always grey** before the offline model was
  downloaded. It now says Set up and takes you to the download.

## 1.48.28 — 2026-09-26

### Fixed

- **Mac permissions showed "Enable" although they were switched on.** The
  switch in System Settings belonged to an earlier copy of Squint, and
  macOS no longer honoured it for this one. Pressing Enable now clears that
  old entry first, so the switch you flip is for the Squint you are running.
  (Once: press Enable on each, flip the switch again.)
- **A permission that is on now shows a grey "Enabled"** button with a
  tick, and the checklist and the front-page reminder update whenever the
  window is opened.

### Removed

- **The welcome screen.** Keys, languages and permissions all have their
  place in the main window now. The welcome window could also sit over
  Settings and stop it scrolling.

## 1.48.27 — 2026-09-26

### Changed

- **Mac permissions in two steps.** Settings › Shortcuts has a short
  checklist: ① Copy selected text (Accessibility) and ② Snip the screen
  (Screen Recording). Press Enable and Squint opens the right page of
  System Settings with Squint already in the list — flip its switch. Squint
  notices the first one by itself and opens the second page straight away;
  after that, one restart (macOS offers Quit & Reopen, or press Restart
  Squint). macOS allows only you to flip the switches; everything else is
  done for you.
- **A reminder on the front page** — "Two permissions to switch on · Set
  up →" — while either is missing on a Mac. It leads straight to the
  checklist.

## 1.48.26 — 2026-09-26

### Fixed

- **On a Mac, the Squint window flashed over the page** for a moment when
  the translation card appeared after Ctrl+Cmd+C. It is now kept invisible
  while macOS brings the app forward, and shown again once it is back
  behind the page.

## 1.48.25 — 2026-09-26

### Changed

- **Translating copied text (Ctrl+Alt+C) now looks like a snip.** The small
  grey spinner is replaced by the snip's blue "Translating…" pill, with the
  start of the copied text under it and the same blue light sweeping across
  it. It appears by the mouse pointer, and the result card takes its place.

## 1.48.24 — 2026-09-25

### Fixed

- **Dates and amounts in English, German and other Latin-alphabet text came
  out garbled.** "on 23rd Sep" became "am 1. September (23rd)", and
  "44.17EUR" stayed as it was instead of "44,17 EUR". Squint was hiding
  numbers from the engine to protect them — a safeguard meant for Chinese,
  Japanese and Korean text. It now does that only for those languages, so
  the engine sees the whole sentence and writes dates and amounts the way
  the other language does.
- **Translations read more naturally.** The AI engines are now asked for
  grammatical wording in the tone of the original — a polite letter stays
  a polite letter — and to write dates and amounts the target language's
  way.
- **"No offline model for English yet" on the front page.** A leftover
  from the older one-language-at-a-time downloads; the offline model covers
  every language, so it is gone.

### Changed

- **Typed and copied text now works like a snip.** Gemini or Groq answer
  first; with a key, the offline model translates the same text alongside
  and is used if the online answer does not come — no internet, or both
  out for the day. With no key, the offline model translates first.
- **The text box grows as you type**, up to about eight lines, then
  scrolls inside. The translation box grows with it, and both go back to
  their usual size when cleared.

## 1.48.23 — 2026-09-25

### Fixed

- **The offline download failed on a Mac with "HTTP Error 404".** The Mac
  version of the offline engine is published in a different format from
  the Windows one, and the backup address asked for the wrong one. Squint
  now finds the right file and checks it exists before downloading. It
  also no longer depends on a lookup that can run out when many people
  share one internet connection.

### Changed

- **Older offline languages can no longer be added once Hy-MT2 is
  downloaded**, since it covers all of them. Ones already installed stay
  as a backup and can be removed to free the space.

## 1.48.22 — 2026-09-25

### Added

- **Updates has its own page**, between Settings and Support. It holds app
  updates and offline model updates side by side.
- **A red dot on Updates** when a new app version or a new offline model is
  available. It stays until the update is installed.
- **Offline model updates.** Once a week Squint checks whether a newer
  version of the offline model has been published. Nothing downloads until
  you press Update; the old model keeps working while the new one
  downloads, and is replaced only once the new one has arrived whole and
  checked. The offline engine is refreshed at the same time.

### Changed

- **App updates are checked daily while Squint stays open**, not only at
  start-up.
- **The older one-language-at-a-time offline downloads are folded away**
  under "Older offline languages" in Settings, since the offline model now
  covers every language. They can still be removed from there to free
  space.

## 1.48.21 — 2026-09-25

### Changed

- **PDF translation is much faster.** A PDF's paragraphs are now sent
  together, a page at a time, instead of one by one — online and on this
  computer alike. Paragraphs an engine leaves out are asked again on
  their own.

## 1.48.20 — 2026-09-25

### Changed

- **Offline translation uses the graphics chip.** On Windows the offline
  engine now runs the model on the graphics chip (built-in or separate),
  and on a Mac on its own graphics as well. It was running on the processor
  only. Squint swaps the engine by itself in the background (about 30 MB);
  the model is not downloaded again. If the graphics driver will not run
  it, Squint goes back to the processor and remembers that. Settings says
  which one it is using.

- **"Advanced translation" and "More reading languages" are easier to
  see**: each is now a tinted row with a Show button instead of a small
  text link.

### Fixed

- **Automatic sent snips to the offline model while Gemini was working.**
  After "On this computer only" had been used once, Automatic kept asking
  the offline model first: about ten seconds a snip.
- **Snips of German, French and other Latin-script pages were slow.** A
  page Windows read with one doubtful word was read twice more on the
  computer before being checked online. It now goes straight to the online
  check, as it did before.

### Added

- **Online and offline work together under Automatic.** With a Gemini,
  Groq, Google or DeepL key, the online engine answers and is shown; the
  offline model translates the same snip in the background at the same
  time, so if the online answer fails, or leaves lines out, the offline
  translation is already there instead of starting from nothing. With no
  key at all, the offline model translates first. When Gemini's answer
  cannot be lined up with the snip, Groq is asked next.

## 1.48.19 — 2026-09-25

### Changed

- **Offline snips are faster.** A snip is translated in small groups of
  lines side by side instead of one long request, the offline model starts
  loading as soon as you begin a snip, and it uses the processor better.
  Squint's log now records how long each offline snip took.
- **Windows reading languages are folded away** under "More reading
  languages". PaddleOCR already reads Chinese, Japanese, Korean and
  English; the Windows packs are for the other scripts.

### Fixed

- **Settings said the offline engine was not installed** while Hy-MT2 was
  installed and translating.

### Removed

- **The Compact offline model.** It does not run on this computer's offline
  engine. Standard (about 1.1 GB) is now the only choice; a Compact
  download is deleted to free the space.

## 1.48.18 — 2026-09-25

### Fixed

- **"On this computer only" could still send a snip to Google.** When the
  offline model could not answer, a snip fell through to the Google key. It
  now stays on the computer and says why it could not translate.
- **Offline translation said "Ready" as soon as the download finished**,
  whether or not the model runs here. Squint now tests it after downloading
  (and with the new Test button) and says whether it works — or, if Compact
  does not run on this computer, to choose Standard.
- **The Translating list kept saying "(needs the offline engine)"** after the
  model was ready.

### Added

- **Snips show which engine translated them**, in a small tag in the corner,
  as the result card already did.

## 1.48.17 — 2026-09-25

### Fixed

- **Offline translation stopped with "no llama.cpp build for this system".**
  The engine's newest release often has no files yet for the first minutes;
  Squint now takes the newest release that has them, and a known-good one if
  it cannot look.

## 1.48.16 — 2026-09-25

### Added

- **Offline translation with Hy-MT2**, Tencent's open translation model, run
  on this computer: free, private, no key, 33 languages, and it works with no
  internet. Switch it on under Settings › Offline translation and choose
  Standard (about 1.1 GB, recommended) or Compact (about 600 MB). It
  downloads in the background, can be paused and carries on where it
  stopped. Squint uses it when Gemini and Groq cannot answer, and for
  everything under "On this computer only".

## 1.48.15 — 2026-09-25

### Fixed

- **Updating to 1.48.14 on Windows could not install PaddleOCR** ("Cannot
  import 'setuptools.build_meta'"). The one package it failed on now comes
  with Squint, and anything else that needs building is retried in a way
  Squint's own Python can manage. Squint finishes the install in the
  background the next time it opens.

## 1.48.14 — 2026-09-25

### Added

- **Windows reads Chinese, Japanese and Korean on its own.** PaddleOCR is now
  part of the Windows install: no language pack, no key and no internet
  needed. Windows' own reader still goes first; the cloud is only asked when
  neither can read the text. The installer is larger as a result.
- **A picture guide for the Groq key**, behind "How?" on the Groq row.

### Fixed

- **A snip of a headline and a paragraph could come back half translated.**
  A language model sometimes handed a line back unchanged when it came with
  others. Lines returned untranslated are now asked again on their own.
- **Ctrl+Cmd+C on a Mac brought Squint's window to the front** along with
  the card. The window now stays where it was.
- **A strip of the scan could stay on screen** after a snip finished, until
  the next click.

### Changed

- **Every key has its own dot.** Test connection now checks each key on its
  own service and shows green, red or amber beside it, with the reason for any
  that fail. The dots are still there the next time Settings opens.
- **Settings shows the two free keys first:** Gemini and Groq, each with
  "Get free key" and "How?". Google and DeepL, which need a card, sit under
  "Advanced translation", which opens and closes; it starts open for anyone
  who already has one of those keys.
- **Services are listed alphabetically** in Settings and under Translating.

## 1.48.13 — 2026-09-24

### Added

- **Groq, a second free key with no card.** Sign in at Groq, press Create API
  Key and paste it into Settings. It translates quickly with an open language
  model and backs up Gemini when Gemini is slow or out of its daily allowance.
  It can also be chosen on its own under Translating.

## 1.48.12 — 2026-09-24

### Added

- **Squint says when Google's free trial has ended.** Google stops a key when
  its 90-day trial closes. Squint now shows what happened with a button to
  Google's Billing page, where one Upgrade makes the same key work again. It
  translates with Gemini or the free services in the meantime.
- **A reminder before the trial ends**, once, about two weeks before, unless
  you have marked the account as upgraded.

### Changed

- **The Google setup window follows the order the console needs:** project and
  card, Cloud Translation, Cloud Vision, then the key, and finally the upgrade
  that keeps it working. A new step-by-step picture guide matches it.

## 1.48.11 — 2026-09-24

### Added

- **The Google setup window has the picture guide.** A card at the top shows
  a preview of the step-by-step guide and opens it beside the checklist, the
  same way the Gemini guide opens.

## 1.48.10 — 2026-09-24

### Fixed

- **Chinese text on a picture was read as Korean** and translated as Korean,
  into nonsense. Each language's reading is now judged by its own script, and
  a Korean reading made of syllables Korean hardly uses is set aside.
- **Snips of slides and product pages came back as a card** instead of the
  translation in place. Text on pictures is now translated in place like any
  other text.
- **A snip of many lines sent one request per line** to Google. With a Google
  key it now sends them all in one request, and translating is much faster.
- **A resting service is asked anyway** when everything else has failed,
  rather than failing without asking.

## 1.48.9 — 2026-09-24

### Fixed

- **Every snip failed with a list of services "rested after" an error.** One
  failed answer put a service to rest for minutes, and a resting service was
  not asked at all — so once each had failed once, nothing was tried again.
  If everything is resting, each is now asked once anyway, and a rejected
  request no longer rests a service that is working.
- **Errors now say what the service said**, such as "API key not valid",
  instead of only a number.

### Changed

- **With a Gemini key, Gemini leads every snip**, raced against Google with a
  three-second head start. On the Automatic setting it used to be tried last.

## 1.48.8 — 2026-09-24

### Changed

- **Translation no longer waits on one engine.** With a Gemini key, Gemini
  and Google are asked at the same time. Gemini's answer is used if it
  arrives within three seconds; otherwise Google's is used the moment it is
  in. If Gemini's answer cannot be used, Google's is already there.
- **The plainest translation services are no longer used automatically.**
  A clear "could not translate" is shown instead of a wrong translation you
  cannot tell is wrong. They can still be chosen by name.
- **The snipped area shows that it is working.** It is tinted, a light
  sweeps across it, and a label on its edge says whether it is reading or
  translating — instead of a small pill by the cursor.
- **A new version is easier to spot.** Settings shows the current and the
  new version side by side, and the release notes are no longer cut off.

### Fixed

- **Times came back spaced out** ("07: 00") when the page wrote the colon
  in a Chinese font. They are now put back as written.
- **Section headings numbered 一、二、三 kept a stray mark** when the reader
  took the numeral for a dash. They are recognised and numbered I., II., III.
- **Requests that send text could still stall** on a connection a firewall
  had quietly dropped. They now always use a fresh connection after a pause.

## 1.48.7 — 2026-09-24

### Fixed

- **The first snip could take over ten seconds longer than the rest.** Some
  networks — office firewalls especially — silently drop a connection that
  has been idle for a while, and Squint waited its full timeout on the dead
  connection before trying a new one. It now gives up on a quiet reused
  connection after two seconds and sends the request again on a fresh one,
  and stops reusing connections sooner.
- **A startup error from the home page animation**, logged when the
  animation ticked before the page was laid out.

## 1.48.6 — 2026-09-24

### Added

- **A Windows installer.** One file installs Squint with its own copy of
  Python and everything it needs — nothing else to install, no administrator
  rights, and nothing downloaded while installing. It prepares the app for
  first use while the installer is still open, and starts Squint when you
  sign in, so the first translation is not the slow one. In-app updates work
  as before.
- **Tools for a Mac disk image**, built on a Mac, with the same approach.

### Changed

- **Updates is now the first card in Settings**, so checking for a new build
  does not mean scrolling to the end.
- **The glossary card is hidden from Settings for now.** The glossary itself
  still applies to every translation.
- **New installs start in light mode**, with text replaced in place, closing
  on click-away, starting at sign-in, and copying to the clipboard and
  showing the detected text both off. Existing settings are kept.
- **"Start at sign-in" is now really on when the switch says so.** The switch
  also reflects an entry made by the installer.

## 1.48.5 — 2026-09-23

### Fixed

- **Numbered points lost their numbers.** On Chinese text numbered "1、" "2、",
  the number moved to the end of the sentence or was read as part of it —
  "2、" followed by a noun came back as "2 of" that noun. Section numerals
  一、二、三 were left untranslated, glued to the heading, or renumbered. The
  numbering is now kept out of the translation and put back in front: "1.",
  "2.", and "I.", "II.", "III." for sections. Chinese and Japanese keep the
  original markers.
- **Phone numbers and times came back spaced out** — "010 - 12345678",
  "20: 00 - 23: 00". They are now put back exactly as written, including when
  the number is written straight onto the words around it.
- **Korean dates** came back as "(09-18)". They now read "9월 18일".
- **Short lines wrapped halfway across an empty page** wherever a faint
  watermark crossed the space to their right. A watermark no longer counts as
  something in the way; panels, rules and real text still do.

## 1.48.4 — 2026-09-23

### Fixed

- **The end of a paragraph came out a word to a line.** On tightly set text —
  Chinese especially — the last line of every paragraph was split off and
  translated on its own. It starts in the middle of a word, so it came back as
  a fragment that repeated the paragraph above, stacked one word per line in a
  narrow box. A Korean reader took it for bad word spacing; the spacing was
  fine. Paragraphs now keep their last line, and a numbered point's heading
  stays separate from the text under it.
- **Seat layouts like 2+2+3 were rewritten** — one came back as "(2, 2, 3)".
  They are now treated as codes and kept exactly as written.
- **Numbered points "1." came back as "1,".** The number is put back the way it
  was.
- **In Korean, a particle came loose from the code in front of it** — "N90 는"
  instead of "N90는". The space is removed.
- **A rare crash** if the window was rebuilt — for example by switching theme —
  while Squint was installing packages in the background.

### Changed

- **The first translation after starting Squint is much faster**, especially on
  a new computer. The libraries translation needs are loaded quietly in the
  background once the window is open, and the connection to the translation
  service is opened in advance, instead of all of that happening the first time
  you press the shortcut.

---

## 1.48.3 — 2026-09-15

### Fixed

- **Typing anything removed the only way to open a file.** The upload box
  disappeared the moment there was text in the field above it — and since the
  box is the file button, that left no way to open a file at all. It now shrinks
  to a single line instead of going away.
- **Clearing the text did not bring it back.** The box was only ever restored
  when a key was released, and clearing isn't typing — so once a box had had a
  word in it, the file button stayed gone for the rest of the session.
- **The character counter did not reset either**, for the same reason: it still
  read "12 / 10,000" over an empty box.
- **A translation that was still running could refill a box you had just
  cleared.** It arrived whenever it arrived and wrote itself in regardless, so
  clearing seemed to half work, and only sometimes. A result now only lands if
  the box is still about the text it was given.

---

## 1.48.2 — 2026-09-15

### Fixed

- **Drag and drop, for real this time.** The extension it needs was added in
  1.48.0 and never installed, twice over: updating to 1.48.0 ran the old
  updater, which told you to run setup and then restarted before you could read
  it; updating to 1.48.1 ran the fixed updater, which only installs when the
  package list *changes* — and between 1.48.0 and 1.48.1 it hadn't. A machine in
  that state could not be repaired by any later update, because the thing being
  checked had stopped changing. Squint now checks whether the packages are
  actually **there**, every time it starts, and installs anything missing. Once
  the extension is in, the box accepts drops immediately — no restart.
- **The progress bar was still the wrong shape**: its ends were cut off at an
  angle instead of rounded. The bar now draws itself rather than going through
  the shape code the rest of the window shares, and its ends measure within half
  a pixel of a true half-circle at every size.
- **The bar was cut off by a short box** instead of fitting into it. It gets
  shorter now, rather than having its top and bottom sliced away.

### Changed

- **Download is its own button under the box**, instead of the progress bar
  turning into it. The bar fills and finishes full — it says how the work went;
  the button says what to do with the result.

---

## 1.48.1 — 2026-09-15

### Fixed

- **Drag and drop still did not work after updating to 1.48.0**, and the update
  itself is why. When a build needs a package the previous one did not, the app
  used to show "run setup once after it restarts" in a status line and then
  restart less than half a second later — so the sentence was gone before it
  could be read, and nothing ever installed the package. 1.48.0 was the first
  release in a long time to add one, so the drag-and-drop fix it shipped did
  nothing for anyone who updated from inside the app. The updater installs the
  packages now, and if that fails it says so and stays put rather than
  restarting over its own message. **This update will take a minute longer than
  usual for that reason, and drag and drop works once it is done.**
- **The progress bar was drawn wrong** — a tall narrow slab at the start, and a
  shape with a squared-off end further along. Two causes. Its rounding was
  capped by its own width, so a short fill had almost no rounding at all; and
  the pictures it was drawn from were being thrown away while still on screen,
  because the bar never held on to them and the shared store they came from is
  limited and drops the oldest to make room — which the bar itself kept filling
  as it grew. It holds them now, and the fill keeps the bar's rounding the whole
  way across: a circle at its smallest, a stadium after that.
- **The box said "Drag & drop an image" on machines where dropping a file does
  nothing.** Where the extension that provides it is missing, it now says "Click
  to upload an image or PDF" — and either way it records which in the log.

### Added

- **A ✕ to take a file back out of the box.** After a translation it empties the
  box ready for the next file; while one is still running it abandons it. It
  sits beside the bar rather than beside the file's name, so that it is still
  there when the box is too short to show anything else.

---

## 1.48.0 — 2026-09-15

### Fixed

- **Drag and drop has never worked on Windows.** The box on the home page has
  always said "Drag & drop an image, or click to upload", and on Windows the
  first half of that was untrue: files dropped on it were silently ignored, and
  the only way in was the Open file button. Tk has no drag and drop of its own
  and needs an extension to get it, and that extension was installed by the Mac
  installer and by nothing at all on Windows. It is now in the package list
  both installers read — and that list is also what the updater watches, so
  this arrives on your next update rather than needing a reinstall.
- **The box gave no sign it would accept a file.** Nothing responded while a
  file was being dragged over it, so a drop that was about to work looked
  exactly like one that was about to do nothing. It lights up now.
- **The middle of the box was not a drop target.** Only its outer frame
  accepted files; the icon and the words sitting on top of it — the part anyone
  actually aims at — did not.
- **A "Remove" button in the offline languages list had its padding scaled by
  the display when no other button in the app does**, so on some displays it
  was the only cramped button in the window.

### Changed

- **A file now says what is happening to it in the box you put it in.** Progress
  used to be a thin band above the two panes, the sentence explaining it sat
  under that band, and the button that saved the result was at the far end of a
  different row — three places for one thing, none of them where the file had
  gone in, and the one you had to act on was the easiest of the three to miss. A
  file could finish translating and sit there unsaved simply because nothing
  where you were looking had changed. The box now shows the file's name, a bar
  that fills as the work is done, and a line saying which page it is on — and
  when it finishes, that same bar becomes the **Download translated file**
  button.
- **The bar is a real measure of the work now.** The translator only ever
  reported progress as a sentence, so the old bar could do little more than jump
  from empty to a third to full however long the document was. It now reports
  which page of how many, and the bar follows it — stopping just short of the
  end until the translated file has actually been written, because a full bar
  over a file that is still being saved says the work is over when it is not.

---

## 1.47.4 — 2026-09-15

### Fixed

- **The icons were a different weight at every size.** Each one is written as
  shapes in a 24-unit square and asks for a stroke of 1.9 of those units. On a
  Mac the icons are drawn by the system rather than pasted in as pictures, and
  the drawing takes a stroke as a distance on screen, which may be a fraction —
  but it was being given a whole number. On a seventeen-pixel icon 1.9 units is
  1.35, and rounded that is 1: twenty-six per cent thin. Three pixels larger it
  is 1.58, and rounded that is 2: twenty-six per cent heavy. So two icons a few
  pixels apart in size, side by side in the same window, differed in weight by
  more than half — one looking ragged and the other soft. Nothing was gained by
  the rounding, and it is gone. Every icon is now the weight it asked for, to
  within two per cent, at every size.
- **The same fault, smaller, on Windows and Linux**, where an icon is rendered
  several times larger and reduced. How far up it was drawn was fixed at four,
  which made every icon about seven per cent thin and — worse — thin by a
  different amount at each size, so a seventeen-pixel icon and an eighteen-pixel
  one were thirteen per cent apart. How far up to draw is now worked out per
  icon and per size, so the weight lands where it was asked to.
- **A dark rim around every pale icon.** The icon was drawn in its own colour on
  a transparent square and then shrunk, and a transparent pixel is stored as
  transparent *black* — so the reduction averaged that black into every edge
  pixel and left white-on-blue with a grey fringe. The shape and the colour are
  kept apart now, and the fringe cannot happen.
- **The moon's two horns were blunt, or forked, or hooked.** A crescent is the
  gap between two circles, and where the two curves stopped was guessed: they
  ended near each other rather than on each other, and the outline was patched
  across the tip. The two places the circles actually cross are worked out now,
  and each horn is one point where both curves meet. The curve is also traced
  three times as finely, so there are no flat spots left near the tips.
- **The sun's rays and the gear's teeth sat on the angles hardest to draw
  cleanly.** The gear's eight teeth were all on diagonals, which at small sizes
  read as lint round a ring; four of the eight are now exactly upright and
  level. The sun's rays were long and thin on a small disc — four of them came
  out ragged — and are now short ticks around a larger one. The gear's ring is
  drawn heavier than its teeth, so that it reads as a gear and not as a second
  sun.

---

## 1.47.3 — 2026-09-15

### Fixed

- **The same Settings page wrapped its text differently from one opening to the
  next**, and much more narrowly on a PC than on a Mac. The width was measured:
  every row asked how much room it had beside its own control, and the narrowest
  answer decided for all of them. A row measured before it has been laid out
  reports one pixel wide — so a single early measurement wrapped every line in
  the pane into a column a third of the width it should have had, and whether
  that happened came down to timing. It is not measured now. The text takes the
  card's width less a fixed column for the controls, which is a number in the
  design rather than an accident of when something was asked: the same on both
  platforms and the same every time.
- **The brand tile had four stepped corners, on every platform, since it was
  drawn.** It is a gradient behind a rounded mask, and the mask was made with
  the imaging library's rounded rectangle — which has no anti-aliasing at all,
  so every pixel is in or out and the corner is a staircase. It is the one
  shape in the app that never went through the kit's own rounded rectangle,
  which has always drawn at four times the size and reduced for exactly this
  reason. Now it does.

## 1.47.2 — 2026-09-14

### Fixed

- **The drawn curves were faceted.** Every corner was built from eight straight
  segments, which is fine on a small radius and visible on a large one: the end
  of a pill is a half-circle of radius nineteen points, so eight segments put a
  joint every 3.7 device pixels and you could count them. The number of
  segments follows the radius now — a joint every 1.6 device pixels, which is
  finer than the anti-aliasing that draws them.
- **The brand tile had a notch taken out of two of its edges.** The corners are
  cut out of the gradient by the canvas, and the cut ran past the tile at the
  corner point but not at the two ends of its arc — so the shape closed with a
  straight line back across the flat edge, taking a bite out of it. Two on the
  left edge, one along the top.

## 1.47.1 — 2026-09-14

### Fixed

- **Every pill had its rounded ends sliced off flat.** 1.47.0 started drawing
  the shapes instead of pasting them, and drew them from edge to edge of their
  own widget. A canvas clips at that edge, and the outermost pixels of a
  rounded corner are where an anti-aliased curve puts its softest and most
  important ones — so both ends of every pill were cut. Nothing showed on
  Windows or Linux, where there is no anti-aliasing to lose. Every drawn shape
  now keeps a pixel and a half clear of its own edge.
- **The brand tile kept a stepped pixel at each corner.** The corners are cut
  out of the gradient by the canvas, and the cut stopped exactly at the edge —
  leaving the single outermost pixel of each corner behind, which is what a
  stepped corner is made of. The cut now runs past the edge.
- **The three API key boxes were three different widths**, and so were the
  buttons beside them: each row took whatever its own button's label left over,
  so "Get your free key" and "Set up Google" produced two different boxes on
  consecutive rows. All three rows are one shape now and end on one edge.
- **Every grey line in Settings ended somewhere different.** Each was wrapped
  to what was left beside its own control, and every row has a different
  control — a switch, a dropdown, a button with a longer word on it. They are
  all wrapped to the same width now, so the text down the pane ends on one
  straight edge. A card's closing footnote still gets the whole card, because
  nothing sits beside it.

## 1.47.0 — 2026-09-14

### Fixed

- **Nothing in the window is a bitmap any more.** Every pill, button, field,
  card, keycap, switch, dropdown, scrollbar and the brand tile's corners are
  drawn by the canvas on macOS rather than rendered as a picture and pasted.
  That is the whole of the pixellation, and it took far too long to get to.
  Tk has no rounded anything, so all of these have always been pictures —
  rendered at four times the size and reduced, which is the only way to get a
  smooth curve on Windows and Linux, where Tk's canvas has no anti-aliasing at
  all. On macOS it was exactly the wrong choice: the canvas there draws through
  CoreGraphics, which anti-aliases *and* draws at the screen's own resolution,
  while a picture is always drawn one image pixel to the point and stretched.
  So every shape in the app was at half resolution on the one platform whose
  canvas draws better than the imaging library can.

  What is still a picture is what genuinely is one: the photograph at the top,
  the crop of it that sits under each control standing on it, and the brand
  tile's gradient — whose four corners are now cut by the canvas, so no curve
  anywhere is a bitmap curve. Windows and Linux are untouched and keep the
  pictures, which is the right answer there.

## 1.46.1 — 2026-09-14

### Fixed

- **The whole window was drawn at half resolution on a Retina Mac.** Not the
  icons, not the pills, not the picture — all of it, the text included. A Mac
  with a Retina display has two device pixels to the point, and a process that
  has not declared it can cope is drawn at one and scaled up afterwards by the
  window server: every line twice as wide as it should be, every curve stepped,
  the photograph at half the resolution it was prepared at. Squint.app declares
  it, but the app runs from source as often as from the bundle — `Squint.command`,
  a Terminal launch, a debug run, and the bundle's own launcher when it falls
  back to the environment's interpreter — and in those the process belongs to
  whatever the Python framework declares. It is asked for at runtime now, before
  the first window. The launch log says what happened, on the `dpi` line.
- **A dark square behind five of the dropdowns in Settings.** A dropdown is a
  rounded pill drawn on a rectangular widget, so the colour behind it shows at
  the four corners — and five of them were left to assume the page's colour
  while sitting on a card. They take the colour of whatever they are put into
  now, rather than assuming.

### Added

- **`tools/retina_check.py`** — run it and it says whether the window is being
  drawn at the screen's real resolution, and draws the same shape three ways so
  a screenshot shows which part is at fault. It exists because three releases
  went into fixing "pixellation" by changing how things were drawn, when the
  drawing was never where it happened.

## 1.46.0 — 2026-09-14

### Fixed

- **Scrolling the Support page stopped dead when the pointer crossed the
  report box.** A box that scrolls claims the wheel, so the page stopped and
  did not start again until the pointer was moved off it — which is not
  something anybody does on purpose, so it read as the window having seized.
  The box grows with what is written in it now and never scrolls, so there is
  nothing inside for the wheel to be claimed by. It holds 500 characters.
- **Icons were drawn at half resolution on a Retina Mac.** Every icon in the
  app — the gear, the globe, the marks in the corner, the rail, the brand
  square — was a rendered picture, because Tk's canvas draws its own lines and
  arcs with no anti-aliasing at all on Windows and Linux. On macOS that is
  backwards: the canvas there draws through CoreGraphics, which anti-aliases
  *and* draws at the screen's real resolution, while a picture is always drawn
  one image pixel to the point and stretched. Measured on a screenshot of the
  Settings pane: the word beside the gear had 165 distinct grey levels along
  its edges and the gear had eight. Icons are drawn by the canvas on macOS now
  and stay pictures on Windows and Linux, which is the sharp answer on both.

### Changed

- **The engine keys row says what to do next.** Beside Gemini is Get your free
  key, beside Google is Set up Google, beside DeepL is Get a DeepL key — each
  opens the page that issues the key. It was Save & test on all three rows: the
  same button three times, for a job that is not per-row at all. Test connection
  now sits under them with How to set up Gemini, How to set up Google API and
  How to set up DeepL. Keys save when you leave the box or press Return, the
  way every other field in the window already worked.

## 1.45.0 — 2026-09-14

### Changed

- **Light and dark change instantly.** One click, one change, no fade and no
  wait — and the window stays exactly where it is, as it always did. There was
  a fade, through four releases, and it was answering a question nobody asked:
  fading the window's *opacity* dims the whole thing to almost nothing and
  brings it back, with the scheme changing in the middle where it cannot be
  seen. However smoothly that is done, it is a blink with the change hidden
  inside it rather than a colour transition — so every attempt to smooth it
  made it slower and none of them made it better. Taking it out makes the
  change about twice as fast as well.

## 1.44.2 — 2026-09-14

### Fixed

- **No button in 1.44.0 or 1.44.1 did anything when you pressed it.** Check for
  updates, Install and restart, Download, Remove, Save & test — every one of
  them was built, laid out and painted correctly and wired to nothing. Adding
  the mark to the Download button in 1.44.0 put a new method between the end of
  the button's setup and the four lines that connect it to the mouse, so those
  four lines ended up inside that method, after the line that returns from it.
  Code that can never run does not look any different in a file.

  **If you are on 1.44.0 or 1.44.1 the app cannot update itself** — that is the
  one thing this broke that you cannot work around from inside it. Download the
  zip from the release page and run the setup script once; the updater works
  again from there.

  Buttons are now tested by sending them real mouse events rather than by
  calling the code behind them, which is what let this through: every existing
  test pressed a button by calling its command directly, so it passed on a
  button connected to nothing. Every button in every pane of the window is
  checked, and the whole app is scanned for any statement left stranded after a
  return.

## 1.44.1 — 2026-09-14

### Fixed

- **The word in a pill sat low.** Two pixels below the middle, with the icon
  beside it dead centre — and three and a half on a word with a descender, like
  Settings. Tk centres a line *box*, which is the type plus the empty space a
  descender would hang into, and that space is under every word that has no
  descender in it. What the eye centres is the band from the top of the
  capitals to the baseline, and that is what every pill in the app centres now:
  the Settings button, the Snip & Translate button, the dropdowns, the keycaps,
  Download, Remove, Donate.
- **Light and dark still changed in steps.** Three separate things, and the one
  that mattered was not the fade. The window only dimmed to a third of the way
  to invisible on its way through, and a third of the way is perfectly legible —
  so the instant the dark widgets were replaced by light ones there was a hard
  cut in the middle, which no amount of smoothing either side can hide. It goes
  properly dark now, changes where it cannot be seen, and comes back up.
  Alongside that: the button that crosses from sun to moon was being redrawn on
  every frame, which cost more than the frame had, so the frames landed
  unevenly — and unevenly spaced frames are exactly what reads as stepping. It
  crosses in sixteen stops instead.
- **The pause in the middle of a theme change was twice as long as it needed
  to be.** Rebuilding the page hands the picture at the top four or five
  different widths on the way to the final one, and each of them was a full
  repaint — the photograph resized, the veil mixed, the Japanese card drawn at
  twice size and put down. Sixty milliseconds each, four of them thrown away.
  It paints once now, at the size that turns out to be the real one.

## 1.44.0 — 2026-09-14

### Fixed

- **The language you picked was not reaching the thing doing the reading.** A
  page you had told Squint was Chinese came back with Korean characters
  scattered through the Han, and with 红旗 read as 虹旗 and 试驾 as i式驾. That is
  not a translation fault — a translator handed nonsense returns nonsense, or
  transliterates it. Every reader took the language you chose and three of
  them did nothing with it: the built-in reader was never passed it at all and
  picked its script from whatever the *previous* snip turned out to be; Apple
  Vision accepted its own unconstrained reading on the grounds that a non-Latin
  result must have detected the script, when Han, kana and Hangul are three
  scripts and they are precisely the three that get read as one another; and
  the Gemini reader's instructions never mentioned the language. All four
  readers are told now, and the one you name is the one that is used.
- **The translation engine was detecting the language on every snip too**, over
  the whole page joined into a single request — so one badly-read block could
  pull the detection off for everything else on the page. It is told what you
  chose.
- **Two columns of a page could arrive as one sentence.** A reader handed a
  page in columns joins the end of one column's line to the start of the next
  one's, because they share a baseline. Squint looks at the picture to find the
  gutters and cut there, but it required a column to be a fifth of the page
  wide — a rule about magazines. A news site or a shop front page is five or
  six cards across, every column on it is narrower than that, so every gutter
  was discarded and the page was read as prose running edge to edge. The
  result was captions from different columns welded into sentences nobody
  wrote. Nothing is cut without checking the picture first, so the rule did not
  need to be that cautious.
- **A wide line could adopt a caption from the column next door.** Two lines
  join into a paragraph if their left edges are close, and "close" was measured
  against the wider of the two — a quarter of a page-wide headline is most of
  the way across the page. It is measured against the narrower one.
- **Choosing a European language told the cloud reader nothing.** Its table of
  language hints had entries for Chinese, Japanese, Korean, Russian and a
  handful of others, and none at all for German, French, Spanish or any other
  Latin language: picking one sent exactly what picking nothing sent.

### Changed

- **Offline translation is a list of what you have.** One row per language,
  with what it takes up on disk and a Remove button, and one row at the bottom
  to add another. It was a single picker with a button beside it that had to
  change its own label depending on what you had selected — Download for some
  languages, Update for others, with a Remove that appeared and vanished. What
  you want from that card is what you have, what it costs and how to add
  another, which is a list.

## 1.43.0 — 2026-09-14

### Fixed

- **Every word outside the front page was a third too big on Windows.** A Tk
  font size given as a positive number is a size in *points*, which the display
  multiplies by its DPI — so the same number was thirteen pixels of type on a
  Mac and twenty on a PC. Sizes are in pixels now, the way the rest of the app
  measures everything, and the two platforms match.
- **Settings was tight where it should be airy.** The spacing inside the cards
  was a fixed number of pixels whatever size the window was, while the type
  grew with it: heavy type in cramped rows. The rhythm of a card — the inset,
  the gap between rows, the space around a heading — is in the design's own
  pixels now and keeps its proportions at every size.

### Changed

- **Settings is a list of settings.** Every card is rows, and every row is one
  thing: what it is called and one line saying what it does on the left, the
  control that changes it on the right, a hairline between them. It was
  paragraphs with the controls underneath — a manual with switches in it. The
  explanations are still there; they are one line each, beside the thing they
  explain, which is the only place anybody reads them.

### Fixed

- **Light and dark still flashed a blank window.** The old contents were being
  thrown away before the new ones were built, so halfway through the change
  there was a grey rectangle to look at. The replacement is built first, behind
  the dimmed window, and the swap is one step with nothing in between.
- **Scrolling stuck and lagged.** It was easing towards a target on a timer,
  which is lovely when it keeps up and awful when it does not: the page trailed
  the hand, the trailing got worse the faster you scrolled, and letting go left
  it still moving. It moves when you move it now.
- **The light/dark button and the Settings button were different heights.**
  They sit in a row in the corner and they are the same kind of thing.
- **Both of those buttons sat in a little square of the wrong blue.** They
  stand on the photograph, and the colour behind them was the average of the
  sky they covered. An average is the right colour and still the wrong answer:
  a gradient is not one colour, so the square showed at its corners. They are
  given the pixels they cover now, not the average of them.
- **A second click on the drop area could put the window to sleep.** The whole
  area is a click target, and a click that landed while the file chooser was
  already up opened a second one behind the first — nothing responded until
  both had been dismissed, and only one of them was on screen to dismiss.

## 1.42.0 — 2026-09-14

### Fixed

- **The photograph is a photograph now.** A picture large enough for the space
  it fills, cropped to the band's own shape with the peak where the design has
  it — so the app only ever reduces it, which is the one resizing that costs
  nothing. It is sharp on a 4K display.
- **Every icon was drawn without anti-aliasing.** Tk draws its own lines and
  arcs with stepped edges on Windows and Linux, which at the size of a gear or
  a chevron is a handful of hard dots. They are rendered four times up and
  reduced now — smooth everywhere, at every size.
- **Settings and Support were set in the wrong size.** Their type was a fixed
  number of pixels whatever size the window was: headline type on a small
  window. It follows the page now, like everything else.
- **A paragraph in Settings lost its first words off one side and its last off
  the other.** The wrap widths were typed in, and were right for one window
  size. They follow the card they are in.
- **The window never goes below eleven-pixel body text.** That is the smallest
  this page is worth reading at, so it is the floor: a smaller screen gets the
  window it can hold, not a page it cannot read.

### Changed

- **A 4K display gets a window about half again the size of the one a laptop
  gets**, rather than one and a half times over. A screen twice as wide is a
  reason for more desk around the window, not for twice the window.

## 1.41.0 — 2026-09-14

### Fixed

- **The window was a different size on every kind of display.** It asked for
  960 units, and a unit is not the same thing twice: on a Retina Mac those are
  points and the display draws two pixels for each, so the window is a
  comfortable size; on a 4K screen they are pixels, and the same window is a
  quarter of the width it should be. It now takes a share of whatever screen it
  opens on, and the page is drawn at a scale that moves with it — the same
  window, in proportion, on a laptop and on a 4K display.

## 1.40.0 — 2026-09-13

### Fixed

- **The photograph at the top was crunchy.** It was being sharpened twice —
  once in the file that shipped and again as the band was drawn — on a picture
  already enlarged past its own resolution. That does not make a photograph
  sharp, it makes it stepped, which is what it looked like. It ships lossless
  now, is resized exactly once, and is not sharpened at all; the one thing that
  wanted the extra resolution, the card with the Japanese in it, is drawn large
  and put down small.
- **Light and dark still blinked.** It was building a second window and
  throwing the first away, and a new window is new to the system too — it
  appears, it takes focus, and no amount of fading one into the other hides
  that there are two. The window now rebuilds its own contents inside itself
  and dims while it does: one window, going dark and coming back in the other
  scheme, with the button crossing at the same time.
- **Scrolling stuck in Settings.** Tk sends a wheel event only to the widget
  under the pointer, so every widget had to be told about it one by one and
  anything built later was a patch of page the wheel did not work over. One
  handler on the window covers everything, including whatever is built next.
  It also moves further per notch.

### Changed

- **The window is one size and does not resize.** 960 by 540, on every
  machine. Everything that had to hold at every size held properly at none of
  them: the photograph was cropped away as the window widened, and the type —
  which is drawn at one scale — ran into itself when it narrowed. One shape,
  laid out for that shape.
- **The headline is one line.** "Snip it, Understand it." as a sentence rather
  than as two lines of a poster.
- **Snip & Translate sits beside "Other ways to translate"** rather than on a
  row of its own with a band of empty page beside it. Same button; the row it
  used to have goes to the boxes.
- **Light and dark is one button.** It was two halves of a pill and you had to
  hit the right one. The whole thing is the button now; both marks stay,
  because they say which scheme you are in and which is on the other side of
  the click.

## 1.39.0 — 2026-09-13

### Fixed

- **The photograph at the top was soft and blocky.** It was being enlarged to
  fill the band — the picture shipped smaller than the space it had to cover.
  A larger copy ships now, and it is sharpened at exactly the size it is drawn
  at rather than scaled up and left soft.
- **The window still opened too big.** It opens at 780 by 520 on every machine
  now, and will not be dragged smaller than that.
- **Dragging the window narrow printed the heading through itself.** The
  sentence under the headline ran into the row of claims beneath it. Every line
  in the band is measured against the room there is and the block shrinks to
  fit, so nothing can land on anything else at any size.
- **The place to drop a file had disappeared from the box.** The left box was
  being given the height of whatever was in the right one, which in a small
  window left the dashed area with no room at all — not smaller, gone.
- **The tip along the bottom ran underneath its own link** in a narrow window.
  The tail of the sentence stands down when there is no room for it.
- **Light and dark still blinked.** The old window went out before the new one
  came in, so for an instant there was nothing there. Both are on screen
  together now and their opacities cross — the same window fading from one
  scheme to the other.
- **The line in the picture was in Russian.** It is Japanese, which is what the
  mountain in the photograph is. The Japanese faces on a Mac are named in
  Japanese, which no list of file names was ever going to find.

### Changed

- **The page is drawn at one scale.** Type does not grow with the window any
  more: make the window bigger and the boxes get bigger, the words stay the
  size they were.

## 1.38.0 — 2026-09-13

### Changed

- **A new heading.** The photograph runs behind the whole top of the page now —
  edge to edge, up to the top of the window — with the headline standing on it,
  three things the app is under that, and the snip playing over it on the right
  with a note pointing at it. Settings and the light/dark switch sit on the
  picture rather than in a bar above it, which is where the bar went.
- **Snip & Translate is directly under the picture.** Same button, same
  shortcut printed on it; it is the first thing on the page rather than a third
  of the way down the heading.

### Fixed

- **The window opened too big, and a page meant to be one screen had a scroll
  bar down it.** It now takes a share of the screen rather than all of it —
  about a third less than before on a laptop — and the page is drawn at a scale
  that fits the window on every size tried, from a 1000-point screen up.
- **Light and dark jumped, with the front page visible for an instant on the
  way.** It dissolves now: the window dims as you click, the replacement is
  built out of sight and put on the pane you were on before it is ever shown,
  and the two fade past each other.
- **The drop area cut off its own contents in a small window.** It shows as
  much as there is room for — the mark goes first, then the button, never the
  line that tells you the whole box is a target.
- **The scroll bar kept its strip of the window even when there was nothing to
  scroll.** It gives it back.

## 1.37.0 — 2026-09-13

### Fixed

- **The window opened bigger than the screen.** On a laptop it was clamped by
  the system and the page ran off the bottom, and the minimum size was larger
  than some screens, so it could not be made to fit by hand either. It now opens
  at a size your screen has and draws the page to match.
- **Switching between light and dark moved the window.** It keeps its size, its
  position and the pane you were on.
- **Changing a shortcut did nothing.** It applies, and the new keys appear on the
  button and in the tip along the bottom.
- **The language swap button sat slightly right of, and below, the gap between
  the two boxes.** It is centred on them.
- **A sentence in Settings was cut off at both ends.** The notes under the
  switches wrap to the width of the card.

### Added

- **Support is a real page now.** The tip jar, and a form for telling me
  something is wrong: what happened, and an address to write back to. It opens
  your mail program with the message already in it — nothing is posted anywhere,
  and what goes along with it is spelled out above the button: the version and
  the platform, and nothing else.

## 1.36.0 — 2026-09-13

### Changed

- **A new front page.** A sidebar with Home, Settings and Support; the snip
  button as the thing the page is built around, with your shortcut printed on
  it; and underneath, the other ways in — typing, pasting, or opening a file —
  as a pair of boxes with the language swap sitting between them. Settings and
  Support are parts of the same page now rather than somewhere else to go.
- **Opening a file happens in the box you would otherwise type in.** Drag one
  onto it, or click to choose. There is no separate Open file button any more:
  typing and dropping a file are the same request, so they are the same box,
  and the drop target gets out of the way the moment there is text. This is the
  one habit in this release that changes.
- **The picture beside the headline shows a snip being taken.** The selection is
  drawn around a line of Japanese and the English appears under it, on a loop.
  It stops whenever the window is hidden or you are on another pane, so it costs
  nothing while Squint is sitting in the tray.

### Fixed

- **Three of the five type weights were being drawn in the wrong typeface.** On
  some systems the app asked for a weight by name and was told, wrongly, that no
  such face existed — so the heading came out in the system font while the line
  beside it came out in the right one. It now steps down a weight rather than
  out of the typeface.
- **The two text boxes could end up different heights**, which looks like a
  fault even when both are the right size. They are now the same height by
  construction.
- **A second window could open with pieces of it missing.** Changing the theme
  rebuilds the window, and the rebuilt one was drawing with pictures the new
  window had never been given.

## 1.35.0 — 2026-09-13

### Added

- **Squint now carries the typefaces its own interface is set in.** Nothing
  looks different in this build — this is groundwork for the new front page,
  which is drawn in a particular face and would not be the same design set in
  whatever each machine happens to have. Half a megabyte, loaded for Squint
  alone while it is running: nothing is installed on your computer and nothing
  is left behind when you quit. On a machine where it cannot work, Squint uses
  the system face exactly as it did before, so there is nothing here that can
  go wrong. Translations are unaffected — they have always been drawn in a face
  chosen to suit the language, and still are.

---

## 1.34.0 — 2026-09-11

### Fixed

- **Lists are no longer read as sentences.** A shop's navigation menu, a
  table of contents, an index, an address block, a page of verse — any
  page where each line is its own item rather than the continuation of a
  sentence. Squint was running whole columns together and translating
  them as one run of prose: "Sports Shoes Hiking Boots Sneakers
  Flip-Flops Water Shoes All Products". Worse, it was inconsistent — one
  column of a menu would come back correctly as six links while the
  column beside it, laid out identically, came back as a paragraph.

  It now tells the two apart by the right margin. Wrapped text has one:
  every line but the last runs to the same place and stops. A list does
  not — each item is as long as it is. That holds in any language and on
  any page, and it needs nothing from the text itself.

  On a seven-column menu that is 20 blocks becoming 41, one per link. A
  contract and a Chinese newsletter are unchanged.

  Three things this does **not** settle, measured and recorded rather
  than glossed over: two of the nine language test pages (French and
  Spanish) now split one paragraph each into fragments — nothing overlaps
  and nothing is lost, but it is a real cost; verse is better without
  being right, at 22 blocks for 24 lines of poetry; and choosing a source
  language still has no effect where Tesseract is the reader, though
  Windows and macOS use their own built-in readers, which do honour it.

---

## 1.33.0 — 2026-09-11

### Fixed

- **Squint no longer paints over pictures.** Text that is part of an
  image — a logo, a title set across a photograph, a caption baked into a
  product shot — is now left exactly as it was, instead of being covered
  with an opaque box containing a translation of whatever the recogniser
  made of type it cannot read. On a page of product artwork that is 34 of
  57 lines left alone; on a contract, a newsletter and a page of verse,
  not one line is affected.

  It decides this by looking at what surrounds each line rather than at
  what the line says: on a page, the space above and below is margin and
  is one flat colour; on a picture it is picture. So it works the same in
  any language and on a dark page as on a white one.

  This also fixes the worst of the layout damage on such pages. A caption
  inside a card was being set six times its own size, spilling past the
  card and pushing everything below it far down the page — because "how
  much room is there" was being measured against a photograph, where the
  answer is meaningless.

  If you would rather have the guess, `translate_pictures` in the config
  file turns it back on.

  Verse is a separate fault and is **not** fixed in this release: a page
  of 24 lines of poetry still comes back as 9 paragraphs. The cause is
  understood, but the fix that worked on poetry fragmented Chinese and
  Korean pages, which is the fault an earlier release was spent removing.

---

## 1.32.0 — 2026-09-10

### Fixed

- **Documents that number their own sections now keep their shape.**
  Contracts, specifications, standards, terms and conditions — anything
  with `3.5`, `3.8.1`, `2.10.4` headings. Squint was reading a whole
  numbered section as one paragraph, so headings were swallowed by the
  text beneath them and several clauses were run into a single block.

- **And keep their wording.** This was the damaging half. Handed a large
  block of numbered clauses in one piece, a translation engine stops
  translating and starts tidying: it moves the clause numbers to the end
  of the paragraph and replaces figures with placeholders. On a real
  contract page that turned "the initial term is 24 months" into "the
  initial term is [number] months" — the kind of mistake a reader cannot
  catch, because catching it would mean reading the original. Clause by
  clause, it does neither.

- **Headings are recognised by being bold.** A heading sits at the same
  margin, in the same size, one line above its paragraph, so nothing
  about its position says it is separate — only its weight does. Squint
  now measures that off the page itself, which works the same on a scan,
  a screenshot or a PDF, in light and dark documents alike.

---

## 1.31.0 — 2026-09-09

### Fixed

- **Pinching the overlay no longer quits the app.** The trackpad was
  answered from the wrong side of the app — from the part of macOS that
  delivers the gesture, rather than from the part of Squint that draws
  the window — and asking the drawing side to do anything from there
  brings the whole process down instantly. The gesture is now handed
  across properly and read a fortieth of a second later. Pinch zoom works
  as intended; if it ever misbehaves again it can be switched off in the
  config file with `pinch_zoom`.

### Removed

- **The language button on the overlay strip.** Reading one document in
  four languages one after another is not something anyone does, and the
  main window's language setting already covers picking a different one.
  The strip itself stays — it is there to tell you when a reference
  number could not be placed, which is the one mistake you cannot catch
  by reading.

---

## 1.30.0 — 2026-09-09

### Fixed

- **Translations no longer overlap on a Retina display.** On a Mac the
  screen is captured at twice the size, the type is twice the size with
  it, and a paragraph growing rightwards into the white space beside it
  could reach across the gutter into the next column. It now stops at
  whatever is actually there rather than at the edge of the page. On the
  Korean newsletter that is three overlapping paragraphs before and none
  after; the same across every width from 500 to 1000 points.

- **The language strip on the overlay works.** Clicking it did nothing
  visible and the translation vanished — the list was opening *behind* the
  overlay, so the next click landed on the backdrop and closed everything.
  The list is now a small window of its own that opens in front, with
  English pinned at the top, a rule, and a heading per letter.

### Added

- **Pinch to zoom.** On a Mac trackpad, pinch the overlay to make the
  translation larger or smaller — the same thing Ctrl and the wheel
  already did, for a laptop with no mouse plugged in. Windows precision
  touchpads already sent a pinch as Ctrl and the wheel, so they were
  covered and now feel the same as a Mac.

### Changed

- **Zoom is smooth rather than steppy.** It used to jump in eleven coarse
  notches, which suited a wheel that clicks and made a trackpad leap from
  life size to three times it in one gesture. The steps are now half the
  size, small movements add up instead of being rounded away, and a
  gesture grows the page at about one doubling a second no matter how
  fast the fingers move. A mouse wheel still moves the same twelve per
  cent a notch it always did.

---

## 1.29.0 — 2026-09-09

### Added

- **Change the language from the overlay.** The translation now carries a
  small strip along its bottom edge with the language it is in. Click it
  and the same capture is translated again into another language — no
  closing, no changing a setting, no snipping the same rectangle a second
  time. The page is not read again; only the translation is done afresh.

- **The last five translations are kept.** A "Recent" row in the main
  window puts any of them back where it came from. Finding the document
  again to redraw the same rectangle was the most repeated piece of work
  in the app.

- **A dropped reference number is now said on the page.** 1.28.0 puts back
  codes the engine retypes; where it loses one altogether, that was
  written to the log. It now appears on the overlay — "1 code could not be
  placed: GT-2026-115" — because a fluent sentence with a reference number
  missing from it is the one mistake the reader cannot catch.

### Changed

- **The language picker is a list you can read.** Sixty names ran in one
  column from the top of the screen to the bottom. Now: your own language
  and "Detect language" at the top, a rule, then a heading for each letter
  with its languages under it, in columns. About a third of the height,
  and you land on the letter instead of reading names. Short pickers —
  font size, theme, engine — are unchanged.

---

## 1.28.0 — 2026-09-09

### Fixed

- **Translations drawn on top of each other on a full page.** A page laid
  out in columns matched the test for "a table" exactly — the third line of
  one column has the third line of the next beside it — so between 55% and
  90% of every line on a page was treated as a table cell. A cell is
  translated on its own, so the engine never saw a whole sentence and gave
  back fragments; it is measured against its own box, so it could not use
  the space beside it; and it is pinned where it was found, so a
  translation longer than its original had nowhere to go and was drawn
  where it stood. Across six document pages: **234 pairs of overlapping
  blocks, now none**. Across nine languages laid out into each other, 144
  pairs: **120 with overlapping text, now none**.

- **Paragraphs cut in half, and paragraphs joined together.** Whether two
  lines belong to one paragraph was judged against the height of the box
  around the letters — which changes with the script, while the spacing
  does not — and then against a spacing measurement that a page with a
  table on it got wrong. A page in a dense script had four of its
  paragraphs merged into two and eight cut in half. Nine languages now
  recover **18 of 18 paragraphs exactly**, in both directions. This is what
  the wording depends on: the engine words a paragraph well and a fragment
  badly.

- **Tables losing their grid.** A row whose translation needed more depth
  was drawn over the row beneath it. Rows are now placed as rows: the cells
  of one row move together and the row below starts under the tallest of
  them.

- **A table coming back in three different sizes.** Cells were sized one at
  a time, so one name in a column could be set at half the size of the name
  below it. Cells of the same original size now share one size.

- **Text set too small to read comfortably.** A block that would not fit
  could shrink to three quarters of the document's own size before the
  layout looked for more room; one block in four was at four fifths or
  less, the worst at 69%. A block may now give up a tenth and takes room
  below instead — **nothing is set below 80%** of what the page itself
  uses. Dense pages get taller as a result, which is what Google's own page
  translation does too.

- **Eleven languages drawn as empty boxes.** The font search returned the
  first file that existed without checking it contained the script. Hebrew
  was given a Persian face, Thai the system interface font, and Tamil,
  Telugu, Kannada, Malayalam, Gujarati, Punjabi and Bengali were each given
  a Devanagari face — a different alphabet. A font is now used only if it
  can draw the script, tested character by character, including the Latin
  letters and digits that every document contains.

- **Hindi, Thai and Arabic lines drawn through each other.** Line spacing
  was one number chosen for Latin. It is now measured from the script's own
  font.

- **Arabic, Hebrew, Persian and Urdu set flush left.** They are written
  right to left and are now set flush right, as they are on the page they
  came from.

- **Covers painting over the first sliver of the next column.** Invisible
  when both columns are the same colour, and not when they are not.

### Added

- **Reference numbers, part numbers and addresses come back exactly.** A
  translation engine writes well and retypes badly: a code in the middle of
  a sentence can come back with a character changed, split in two, or
  missing, and nothing on screen says so — the reader cannot check a code
  against a sentence they cannot read. Codes are now put back as they were.
  Dates, times and amounts are deliberately left alone: a date written the
  source language's way is meant to arrive written the reader's way. A code
  the engine dropped entirely is written to the log rather than guessed at.

- **Two test harnesses**, `tools/langcheck.py` and `tools/langpages.py`,
  which write one document in twelve languages and lay every one out into
  every other, and `tools/testcard.py`, which builds pages carrying the
  things known to go wrong. The existing `tools/pagecheck.py` now measures
  translation length the way a real translation runs rather than by
  counting spaces — which is why it used to report dense-script pages as
  perfect.

### Changed

- The working set of languages is English, German, French, Spanish,
  Italian, Portuguese, Chinese, Japanese and Korean. Nothing is language
  specific; this is the set the results are checked against on every
  change.

---

## 1.27.1 — 2026-09-08

### Fixed

- **The same page snipped twice came back laid out differently.** Not the
  translator — both engines run at fixed settings and the one in use is
  deterministic. Different text was being *sent*, because the page was
  being carved up differently each time.

  Squint decided a page had columns on the evidence of one horizontal band
  of it. A wide gap between two cells of a table row looks exactly like the
  space between two columns if that is all you look at, so single-column
  pages were being cut mid-sentence. And the bands were measured across the
  picture rather than across the writing — a snip is drawn by hand, so the
  same page captured twice is two crops a few pixels apart, and seven
  pixels of margin was enough to change the answer.

  A column boundary now has to continue into the band above or below it,
  and the bands are laid over the text rather than the crop. On the test
  corpus that takes the false cuts on the four single-column pages to zero
  while the genuine three-column page is cut exactly as before — and the
  same page gives the same answer however it is snipped.

- **Translations drawn on top of each other.** When a block became free to
  use the empty space to its right, two places still worked out what was
  above what using the width the text was *found* at rather than the width
  it would be *drawn* at. So a block that had grown wide was not treated as
  being above the things it now covered, nothing moved out of its way, and
  they were drawn over each other. My fault, from 1.26.0.

---

## 1.27.0 — 2026-09-08

### Fixed

- **A shortcut that stopped working stayed broken until Squint was
  restarted.** That was true of every cause found this week, and it is why
  the same complaint kept coming back wearing different clothes: something
  killed the small background process that listens for your shortcut, the
  app noticed, wrote a line in its log, and did nothing.

  It restarts it now — quickly at first, then further apart if it keeps
  failing, and it never stops trying for as long as Squint is running. So a
  machine that recovers gets its shortcut back without anybody noticing
  anything happened.

- **And Squint looks in on it every half minute.** The part that notices a
  dead listener is itself a thread, and a thread that dies takes the only
  watcher of the watcher with it. Now nothing can quietly stop working: if
  the listener is gone at any point, it comes back within thirty seconds
  and says so in the log.

  You should never have to run anything to get a keyboard shortcut back.
  It is not a feature that may be unavailable; it is how the app is used.

---

## 1.26.1 — 2026-09-08

### Fixed

- **The shortcut listener killed itself the moment it started, on every
  launch from the app icon.** 1.25.0 taught it to quit when Squint quits,
  so that leftover copies could not pile up and hold your shortcut. One of
  the two signals it watched for was its input stream ending — which only
  means anything if that stream comes from Squint, and it did not: a
  program started from an app icon inherits an empty one, which reports
  itself finished immediately. So the listener read "Squint has gone"
  before it had registered anything, and there was no shortcut at all.

  It was shipped as the cure for leftover listeners and was worse than the
  disease: that one accumulated over weeks, this happened every single
  time. Squint now hands the listener a real connection and holds it open,
  and the listener only watches that stream when there is genuinely one
  there.

---

## 1.26.0 — 2026-09-08

### Fixed

- **Translations were squeezed into a fraction of the free space and shrunk
  to fit.** Three limits, none of which was protecting anything:

  A block could reach right by at most a third of its own width — on a
  left-aligned page with the whole right-hand side blank. It can now use
  the empty space beside it, as far as the page is genuinely empty.

  It could grow down by at most a third more than its own depth, however
  much blank page was underneath. Squint already measured the real distance
  to whatever is actually below; that measurement was then overruled by
  arithmetic. It is the answer now.

  And it could wrap to at most four lines whatever the room, so the space
  available never got to decide.

  Worst when translating into a wordier language than the original —
  Chinese into Korean or English is the extreme, where a two-line paragraph
  needs five or six lines and used to shrink instead.

- **Numbered and bulleted items were being merged into one block.** Two
  list items sit side by side, indented the same, the same height — every
  test for "these are one wrapped paragraph" says yes. So a numbered list
  came back as a single dense paragraph with the numbers buried inside it,
  and one box had to hold what the page had given two. A line that starts
  with a list marker now starts its own block.

---

## 1.25.1 — 2026-09-08

### Fixed

- **Korean translations were drawn with every space removed.** Korean is
  written with spaces between words; Chinese and Japanese are not. All
  three sit in the same part of Unicode, and the text wrapper had one rule
  for the lot — break between characters, rejoin with nothing — so a
  Korean translation came out as one unbroken run of syllables:

      연구진은 세 도시에서   →   연구진은세도시에서

  Only the overlay was affected, and only when translating *into* Korean,
  which is why it took somebody using Korean as their target language to
  find it. Korean words are now units, as they should be, and a word is
  split between syllables only when it is too wide for its line on its own.

- **A word wider than its box no longer runs off the side of the page.**
  It used to be placed on a line of its own and left to overflow, with the
  rest of the sentence simply not on screen and nothing to say so. Worst
  for Thai, which has no spaces between words at all.

- **Vowel and tone marks stay with the letter they belong to.** Thai,
  Hindi, Arabic and Vietnamese write marks above and below their
  consonants; a line break between the two left the letter without its
  vowel.

---

## 1.25.0 — 2026-09-08

### Fixed

- **The shortcut stopped working because old copies of Squint's shortcut
  listener were still running and still holding it.** Every time Squint is
  force-quit, crashes, or is killed, it used to leave a small background
  process behind — and that process keeps its claim on your shortcut. On
  one Mac more than forty had piled up over several weeks, some of them
  from before the app was renamed. macOS hands the shortcut to one of them,
  its Squint died a fortnight ago, and the keypress goes nowhere. The
  Squint you are actually using registers the shortcut, reports itself
  ready, and never hears a thing.

  It explains the two things that made no sense: why it worked sometimes
  and not others (whichever leftover holds it changes as they come and go),
  and why going back to an older build did not help (they are processes —
  they outlive every version).

  Two halves to the repair. The listener now quits the moment the app that
  started it does, so no new ones can pile up. And Squint clears away any
  that are already there when it starts, saying in the log how many it
  found.

### Changed

- The tray/menu shortcut listener writes a line in the log when it clears
  up after earlier runs, so this can never again be invisible.

---

## 1.24.4 — 2026-09-07

### Fixed

- **Squint was pulling its own app out from under itself every time it
  started, and that is what broke the shortcuts.** 1.23.1 added a check
  that rebuilt the Squint.app icon whenever it had fallen behind the code —
  including the one the app had just been launched from. Renaming and
  replacing a running application's bundle is not a filing detail on macOS:
  the app stops counting as a properly installed application, and asking it
  to come to the front stops doing anything. The snip then fires, captures
  the screen, builds its selection overlay at exactly the right size and
  position, and nobody ever sees it, because there is nothing left to raise
  it above.

  It reports now instead of rebuilding, and tells you to run
  `check.command` — which does the same job from outside the app, where it
  is safe.

---

## 1.24.3 — 2026-09-07

### Fixed

- **The selection overlay is now raised after it exists, not before.**
  Bringing an app to the front raises the windows it owns *at that moment*
  — and at that moment there was no overlay yet. So the overlay was built
  and then ordered behind whatever app you had been looking at when you
  pressed the shortcut: right size, right place, on top within an
  application that was not in front, and invisible. Squint now asks for the
  front again once the overlay is on screen, and lifts it.

- **A shortcut box left listening no longer leaves you with no shortcuts.**
  Since Squint releases its shortcuts while the box records a new one,
  walking away from an armed box meant the app sat there with none of them
  and nothing on screen to explain why. It gives up after fifteen seconds
  now, and closing the window releases it too.

---

## 1.24.2 — 2026-09-07

### Fixed

- **The snip shortcut did nothing while the button did the same job
  perfectly.** There were two routes into taking a snip. With the window
  open it hid the window, let things settle, and built the selection
  overlay a moment later. With the window hidden it went straight there —
  and the window is always hidden when you press the shortcut. Bringing the
  app to the front on macOS is a request, not something that has already
  happened by the next line, so the overlay was being built behind whatever
  you were looking at and you never saw it. There is one route now, the one
  that worked.

- **The shortcut box in Settings could not record the shortcut you already
  had.** A global shortcut swallows the keystroke — that is what makes it
  global. So while Squint held Ctrl+Cmd+T, pressing Ctrl+Cmd+T into the box
  went to the shortcut instead of the box, and the combination you most
  want to change is the one you could not. Squint now lets go of its
  shortcuts while the box is listening and takes them back afterwards. The
  same bug was on Windows, for the same reason, and is fixed there too.

- **The log now says whether the selection overlay actually appeared.** It
  reported the overlay's size and position — correctly — for an overlay
  nobody could see. Position is what a window was asked for, not what
  became of it.

---

## 1.24.1 — 2026-09-07

### Fixed

- **The keyboard check added an hour ago gave a confident wrong answer.**
  It reported that the Command key had never been pressed, on a Mac that
  had been using Command all day. Two reasons, and both are the sort of
  thing that makes a diagnostic worse than useless: it only ever asked
  about the left-hand key of each pair, so anyone who holds the right
  Command was told their key was dead — and it looked five times a second,
  which cannot see an ordinary keypress at all, so "never arrived" could
  always have meant "not while I happened to be looking".

  It now watches both keys of every pair, fifty times a second, and asks
  you to hold the keys down on their own for a moment first so the answer
  is about your keyboard rather than your reaction time. If it still says a
  key did not arrive, it now says plainly that a key which works elsewhere
  means this check is wrong rather than your keyboard.

- **The same screen printed two incompatible explanations.** It said one
  key had never arrived and then, four lines later, that another app had
  probably taken the shortcut — from a tool whose entire purpose is to stop
  people guessing. It reports what it observed, and only then what that
  might mean.

---

## 1.24.0 — 2026-09-07

### Fixed

- **Global shortcuts could register successfully and never fire, on any
  Mac, with nothing anywhere to say so.** Squint asks macOS to deliver its
  shortcuts through an old Apple interface, and the presses arrive on a
  queue that exactly one function drains. If that function is missing —
  Apple has been retiring this interface for years — the code fell back to
  a different loop that cannot drain that queue. Every shortcut then
  registered perfectly, none was ever delivered, and no error was produced
  at any point.

  Squint now checks up front that everything it needs is actually there.
  When it is not, it says so in the log and uses the other method it
  already had, which needs Accessibility permission but does deliver.

- **The reasons a shortcut backend was rejected were written where nobody
  could read them** — they went to a channel only examined after the
  shortcut watcher had already stopped. They are in the log now, while
  they are still useful.

### Added

- **`shortcut-test.command` now tells you which modifier keys actually
  reached your Mac.** "Nothing arrived" was the same answer whether the
  shortcut was broken, taken by another app, or never pressed. It now
  reports plainly that, say, Cmd arrived and Ctrl did not — which points at
  the keyboard rather than at Squint, and takes a minute instead of an
  evening.

- **The shortcut method can be chosen by hand.** `hotkey_backend` in your
  settings takes `auto` (the default), `carbon` or `watcher`. If one of
  them stops working there is now a way to try the other without waiting
  for a release.

### Changed

- **Setup finds Homebrew where it actually lives.** A double-clicked
  setup does not see the folders your Terminal sees, so on a Mac that had
  Homebrew all along, Squint would fail to notice and send you to a
  download page instead of just installing Python. It also offers the
  Homebrew route explicitly when there is no Homebrew, rather than
  mentioning it at the bottom as an aside.

---

## 1.23.3 — 2026-09-07

### Fixed

- **Shortcuts could stop working for the rest of a session while the window
  carried on working perfectly.** Everything that reaches Squint from
  outside — every press of a global shortcut — arrives on one queue, and
  the loop that empties that queue asked to be run again as its last step.
  If anything at all went wrong while handling an item, that last step was
  skipped and the loop was never run again. Nothing was reported, because
  the failure was in the part that reports things.

  The buttons in the window go straight to the same actions and never touch
  that queue, so they kept working — which makes it look exactly like macOS
  refusing to deliver the keystrokes, and sends anyone looking at it
  straight into permissions and Accessibility settings, nowhere near the
  cause. The loop now always runs again, and says in the log what went
  wrong.

- **The shortcut watcher now reports whether it can actually receive
  presses.** It runs as a separate process, and such a process can register
  a shortcut successfully and then never be told it was pressed. Squint
  already worked out which of those it had and then threw the answer away.

---

## 1.23.2 — 2026-09-07

### Fixed

- **The log could not tell a shortcut that never fired from one that fired
  and then failed.** Both look the same from outside — nothing happens —
  and they have nothing in common behind it. Squint now writes down which
  shortcut backend it is using, whether it started, what the shortcuts are
  bound to, and every press as it arrives. Without those lines a dead
  shortcut can only be guessed at, which is what was happening.

- **Two test files were changing a setting under the others.** They
  shortened a timeout to run quickly and put back a number they had typed
  rather than the one that was there, leaving every test after them running
  against a value the app does not use. A failure that had been written off
  as a known quirk for a whole release was this, and the real setting was
  correct the entire time.

---

## 1.23.1 — 2026-09-07

### Fixed

- **On a Mac, clicking the Squint icon did nothing — while the same app
  started perfectly from Terminal.** The app bundle carries its own copy of
  Python so the Dock shows the right icon, and it tests that copy before
  trusting it. The test asked whether the copy could load two things that
  come with every Python and therefore could not fail, rather than
  something the app actually needs — so a copy that could not see any of
  the installed packages passed the test, and the app died on its first
  import with no window and no message.

- **An update could never have fixed that.** An update replaces the app's
  code, not the small launcher that starts it, so the launcher had been
  frozen since the day it was first built and every release since had been
  fixing code it then failed to load. Squint now checks the launcher
  against the version running and rebuilds it when it has fallen behind —
  in the background, a few seconds after startup, and by building the new
  one beside the old and swapping it in, so a failure halfway leaves the
  app you already had.

  If yours is stuck right now, running `check.command` once fixes it.

- **`diagnose.txt` contained your API keys in full.** That file exists to
  be sent to somebody, so the instruction to run it and share the result
  was an instruction to hand over live keys. The keys are now shown as
  "set, hidden" — you can still see whether one is filled in, which is the
  part that helps. If you have sent a diagnostics file to anyone, replace
  your keys.

- **The log said "Squint 1.2.0 starting" whatever version was running.** A
  version written down in a second place and never updated since 1.2.0. A
  log is read when something is already broken and every line in it is
  being believed.

---

## 1.23.0 — 2026-09-07

### Fixed

- **A page in columns came back as nonsense, one line in five.** On a
  newspaper, a newsletter or a two-column notice, the text recogniser
  joins the end of one column's line to the start of the next one's —
  they sit on the same line of the page, and nothing has told it there is
  a wall between them. What comes out is two halves of two unrelated
  sentences glued together, and no translator on earth can make sense of
  that. It also puts the text in the wrong place, because the box it came
  in spans the whole page. On the Korean test page it was happening to a
  fifth of the lines.

  Squint now finds the empty channels running down a page by looking at
  the picture itself, and cuts any line that was read straight across
  one. Three things had to be right for that to work. It reads the page
  in horizontal bands, because a full-width headline closes every gutter
  underneath it — looked at whole, that page has no empty channel
  anywhere. What is left between two channels has to be wide enough to be
  a column, which is what stops a table being cut into confetti and stops
  a numbered contract being split away from its numbers. And a headline
  is told apart from a merged line by looking for its letters in the
  channel, not by how wide it is: on a three-column page a line merged
  across all three is very nearly page-wide itself.

  Nothing changes on a page with one column of text. Works the same on
  dark backgrounds.

### Added

- **Settings now shows where your own glossary is, and opens it.** 1.22.0
  added a second glossary that updates cannot delete, and the shipped one
  says to edit that one instead — without telling anybody where it was. A
  file nobody can find is a file nobody edits. Settings → Your glossary
  has the path, an **Open** button that creates the file if it is not
  there yet, and a way to the folder for anyone whose machine does not
  open `.txt` files on its own.

### Changed

- **Clicking the tray icon opens Squint instead of starting a snip.** A
  stray click used to dim the entire screen and sit there waiting for a
  selection, over whatever you were actually doing, with Escape the only
  way out. That is the wrong thing to put on the one gesture people make
  by accident — and it was the one action that already had a global
  shortcut, so the click was never how anybody reached it on purpose.
  Snipping is still on the menu, still on the shortcut, and still a
  button in the window.

---

## 1.22.1 — 2026-09-07

### Fixed

- **The Chinese marque names added in 1.22.0 were never actually being
  used.** They worked when tested and did nothing on a real page, and the
  reason had nothing to do with the names. Chinese, Japanese and Korean are
  not written with spaces between words, but a text recogniser hands back
  one box per character and has to join them up itself — and each one does
  it differently. Squint tidied that up for one of its five readers and not
  the other four, so on a Mac (Apple Vision) or a PC (Windows OCR) a marque
  could arrive as "享 界" with spaces in it. That reads the same, draws the
  same, and looks right on screen; what it quietly breaks is every exact
  match, because "享界" is not in "享 界". Anyone using the two readers this
  app leads with got nothing from the glossary at all.

  Now settled in the one place every reader passes through on the way out,
  so no reader has to remember. The glossary also matches through the gaps
  as a second line of defence, so a rule you have written down does not
  stop working because one reader of five spaces things differently.

---

## 1.22.0 — 2026-09-07

### Fixed

- **Chinese dates came back as "2026 Year 8 Month 28 Day".** The characters
  年, 月 and 日 are ordinary words meaning year, month and day, and Squint
  was taking the numbers out of a date one at a time before anything looked
  for a date — so what the translation service received was three separate
  numbers with three Chinese words between them, and it translated exactly
  that. Dates are now recognised whole: `2026年8月28日` becomes **28 August
  2026**, and `9月7日、9月12日` becomes **7 September, 12 September**. A
  combined issue written `2026年7-8月` becomes **July–August 2026**. Also
  covers 号 for 日 and Korean 년월일. When translating into something other
  than English the date is written `2026-08-28`, which cannot come back with
  the day and month the wrong way round.

- **Chinese car marques were being translated as words.** 享界 is the marque
  Stelato, written with two characters meaning "enjoy" and "boundary", so it
  came back as "Enjoy G9". 尊界 (Maextro) came back as "Premium". There is
  nothing about these that looks like a name, so no rule can spot them —
  they have to be known. Around forty are now in the glossary: the HIMA
  marques, the electric-vehicle makers, the state groups. The translation
  service is also now asked for a name's established English form rather
  than being told to copy it exactly, which was the wrong instruction for a
  name written in Chinese characters.

### Added

- **A glossary of your own, that updates cannot delete.** Rules added to
  `glossary.txt` in the Squint folder were being wiped by every update,
  quietly — an update replaces that file, and the terms you had fixed
  started coming back wrong with nothing to connect the two. There is now a
  second glossary next to your settings, which no update touches. Both are
  read, and a rule of yours beats the shipped rule for the same term. Add
  your own terms there.

  Two the shipped glossary deliberately leaves alone: 钛 and 汉. Each is a
  model name in one sentence and an ordinary word in the next — 钛合金 is
  titanium alloy, not Ti alloy — so they belong in your glossary if your
  work needs them, where you can decide.

---

## 1.21.0 — 2026-09-06

### Added

- **A question mark beside the Gemini and Google key fields, opening a
  step-by-step picture guide.** There has been a written guide to getting a
  key in the app for a while, behind a button at the foot of the same
  screen, and hardly anyone found it. What people get stuck on is not what
  an API key is — it is which of forty buttons in a console that Google
  redesigns every few months, and no sentence survives that. So each of
  those two keys now has a guide made of the actual screens, in order, with
  the button to press circled on each one. It opens inside Squint rather
  than in a browser, so it works on a locked-down machine and it cannot
  drift out of step with the version you are running. DeepL has no picture
  guide and so has no question mark.

  It opens as a floating window you can **zoom and move around**: the wheel
  scrolls, Ctrl (⌘ on a Mac) and the wheel zooms, dragging pans, and there
  are **Fit**, **−** and **+** buttons with the current size shown beside
  the title. It opens at whatever size fits your screen and goes up to
  three times that, because a guide made of screenshots is no use at a size
  where you can see there is a button but not read what it says.

  The written guide corrected in 1.20.3 is still there and still
  translated; the pictures are in English only. Adding them takes the
  download from about 0.6 MB to about 1.3 MB.

### Fixed

- **Squint could stop responding, repeatedly.** Reported after 1.20.3. The
  most likely cause has been taken back out: that release asked macOS,
  through an undocumented corner of the window system, not to bring the
  app forward when the small "Translating…" pill appeared. It was a guess
  at a fix, it could not be tested anywhere but on a Mac, and it ran on
  every single translation — which is the right shape for a fault that
  shows up constantly. The half of that fix that is certain stays: the
  translation card still does not steal focus, so translating a selection
  still does not drag the whole app in front of what you are reading.

- **A failure inside the app is now written to the log instead of being
  swallowed.** Until now an error in a button, a timer or a redraw was
  printed to a console that a packaged app does not have — so what reached
  you was a button that did nothing, and nothing anywhere saying why. Every
  one of those now lands in the log with the line that caused it. This does
  not stop anything going wrong; it turns "it crashes a lot" into something
  that can be found and fixed. If it happens again, double-click
  **logs.command** (macOS) or **diagnose.bat** (Windows) in the Squint
  folder — it gathers the logs onto your Desktop in one file.

---

## 1.20.3 — 2026-09-06

### Fixed

- **Translating a selection brought the whole app to the front** *(macOS)*.
  Press the shortcut over a sentence in a browser and Squint came forward —
  the settings window you left open two hours ago and all — and then drew
  the translation card on top of its own window, over the thing you were
  reading. Two causes, both the same mistake: asking for the keyboard on
  macOS does not focus a window, it activates the *application*, and
  activating an application raises every window it has; and simply showing
  a window does the same. The card no longer asks for the keyboard — it
  never needed it, since it has Copy and Close buttons and closes when you
  click anywhere else — and the small "Translating…" pill now asks macOS
  not to bring the app forward when it appears. Escape still closes the
  card: it is now read from the system rather than waited for, which is
  how the snip overlay has always done it.

### Changed

- **The in-app key guide matches the picture guides.** *Settings → How to
  add API keys* had three things wrong with it. It told everyone to accept
  a free trial that only brand-new accounts are ever offered; it never
  mentioned that Google wants a payment method on any project using these
  services, even inside the free limits; and it said nothing about
  restricting a key, or about the trap where restricting one before
  switching the services on fails in exactly the same way as never having
  made it. The Gemini section now also says what the settings screen says:
  the allowance is per day, it resets at midnight in California, it belongs
  to your Google account rather than to Squint, and leaving **Reading
  text** on **Automatic** makes it last about twice as long.

---

## 1.20.2 — 2026-09-06

### Changed

- **Translations no longer open a new connection every time.** Every
  translation is a request to a server that is usually on another
  continent, and Squint was hanging up after each one and dialling again
  from scratch for the next: a fresh address lookup, a connection
  handshake, and a second handshake for the encryption — three or four
  trips across the world before a single character of your sentence was
  sent. The connection is now held open and reused, so from the second
  translation onward the sentence goes out immediately. How much time that
  saves depends entirely on how far away the server is; on a slow or
  distant connection it is the larger part of the wait. Reading the screen
  through Cloud Vision gets the same treatment, which matters because a
  snip pays the cost twice — once to read the image and once to translate
  what was read.

  If you are behind a proxy — most office networks — nothing changes:
  Squint hands those requests back to the old path, which knows how to
  find the proxy.

  Squint now writes one line to its log when it closes, saying how many
  requests were made, how many had to dial, and the average time for each
  kind. That is the only honest way to see what this was worth on your own
  network.

---

## 1.20.1 — 2026-09-06

### Removed

- **A snip always draws the translation back onto what you captured.**
  1.20.0 added a reading pane: on a page it judged too dense, it stopped
  redrawing the page and laid the translation out as a single column
  instead. That was a mistake and it is gone. A column of translated
  paragraphs is what the text-translation shortcut already gives you; the
  reason to snip something is to see it translated *in the shape it was
  in*, with a form still a form and a table still a table. Density is no
  longer a reason to show you anything else — for text that came out
  small, the overlay zooms, and it re-lays the page out at the new size
  rather than magnifying what was drawn.

Everything else from 1.20.0 stays, including the fix for Korean, Chinese
and Japanese paragraphs arriving in fragments.

---

## 1.20.0 — 2026-09-06

### Added

- **A dense page is now shown as something to read, not something to look
  at.** Squint normally draws each translation back over the text it
  replaces, which is right for what people actually capture — a paragraph,
  a dialog, a menu, a form field. It has one failure and the failure is
  total: a whole page laid out in narrow columns. Translated text is a
  different length than the original, so blocks grow, grown blocks collide,
  and what you get back is text written over text. Past a certain density
  Squint now stops trying to redraw the page and lays the translation out
  as a single column at a size made for reading: paragraphs one after
  another, in reading order, nothing on top of anything else. Which of the
  two you get is decided by measuring the finished layout — whether blocks
  landed on each other, and whether the text ended up too small to read —
  so a paragraph is still drawn where it sits and a newsletter is not.
  Tables keep their rows, and reference numbers and amounts that are left
  showing in the original on the page are carried across so they cannot be
  lost. Over the six test pages this removes every overlap and loses no
  words.

- **Tab switches between the two.** Whichever Squint chose, Tab gives you
  the other one, both ways round, without capturing again.

### Fixed

- **Korean, Chinese and Japanese paragraphs came back chopped into
  fragments.** Copy a paragraph out of a document and the clipboard gets a
  line break at the end of every rendered line; Squint joins those back
  together before translating, but only if the line was long enough to have
  been the full width of a column — otherwise a poem or a list would be run
  together into one sentence. That length was counted in characters, which
  is a Latin habit: a full-width column of Korean holds around 25
  characters, because each one takes two columns of the page and carries
  about as much meaning as an English word. So no line in it was ever long
  enough, no break was ever joined, and the engine received the paragraph
  already in pieces — "The researchers selected pairs of / buildings / with
  similar structures and / floors across three cities." The identical
  paragraph in French joined perfectly. Lines are now measured by how much
  room they take rather than how many characters they have, and a break
  inside a script written without word spaces is closed without inserting
  one, so 시행한 no longer becomes 시 행한.

- **A long list could be run together into a paragraph.** Items in a list
  are often all about the same length, which is exactly what a wrapped
  column looks like. A line that begins a list item — a dash, a bullet, a
  number — is now never joined onto the line above it.

---

## 1.19.4 — 2026-09-05

### Fixed

- **Translated text arrived with words cut in half.** Copy a paragraph out
  of a PDF, a page of a book, or most email clients and the clipboard gets
  a line break at the end of every *rendered* line — those breaks belong to
  the column the text was set in, not to the text. Handing them to a
  translation engine gives it a paragraph already chopped into fragments,
  and what comes back is chopped in the same places; except those places no
  longer fall between words, because two languages do not run out of column
  at the same point. "Our dis / hes may contain… fish and crust / a /
  ceans." The translation itself was perfect every time. Wrapped lines are
  now joined back into paragraphs before anything is translated, which is
  what the reading path has always done and this one never did. Lines
  somebody meant to keep apart — a poem, a list, a heading, a menu — are
  left exactly as they are.

- **A placeholder could appear on the page in place of a number.** Before a
  reference number, price or date is sent to a translation engine it is
  swapped for a marker, so the engine cannot alter it, and swapped back
  afterwards. Sometimes an engine invents an extra marker of its own — a
  language model handed a paragraph full of them will occasionally produce
  one more — and there is nothing to put back in its place, because nothing
  was ever taken from there. That marker used to be left where it stood,
  which is how a bill came back reading "ZQXQQ kWh" instead of "3.344 kWh".
  It is now removed. A gap in a sentence reads as a translation that
  dropped a word; the marker read as the app being broken.

---

## 1.19.3 — 2026-09-05

### Fixed

- **Text was being drawn on top of other text.** The fault you notice
  before any other, and it had two causes that are the same mistake:
  asking "what comes next?" by position down the page alone. The room a
  block had to grow into was measured to whatever came next going down —
  which on a table is very often the cell to its *right* on the same row,
  so a block was told it had no room when the space beneath it was empty,
  or told it had the whole page when the next row began ten pixels lower.
  And a block that grew pushed everything after it down the page, so on a
  page laid out in columns one long paragraph shoved the *other* column's
  blocks out of place — which is why a contract's clause numbers had
  drifted away from their own clauses, with nothing wrong with either.
  Both now ask whether the two blocks are actually in each other's way,
  which means overlapping side to side. Measured over six pages in six
  languages, blocks drawn over each other fell from 80 to 43; on the four
  pages that are not multi-column, from 23 to 3.

### Added

- **Glossary rules can name the language they are for.** Write
  `de: Menge = Quantity` and the rule applies only when the page is
  German. A rule without a language applies to everything, exactly as
  before.

  This matters because the words a translation engine gets wrong are
  mostly single cells of a table — one word with no sentence around it to
  say what it means. "Menge" comes back as "Crowd", "Eingang" as
  "Entrance". Until now a glossary rule applied to every language, which
  is right for a brand name and wrong for a word: "Art" is German for
  "type" and English for art, so a rule to fix the German would have
  damaged the English. Language-specific rules are used only when the
  source language is known — set it in Settings, or leave it on Detect and
  they are simply skipped, so not knowing costs a word left to the engine
  rather than a word rewritten wrongly.

  `glossary.txt` now ships with the terms actually seen going wrong on
  real documents: German invoice and statement headings, French menu
  headings, Chinese notice headings. It is a plain text file you can edit.

---

## 1.19.2 — 2026-09-05

### Fixed

- **A page could be read in the wrong language altogether.** Before reading
  a page, the app decides which alphabet it is written in by trying each of
  them on a sample of the page and seeing which does best. That sample was
  the whole page shrunk down to a fixed size — and what the test actually
  measures is how well each alphabet's model reads the *shapes of the
  letters*, so shrinking the letters changed the answer. It changed it most
  for the writing that needs the detail most. A page of Chinese was read
  with a European model, which does not fail and does not warn: it returns
  confident nonsense, and the nonsense was then translated and drawn over
  the page as though it were the document. The app now looks at a strip of
  the page at its real size instead. Across six pages in six languages the
  right model is now chosen every time, where before it was three times out
  of six — Chinese and Korean went from unreadable to correct.

- **Rows of a table were read as a single line, and the more like a table a
  row was the worse it got.** Splitting a row into its cells depends on
  spotting a gap far wider than the space between words. The width it
  compared against was the *typical* gap on that line — so on a row that is
  nothing but columns, where every gap is a wide one, the typical gap was
  itself enormous and no gap on the line could ever beat it. On a bill, a
  label and the figure 658 pixels away from it stayed in one box, and every
  column position on the page was lost before the translation was even
  placed. The comparison is now against the width of an actual word space,
  which cannot be wider than the line is tall. Lines of ordinary prose are
  unaffected.

- **A cell of a table was laid out as though it were a line of a
  paragraph.** Everything the app does to a line of prose is wrong for a
  cell: a line that grows pushes the line below it down, is gathered
  together with its neighbour into a paragraph, and may spread into the
  space to its right. In a table, the space to the right is the next cell
  and the thing below is the next row — so the label of one row ended up
  beside the value of another, columns of figures were sent to be
  translated as though they were sentences, and blocks of background colour
  were painted across neighbouring cells. Cells are now recognised by the
  fact that something else sits beside them on the same row. A cell keeps
  its place, takes its size from its own box, and stays inside it.
  Paragraphs behave exactly as before.

- **Meter numbers, dates and columns of amounts are no longer sent to be
  translated.** A translation engine cannot improve a reference number and
  can corrupt it — and a corrupted number still looks like a number, so
  nothing on the page tells you it changed. This is the same protection
  already given to email and web addresses.

### Added

- **A way to measure a translated page instead of looking at it.**
  `tools/pagecheck.py` runs a page through the real reading and layout code
  and reports what was actually wrong on real documents: rows left
  unsplit, words that went missing between the translator and the page,
  original text still visible underneath, reference numbers protected, and
  how far the largest and smallest text on the page are apart. It needs no
  internet connection. Every fix in this release was measured with it
  before and after.

---

## 1.19.1 — 2026-09-05

### Fixed

- **Part of a translated paragraph could go missing, with nothing to say
  so.** A paragraph is sent to the engine whole, because that is what makes
  the wording good, and then has to be put back onto the lines it came
  from. Which lines belonged together was being worked out twice — once
  before translating and once before drawing — from different information,
  and nothing made the two answers agree. Where they differed, the page
  filled with half-sentences that began nowhere. And a line deliberately
  left in the original, such as an email or web address, took its share of
  the paragraph's words away with it: measured on an ordinary contact
  block, four words of eleven were simply not on the page. That reads as a
  bad translation and was not one. It is decided once now, and the
  paragraph the engine returned is the paragraph that gets laid out.

- **The original could still be showing underneath its own translation.**
  English is shorter than German more often than not, so three lines of a
  paragraph regularly become one. The rectangle painted over the original
  was sized to what was drawn rather than to what it replaced, and stopped
  two lines short — leaving both languages on the page, one under the
  other.

- **Some lines were set two or three times too large.** The previous
  release shrank each box to the writing inside it, which cures a box that
  swallowed the blank space above a line. It cannot cure a box drawn round
  two lines of the page at once: the ink really is that tall. Two lines
  have blank paper between them and one line does not, so the lines inside
  a box are now counted and the size comes from one of them. An accent or
  the dot of an i is not counted as a line.

- **Snipping across several monitors behaved as though they were one
  screen.** Two faults. A window position beginning with a minus is not a
  negative coordinate to the window system — it means a distance from the
  far edge of the screen — so every display arranged to the left of or
  above the main one had its overlay placed by measuring in from the wrong
  edge of the wrong screen. One display was then covered twice and another
  not at all.

- **The translation could appear on a different monitor from the thing it
  translated.** The finished overlay was pulled back inside the *main*
  display's bounds, because that is the only size the window system offers
  by default. A selection on a second or third monitor was dragged back
  onto the first. How much room the overlay has before it starts scrolling
  was measured the same way, so it was too small on a large second monitor
  and hung off the edge of a small one.

- **On Windows, the app could be told the wrong size for a screen.** A
  program has to ask Windows for real pixels, and the request fails
  silently if something has already answered it. The result of that request
  was never checked, so a process that had been refused carried on
  measuring a display set to a different scale as though it were the main
  one — right on one monitor and wrong on the others. It is checked now,
  asked for in the best way available first, and what was actually granted
  is written to the log.

- **A selection on a high-scale display was set at the wrong size.** How
  much of the screen was grabbed decides how large the translation is
  drawn, and it was counted in raw pixels. A 4K display at 150% draws the
  same document half again as wide, so a modest selection on it counted as
  a whole page and was set at the size a whole page gets. It is now
  measured against that display's own scale.

### Added

- **The picker writes down what it saw.** Every time the selection overlay
  opens, the log records how many displays were reported, the size and
  position of each, where its overlay actually ended up, and the scale that
  display is drawn at. A selection that misbehaves across monitors is one
  of two different faults, and a screenshot of it cannot tell them apart.

---

## 1.19.0 — 2026-09-04

### Fixed

- **Some lines were translated several times too large, shouldering the
  rest of the page aside.** The size of a translation was taken from the
  height of the box the reader drew round the original line. When that box
  also took in the blank space above the line — which happens most on
  Chinese and Japanese, where the top and bottom of a line are far less
  obvious — the height being measured was the emptiness rather than the
  writing. The box is now shrunk to the ink actually inside it before
  anything is measured from it, so a box reported as five times too tall
  no longer changes the result at all.
- **Watermarks that sit straight and appear only once or twice are now
  removed.** A watermark had to look wrong in two ways before being
  dropped — repeated many times, set at an angle, or pale — and a pale
  horizontal one in the corner of a page only ever looked wrong in one.
  Being far larger than everything else on the page now counts as the
  second way, which is what a reader notices about a watermark first.
- **A dark heading could be deleted as though it were a watermark.** The
  test for pale text compared the darkest tenth of a box against the
  lightest tenth, and ink is a small minority of the pixels in its own
  box — smaller the taller the box. On a heading, that tenth reached past
  the letters into the paper around them and averaged the two together, so
  black type scored as pale.
- **Watermark removal did not run for every way of reading a page.** Two
  of the four paths returned the text without it: the basic reader used
  when neither the built-in one nor a cloud key is available, and the path
  taken when a cloud reader has been chosen explicitly in Settings.

---

## 1.18.0 — 2026-09-04

### Fixed

- **Zooming an overlay sent it off the side of the screen.** Only the
  window's position was ever pulled back onto the display, never its size,
  so a zoomed full-screen capture became a window wider than the monitor
  with everything past the right edge unreachable — and there was no
  sideways scrolling to reach it with. It looked as though ctrl and the
  wheel did nothing. The window now stays within the screen and the page
  moves inside it.
- **A paragraph came back in several sizes, several greys, and drifting
  down the page.** Each line was placed, sized and coloured on its own, so
  a line that grew nudged the next one down and the nudges accumulated —
  by the foot of a column the text had wandered away from what it was
  replacing, worst on numbered lists and label-and-value rows. A paragraph
  is now laid out once, as one block, and the translation is rewrapped
  inside it rather than cut to wherever the original happened to break.
- **Stray grey blocks over a white page.** The patch covering a line
  reaches to the right on the assumption that the space beside it is the
  same background. That is usually true and sometimes wrong — beside a
  shaded panel, a table cell or a rule it painted one background across
  another. How far it reaches is now measured rather than assumed.
- **A zoom that failed did so silently and took the overlay with it.** The
  old view was discarded before the new one had been built, so anything
  going wrong left an empty window; and both failure paths returned
  quietly, which made "could not zoom" and "zoom was never connected"
  identical from the outside and in the log. Neither is true now.
- **The snip overlay left timers running after it closed**, firing into
  windows that no longer existed.

### Added

- **Drag inside the overlay to move around a zoomed page.** Sideways
  scrolling needs a wheel that tilts or a trackpad and plenty of mice have
  neither, so anything pushed past the right edge was out of reach. Press
  and drag now moves the page in both directions at once. Clicking away
  still closes it, as do Escape and right-click. Shift and the wheel, and
  the arrow keys, scroll sideways too.
- **The menu-bar icon on macOS can change the target language.** The tray
  menu on Windows has had this since it was written; the menu bar had four
  flat items and no submenu at all, so changing language on a Mac meant
  opening the window for something that is one click away everywhere else.
  Both menus now offer the same languages.
- **The clipboard shortcut records what it did** — whether permission was
  granted, whether the copy actually landed, which text it fell back to,
  and what was on screen afterwards. Every failure on that path is silent
  by nature, which left a report of "it translated the wrong thing" with
  four possible causes and no way to tell them apart.

---

## 1.17.0 — 2026-09-04

### Fixed

- **A translated page could show both languages at once.** Text that
  needed more room than the line it replaced was drawn lower down, but the
  patch covering the original moved with it — so the original stayed on
  screen above the translation. Every line that did not fit appeared
  twice, once in each language. Introduced in 1.16.0.
- **A whole page came back far taller than the region it was taken
  from.** The smallest permitted text size was larger than the size
  documents are actually set in, so every line on a page was being drawn
  *bigger* than the original. Nothing then fitted where it came from and
  each block pushed the next one down. A page is now kept at its own text
  size — measured against the document rather than a fixed number — and
  only fine print too small to read is enlarged. On the page this was
  found with, the translation went from three times the height of the
  capture to a twenty-fifth over it.
- **Chinese and Japanese translations ran off the side.** Lines were
  broken between words, and neither language puts spaces between words —
  so a whole paragraph arrived as one unbreakable piece, was drawn as a
  single line, and everything past the edge was simply not on screen.
  Both now break between characters, without stranding punctuation at the
  start of a line.
- **Translating into a language the machine had no font for produced
  empty boxes.** The font search returned whatever scalable file it found
  first, which frequently could not draw the script it was asked for, and
  nothing reported a problem. It now checks that a font can draw the
  script before offering it.
- **A long file name pushed the Save button off the edge of the window.**

### Added

- **A PDF that contains its own text is now translated from that text
  rather than from a picture of it.** Recognising a rendered page turned
  correct words into near-misses before anything was translated, and no
  care taken over the result afterwards could recover them. The output is
  a real document whose text can be selected and searched. A scanned page,
  or any file this cannot read honestly, still goes through recognition as
  before.

---

## 1.16.0 — 2026-09-03

### Fixed

- **Translations no longer get cut off mid-sentence.** Text that did not
  fit the space the original line occupied was trimmed and given an
  ellipsis. That is the one failure a reader cannot see — a document may
  contain an ellipsis of its own, and the missing words leave no trace.
  Nothing is trimmed now. Text that needs more room pushes the rest of its
  own column down; lines that fit do not move at all.
- **A page with more than one column is no longer overwritten.** The
  renderer assumed the space to the right of a line was empty and free to
  use, which is true of one column of prose and false of a letter with an
  address block beside the body — so the body painted over its neighbour,
  and the room each line was given was measured against a line in the
  other column. Columns are now found before anything is drawn.
- **The setting called Text size no longer works backwards on the
  in-place translation.** It was being used as the smallest size the text
  was allowed to shrink to, so raising it stopped the translation fitting
  and cut the remainder off — a bigger number gave you less to read. The
  size is now chosen from how much of the screen was captured: a small
  selection is drawn at a comfortable reading size, a whole page is drawn
  to fit its layout and read by zooming into it. Text size in Settings now
  applies to the result card, which is what its preview always showed.
- **The translation is sharp on high-resolution displays.** It was drawn
  into a picture at capture resolution, scaled down to fit the window and
  scaled back up by the system to reach the screen — every letter made the
  trip twice. It is drawn directly at the screen's own resolution now, as
  is the mark around it.
- **The corners of the selection frame had small spikes on them.** The
  straight part of each corner mark was drawn with a rounded end that
  bulged back over its join with the curve.
- **The macOS menu-bar menu said "Snip && Translate".**

### Added

- **A translation taller than the screen can be scrolled.** Now that
  nothing is cut, a dense page can produce more text than the space it
  came from. The overlay grows to fit where there is room, and past the
  edge of the display it stops growing and scrolls instead — wheel,
  trackpad, arrow keys or page keys. Ctrl and the wheel still zooms.

---

## 1.15.0 — 2026-09-03

### Fixed

- **Esc did not cancel a snip on macOS.** Dragging a selection worked,
  the ✕ worked, right-click worked, and Escape did nothing — because the
  overlay is a borderless window, and a borderless window on macOS
  accepts mouse clicks while never becoming the window that keyboard
  input is delivered to. Escape is now read directly from the system
  rather than waited for, so it works whether or not the overlay ever got
  focus. No new permission is needed for this.
- **A shortcut could take over a system key combination.** On macOS a
  shortcut is registered with the system properly, which means the system
  hands it over — so a shortcut set to ⌘C stopped Copy working
  everywhere, including in the panel needed to undo it. Setting one that
  way has been refused for a while; what was missing is that a value
  already saved was never re-checked, so it was loaded and re-armed on
  every launch. It is now repaired automatically on startup.

### Added

- **Shortcuts are confirmed before they take effect.** A combination
  using only one modifier and a letter is one most applications also use,
  so it works everywhere except the program being read. Pressing one into
  the field now asks first, and answering no puts the previous shortcut
  back. Both shortcuts being set to the same combination is refused —
  previously one of them silently stopped working.
- **Settings > Shortcuts has a "Reset to defaults" button.** Puts both
  shortcuts back to what they are on a fresh install, in one click,
  without having to remember what they were.

---

## 1.14.0 — 2026-09-03

### Fixed

- **The main window could cover the first-run screens.** A couple of
  startup checks — no tray icon, a shortcut conflict — show the main
  window on their own timer, a second or so in, and if the wizard was
  still open that put the main window in front of it with no way back
  short of dragging it aside. Those checks now wait for the wizard to
  close first.
- **The language screen's "More languages…" list had no scrollbar.**
  Expanding it could run past the bottom of the window with the rest
  clipped off, and the only way to see it all was to resize the window by
  hand. The screen scrolls now, the same as Settings does.

### Added

- **Settings > Behaviour has a "Show again" button for the welcome
  screens.** They are only ever shown automatically once, at first
  launch — this is a way back in on purpose, prefilled with whatever is
  already saved.

---

## 1.13.0 — 2026-09-03

### Fixed

- **The first-run screens could open invisibly** on a fresh install,
  staying behind other windows with no way to bring them forward. They are
  raised and focused properly now, the same way every other window in the
  app already is.

### Added

- **The language screen offers an opt-in checklist of common languages to
  read.** Turning one on installs that language's Windows text-recognition
  pack in the background — setup carries on to the next screen while it
  downloads, and Squint keeps reading over the internet the whole time
  either way. Picking several installs them together, with one permission
  prompt rather than one per language. Left off, declined, or refused by
  the machine: nothing breaks, and the same offer comes back later,
  just-in-time, from Settings.
- **A modern shared progress bar**, used for both this checklist and the
  existing language-pack installer in Settings.

---

## 1.12.0 — 2026-09-03

### Added

- **A short first-run setup.** Two questions the first time the app is
  used: which language you want translations in, and an optional
  translation key. Nothing is downloaded and no permission is asked for —
  that stays where it already was, in Settings, and only for a language
  that actually needs it. Skippable at any point; asked once.

---

## 1.11.3 — 2026-09-03

### Fixed

- **A snip could come back mostly untranslated while looking finished.**
  When the translation engine faltered part-way — a busy service, a spent
  daily allowance, a line it reflowed — the lines it could not do were put
  back as their original text and drawn over themselves. Identical pixels,
  no error, and no way to tell them from lines Squint had deliberately left
  alone, so a half-finished page looked like a completed one. Those lines
  are now left blank, so the real text shows through and a gap looks like a
  gap.
- **An overlay covering less than half the page is no longer shown.** Three
  lines changed out of twenty reads as a finished job done badly. Squint
  now shows the result card instead, with the translation beside the
  original — which is what it already did when nothing at all could be
  drawn.
- **A page of Latin text could be kept by a non-Latin language pack.** When
  no reading is genuinely in another writing system, they are all reading
  the same Latin page, and the stray characters some packs invent are noise
  — but the longest reading won, so the pack that invented the most
  characters won. Nothing reached the screen wrong, since a doubtful
  reading is checked against a cloud reader; it cost a network round-trip
  on every snip to undo a decision that should not have been made.

---

## 1.11.2 — 2026-09-03

### Fixed

- **Watermarked documents came back mostly untranslated.** A rule added in
  1.11.1 holds back any line containing an email address, so a recognised
  copy of one is never drawn over the real thing. Documents stamped with a
  name and email across every paragraph put that address into most of the
  lines, and the page stayed in its original language — protecting nothing,
  since a watermark is not a link anyone will click. An address on most of
  the page is now treated as a stamp and ignored; an address on a line or
  three of it is still protected, and so is a short snip that is mostly an
  address.
- **An internal placeholder could appear in a translation** — text like
  `ZQXBQ.ZQXAQ` in the middle of a sentence, with a fragment such as
  `24Cd 0` left at the end of the paragraph. Squint swaps model codes and
  numbers for markers so the engine cannot rewrite them, and a value like
  `0.24Cd` was masked in two pieces; the pair then looked like an acronym
  to the next pass and was masked again, and unmasking only went one level
  deep.
- **A failed copy is no longer presented as a result.** When the shortcut
  cannot copy your selection it falls back to what is already on the
  clipboard, which is right when you copied something yourself — but the
  only sign was one word in the label, next to a fluent translation of
  something you did not select. On Windows, where it can be known for
  certain that nothing was copied, the card now says **"old clipboard
  (copy failed)"**. 1.11.1 caught only the case where the clipboard held
  Squint's own previous answer; this covers text you had copied yourself.

---

## 1.11.1 — 2026-09-03

### Fixed

- **The selection shortcut could hand back the previous translation instead
  of a new one.** Select a sentence, press the shortcut, and read a fluent
  English answer — to the sentence you translated a minute ago. Two things
  stacked. The shortcut copies for you, but only once your own keys come
  back up, and it gave up waiting after 0.6s; hold the shortcut a moment
  longer and the copy reaches the browser as Ctrl+Alt+C and takes nothing.
  It then fell back to whatever was on the clipboard — which, with
  auto-copy on, is Squint's own last answer, so it translated English into
  English and got it back unchanged.

  It now waits long enough (both limits are give-up times, so nothing is
  slower when it works), and refuses to re-translate its own last answer:
  you get *"Could not copy the selected text in time… try again"* instead
  of a confident wrong result. Text you copied yourself still translates
  normally.
- **Recognised email and web addresses were drawn over the real ones.** One
  letter different is still an address, still looks typeset, and goes
  somewhere else — and unlike a mistranslated word, nothing about it looks
  wrong. An address is not language and gains nothing from being
  translated, so lines carrying one now keep their own text. The rest of
  the page is translated as before.
- **The first read after starting the app was much slower than the rest.**
  Loading a recognition model for each installed language happened on the
  first snip, with you watching. It now happens in the background at
  startup.

### Added

- **`time-read.bat` and `time-read.command` now actually ship.** 1.11.0's
  notes described the first one and the zip did not contain it. A test now
  fails the build if any launcher in the folder is missing from the release.

---

## 1.11.0 — 2026-09-03

### Fixed

- **The wrong language pack could answer, on Windows, and the result looked
  right.** With more than one text-recognition pack installed, a page in
  one language could be read by the engine for another. That engine does
  not fail and does not warn: it returns the page mostly correct, with a
  few characters quietly wrong. In practice that meant an email address
  coming out with one letter changed, a web address gaining a dot, an
  accented letter turning into a digit — drawn in clean type over the real
  ones, with nothing to suggest anything had gone wrong. A translation that
  is visibly broken is a nuisance; one that is wrong in three places and
  looks finished is worse.

  The rule that chose between readings said that two characters in a
  writing system of its own were enough to win, because a misreading can
  only come out as Latin. That holds when a Latin engine is pointed at
  Chinese, Japanese, Korean, Russian or Arabic — which is what it was
  written for. It does not hold in reverse: an engine for one of those
  languages pointed at a Latin page returns the page, with two or three
  lookalike characters dropped in, and two was the whole bar. It is a share
  now — a page really in another writing system is mostly in it, a misread
  Latin page is two characters in two hundred.

  A few stray characters from another script in an otherwise Latin reading
  also used to *stop* Squint asking a second engine, when they are the
  clearest sign there is that the wrong pack answered. Now they prompt it.
- **Overlays in Korean, Japanese and Chinese drew boxes instead of
  characters.** All three shared one list of fonts to try, so a computer
  with a font for one of them and not the others drew the others as `□□□`.
  Each has its own list now, ending in fonts that cover all three. Only the
  overlay was affected — the result card was always right, which is why the
  same text could look fine in one place and broken in the other.
- **Reading a page in a Latin alphabet on a Mac took six passes instead of
  one.** Squint reads an image several ways and compares, because Apple's
  reader will confidently read Russian as the Latin letters that look like
  it. That check stops early once a pass comes back in another writing
  system — so it never stopped early on English, German, French, Spanish or
  anything else written in Latin letters, and the most common case in the
  app was the slowest one in it. The other alphabets are now ruled out
  cheaply, at low resolution, and full accuracy is spent only where
  something turns up. Naming the source language in Settings skips the
  check entirely.
- **Windows leaked system resources on every snip.** Around ten per snip,
  never returned. Nothing visible in a single session; it stops Squint
  slowing down over a long one.

### Added

- **`time-read.bat`** — a diagnostic that times each stage of a screen read
  and writes `time-read.txt` beside it. Reads only, changes nothing. It is
  what found the language-pack fault above: "reading is slow" and "reading
  is wrong" look identical from the outside, and the timings showed reading
  had never been slow.

---

## 1.10.0 — 2026-09-02

### Fixed

- **A busy Gemini was shown as a rejected key.** When the model is busy
  Squint raises its own sentence — *"Gemini is busy at the moment —
  Google's side, not your key"* — and then checked whether that was a busy
  error by looking for words like `503` and `overloaded`. Its own message
  contains none of them, so the app failed to recognise what it had just
  said, marked the key red, and hid the other keys' results behind the
  failure that wasn't one.
- **Two copies of Squint could run at once on macOS.** The single-instance
  guard was a Windows mutex with no equivalent on the Mac, so both copies
  opened a window and both registered the same global shortcut — which is
  why the hotkey could stop working and quitting one app didn't give it
  back. A second launch now says where the first one is.
- **The Dock showed a Python icon.** macOS reads an app's icon and name from
  the running executable's path, and the launcher was exec'ing an
  interpreter outside the bundle. A copy now lives inside `Squint.app`, so
  the icon and the menu-bar name are right. It's verified before use and
  falls back to the old path if anything is wrong — a bad icon is a
  blemish, an app that won't start is not.
- **The Mac bundle's version was hardcoded to 1.2.0** through eight
  releases. It comes from `VERSION.txt` now.
- **The shortcut fields took no keys on macOS.** They lit up when clicked
  and then ignored everything you pressed — and both fields stayed lit at
  once, which is the clue: the widget called `focus_set()` on itself and
  listened for keys there, and a Tk window on macOS accepts mouse clicks
  while not being the key window. So the click landed, the field lit, focus
  never moved, and no keystroke arrived. Nor did the focus-lost event that
  was supposed to disarm the other field. It now brings the window forward
  and listens at the window, only one field arms at a time, and a field
  left armed gives up after half a minute.
- **⌘ and a letter, with nothing else, is refused as a shortcut.** A
  clipboard shortcut set to plain ⌘C takes the system's own copy away
  everywhere — including from the settings panel you would use to undo it.
  ⌘ with ⌃ or ⌥ beside it is unaffected.

### Added

- **Install instructions on every release page.** The description was only
  the changelog, which is right for someone who has the app and wrong for
  everyone else — and a download link lands strangers exactly there.

---

## 1.9.2 — 2026-09-02

### Fixed

- **The first snip on a new machine was slow enough to look broken.** Three
  things stacked, and only on a machine where nothing is cached — which is
  exactly the machine deciding whether the app works.

  Splitting the remembered Gemini model in two in 1.9.0 gave each job its
  own discovery walk, so a fresh key fetched the model listing **twice** on
  its first snip: once to read the picture, again to translate it. One
  listing settles both now, and testing a key warms them, so the first real
  snip pays no discovery at all.

  An image request waited **75 seconds** before giving up — on the *first*
  attempt, with two retries behind it and three models to walk. The first
  attempt is 20 seconds now; the long ceiling belongs on the retry.

  And nothing capped the whole walk. Every request had an opinion about how
  long it could take and no part of the code had an opinion about how long
  the person should wait. There is a budget now, and it clamps each attempt
  to the time actually left rather than starting a 75-second request with
  four seconds on the clock.

### Changed

- **A bigger snip gets more time, not less detail.** The picture sent for
  reading stays at full resolution — a cap that quietly degrades a
  whole-screen capture is a size limit that does not announce itself, and a
  4K grab squeezed to 1100 pixels turns body text into four pixels. The
  time budget grows with the capture instead, up to 90 seconds.

---

## 1.9.1 — 2026-09-02

### Fixed

- **The snip frame had a square corner poking out of each rounded one.**
  The four elbows were joined with a rectangle, which put a sharp corner
  straight back outside every arc — the one thing the rounded mark exists
  to avoid. The hairline now spans only the flats; the corners belong to
  the arcs.

### Added

- **A translated overlay carries the same mark.** Without it the
  translation is a rectangle of English sitting flush against the page it
  replaced, with nothing to say where the translation stops and the
  original starts — and the better the renderer matches the page's own
  styling, the harder that is to see. Same shape as the snip frame and the
  icon: you drag the mark, and what comes back is inside the mark. It is
  drawn into the picture, so zooming redraws it at the new size.
- **Breathing space between the mark and the text**, filled with the
  page's own background colour rather than white — a light band round a
  dark article would announce itself before anyone read a word. The window
  shifts by the same margin so the overlay still lands on the text it
  replaced.

---

## 1.9.0 — 2026-09-02

### Fixed

- **One snip could spend twenty Gemini requests.** When the overlay's
  single joined request came back with the wrong number of lines, Squint
  translated each line on its own. Against Google that is slow and free;
  against Gemini it is twenty calls off one screenshot — and Gemini is the
  engine most likely to cause it, because a language model reflows text,
  merging two short headlines or splitting a long one. That is where a
  day's allowance went after "barely any" translating. The whole batch now
  goes to a cheaper engine in one request instead.
- **The key test painted four answers one colour.** An exhausted Gemini
  allowance showed a working Google key in red. Each key now has its own
  mark beside its field — green for working, red for rejected, amber for
  "could not be judged", which is what busy and out-of-allowance actually
  are. Neither is a verdict on the key.

### Added

- **A Gemini request tally**, beside the Google and Cloud Vision counters:
  *"Gemini: 34 requests today from this computer"*. No denominator, on
  purpose — Google does not report what is left and has stopped publishing
  the free-tier figures, so a fraction would be a number the app invented.
  What it can say is what it spent, which is the question you ask when the
  allowance goes sooner than expected. It is blind to other apps using the
  same key, and says so.

### Changed

- **Overlays use Gemini's lite model, cards use the full one.** Same key —
  the model is chosen per request, not per key. An overlay is headlines and
  button labels where the context a full model brings is worth least and
  the request count is highest; a card is one passage where that context is
  the whole reason for using Gemini. Free-tier allowances are listed per
  model, so the two also draw on separate pots.

---

## 1.8.1 — 2026-09-02

### Fixed

- **The pack list is alphabetical by the name you read**, not by the tag
  behind it. Sorting on the tag is alphabetical and still looks wrong:
  `zh-CN` put Chinese after Turkish, `sr-CYRL-RS` put Serbian after
  Slovenian. Nobody scans a list of languages by their BCP-47 codes.
- **"On this computer" now explains its refusal instead of listing what it
  tried.** It said *"No translation service could be reached. Tried 1 —
  offline: not installed"*, which is true, internal, and useless to
  somebody who had just installed a Windows language pack called Chinese
  and could not see why Chinese would not translate. The message now says
  plainly that a **language pack lets this computer read a language** while
  the **offline engine translates it** — two separate downloads that happen
  to share a language name — and where to get the second one.

---

## 1.8.0 — 2026-09-02

### Changed

- **One Engine setting instead of two.** Reading and Translating were
  separate dropdowns with five answers each — twenty-five combinations, of
  which about four are things anybody wants, and answering it needed you to
  already know that Windows reads but cannot translate, that DeepL
  translates but cannot read, and that Gemini does both slowly. There is
  one control now — Automatic, On this computer, Gemini, Google Translate,
  DeepL — with a line underneath saying what it resolved to: *"Reads with
  Windows (de, en, zh). Translates with Gemini."* Existing settings migrate
  to the nearest profile.
- **Automatic picks per job.** An overlay is twenty short lines with you
  watching the screen, so it uses the quickest good engine. A result card
  is one passage you are about to read properly, so it uses the best one.
  Gemini's slowness now lands where you would accept it and never where you
  would not.
- **A profile that needs a key you do not have is greyed**, with the reason
  beside it, instead of being selectable and quietly doing something else.

### Fixed

- **"On this computer" was sending your text to Google.** If the offline
  engine was not installed it fell through to the web services, like every
  other choice does — a rule written the day Gemini's quota ran out and a
  pinned engine left the app dead. It is the wrong rule here: someone
  choosing *offline* may be choosing it so that nothing leaves the machine,
  and quietly posting their text to a free endpoint is not a smaller
  failure than not translating. It now refuses and says why.

### Added

- **The snip frame is Squint's own mark** — four thick rounded corners
  joined by a hairline, the shape from the icon, instead of a plain
  rectangle.
- **"Always read with the cloud engine"**, under the engine setting. Squint
  normally reads on your computer and only asks the cloud when the reading
  looks like nonsense; that check is a good guess rather than a certainty,
  and this stops you arguing with it.

### Changed

- **Zoom steps are gentler** — about twelve per cent a notch instead of
  forty, so the overlay grows rather than leaps.

---

## 1.7.0 — 2026-09-02

### Fixed

- **"Overlay text size" did not change the overlay.** It set the font on
  the result card, and the translation drawn over the page ignored it
  entirely — so raising it because the writing over the page was too small
  changed the one thing you were not looking at. It is called **Text size**
  now and it does both.
- **The overlay stopped shrinking text past reading.** English runs about
  twice as long as Chinese and has to go back into the box the Chinese
  occupied, so on a dense page the renderer shrank until it fitted — with a
  floor of seven pixels. The floor is your Text size setting now, and below
  it the answer is to take more room instead: a block may spill a little
  past the gap under its line rather than cut the sentence off with an
  ellipsis.

### Added

- **Zoom on an overlay** — Ctrl and the mouse wheel, or `+` and `−`, with
  `0` back to life size. It redraws at the new size rather than magnifying
  what was already drawn, so the letters get sharper as well as bigger.
- **A note about the free Gemini allowance**, beside the key. It gives no
  number on purpose: Google stopped publishing the free-tier figures, the
  allowance has changed more than once, and it is per Google account rather
  than per app. It says what spends it, what happens when it runs out, when
  it resets, and where your own limits are.

---

## 1.6.4 — 2026-09-02

### Added

- **A real progress bar while a pack installs.** 1.6.3 offered a clock and
  said the percentage was unknowable. It wasn't: `Add-WindowsCapability`
  reports through the one PowerShell stream a hidden shell cannot
  redirect, but `dism.exe` — the same servicing engine — prints a
  percentage, which anyone who has watched an install in their own console
  has seen. The install goes through DISM now and the bar follows it. The
  clock stays for the opening stretch, when DISM says nothing yet.

### Changed

- **The pack list is plainly alphabetical.** German sits between Greek and
  Danish, where the alphabet puts it, instead of being grouped at the
  bottom with the other installed packs. The ● and ○ marks already say
  which is which, and hunting for a language you cannot find is worse than
  scrolling past three you have.
- **The install caption says how big a pack is** — a few megabytes, with
  the minutes going on Windows putting it in place rather than on
  downloading. The ~2 GB in the line below it belongs to the offline
  translation engine, an entirely separate thing, and the two were being
  read as one.

---

## 1.6.3 — 2026-09-01

### Fixed

- **The install result no longer vanishes when you open the dropdown.**
  The result and the "Free, and nothing to sign up for…" caption were the
  same line, so looking at another language wrote over the answer. An
  install that had run for minutes then looked as though the button had
  never been pressed. They are two lines now, and only the caption changes
  with the selection.
- **The install shows a clock instead of looking hung.** Windows downloads
  the pack itself and reports nothing while it does — over four minutes on
  the machine this came from, against a panel that said "takes a few
  minutes" once and then sat still. It now counts up, names the pack, and
  says it is safe to leave open.

### Changed

- **The warning offers the Gemini key first and the Windows pack second.**
  It used to say "add one below", so that is what people did — and the
  pack is the harder path by a distance: administrator rights, minutes of
  downloading, and on a managed work laptop it may be refused outright.
  The key takes about a minute and reads every language. The pack keeps
  its place, with its actual reason stated: nothing leaves the computer,
  and it works with no network at all.
- **The pack list uses the same ● and ○ marks as the offline translation
  list**, instead of trailing "(installed)". Two lists in one panel
  answering "do I have this one" in two different notations read as two
  unrelated controls.

---

## 1.6.2 — 2026-09-01

### Fixed

- **Installing a Windows language pack never worked, and said it had.**
  Two faults stacked into one silent failure.

  Windows calls the Chinese OCR pack `Language.OCR~~~zh-CN~0.0.1.0`.
  Squint asked for `zh-Hans-CN`, which is what the OCR engine calls the
  language *after* the pack is installed — a different vocabulary for the
  same thing, and not a capability that exists. So Windows refused.

  It refused quietly. The install runs in a second, elevated PowerShell,
  and `powershell.exe` exits 0 even when the command inside it failed, so
  Squint read "0" and reported **Installed**. Every failed install has
  been reported as a success since the feature shipped.

  The pack list is now transcribed from a real machine instead of reasoned
  out — it was also offering Hindi, Thai, Vietnamese, Ukrainian and Hebrew,
  which Windows has no OCR packs for, while missing Bulgarian, Croatian,
  Slovak, Slovenian, Mexican Spanish, Canadian French, European
  Portuguese, Hong Kong Chinese and both Serbians, which it has. The
  elevated command now checks the pack exists, stops on the first error,
  and reads the state back afterwards, so "Installed" means Windows
  confirmed it and every other outcome says what happened: not offered on
  this edition, download failed, permission declined, or still finishing.
- **An installed pack went on being offered as something to install.**
  `zh-CN` and `zh-Hans-CN` were compared as strings, so the pack Squint
  had just added did not match the language the engine reported. That also
  made the restart advice permanent — it could never see the pack, so it
  could never stop asking.

### Changed

- The pack list tells the three Chinese and two Serbian packs apart in
  words — Simplified, Traditional, Hong Kong, Cyrillic, Latin — rather
  than leaving the tag to do it alone.

---

## 1.6.1 — 2026-09-01

### Fixed

- **Installing a Windows language pack left the rest of Settings saying it
  had not been installed.** The green line said "Installed"; the amber line
  three inches above it still said "This PC can only read de, en", and the
  dropdown went on offering the pack that had just gone on. All three are
  drawn when the panel is built and none of them was told. Together they
  read as "the install did not take", which sent people looking for a
  Windows restart they may not have needed.

  All three are refreshed now, and Squint checks whether the new pack
  actually answers before saying anything about restarting: "Squint can
  read Chinese now" when it does, and a plain sentence plus a **Restart
  Squint** button when it does not. The old message hedged both ways every
  single time, which is the same as saying nothing.
- **PowerShell stopped being quoted at people.** When Windows refuses to
  list its packs without administrator rights, the refusal was pasted into
  the note under the row and cut off at 120 characters, so it arrived on
  screen as "(Get-WindowsCapability : The". The note now explains the
  situation on its own; the raw text is kept for a bug report.

### Added

- **The App language setting is back**, with English in it and a line
  underneath saying more are coming. Removing the control in 1.6.0 said the
  feature had been taken away, which is a different and worse message than
  a short list. The eleven part-finished translations are still in the
  code, and each one appears here as it is completed.

---

## 1.6.0 — 2026-09-01

### Fixed

- **"This edition of Windows offers no text-recognition packs to add" was
  wrong.** Listing them needs administrator rights, which I had assumed
  only installing did — so the query failed, the failure was swallowed, and
  a PC that offers a dozen packs reported none. An empty list is a worse
  answer than a guess, because it is a confident one. Squint now falls back
  to the names Windows uses anyway, and works out what is already there by
  asking the OCR engine, which answers without elevation.
- **A language chosen in 1.5.0 no longer sticks.** It was stored in
  settings, so it would have survived this release and left exactly the
  window this change removes — with no picker left to switch back.

### Changed

- **The app is English only again.** Twelve languages were offered and it
  was worse than offering none: the headings went through the translation
  table and the explanatory prose did not, so a German window had German
  titles and English paragraphs. That reads as broken software.

  The whole app is 282 strings and about 5,300 words, mostly the prose in
  Settings — a real translation job per language, not a table of buttons.
  The rule is structural now: a language appears only when every string is
  translated into it, and a test refuses to offer one otherwise. The
  translations already written are kept, not thrown away.
- **The warnings point at the button** instead of reciting six steps
  through Windows Settings. Telling somebody to go and do by hand the thing
  the app is offering to do reads as an app that does not know what it can
  do.
- **The offline message no longer ends in an import error.** "No module
  named 'argostranslate'" is true, is the reason, and is not for somebody
  who wanted to read a bicycle advertisement.

### Removed

- The App language dropdown, while there is only one language in it. A
  control with one option is worse than no control.

---

## 1.5.0 — 2026-09-01

### Fixed

- **The Windows pack button installed the wrong language.** It took the
  language from the source dropdown, so with the source set to English it
  offered en-US — true, useless, and nothing to do with the Chinese you
  were trying to read. The question was wrong: "what am I reading right
  now" and "which pack should this computer have" are different, and only
  the second one is worth acting on.

### Added

- **A picker for the Windows text-recognition packs.** It lists what
  Windows actually offers on this edition, marks what is already there, and
  installs the one you choose. Always visible on Windows now, not only
  after something has already failed — somebody who knows they will be
  reading Chinese next week can add it today. The Install button is the
  blue one.
- **Twelve app languages** — English, Deutsch, Français, Español, Italiano,
  Português, Svenska, Русский, हिन्दी, 中文, 日本語, 한국어 — each named in
  its own language, because a list written in English is no use to the
  people this setting is for.
- **A Restart now button** when you change the app language. Every label is
  built when the window is built, so nothing already on screen changes
  until Squint starts again; "restart to see the change", left sitting
  there, makes the setting look as though it did nothing.

### Changed

- Choosing an engine that cannot run now says so where you chose it, not
  only in the result card. (Carried over from 1.4.1.)

---

## 1.4.1 — 2026-09-01

### Fixed

- **Selection translate returned something you had copied earlier, and
  called it the selection.** Selecting German on a page and pressing the
  shortcut brought back Squint's own release notes, copied ten minutes
  before. Comparing the clipboard before and after cannot catch this: if
  the "before" read comes back empty — another app holding the clipboard,
  a moment's bad luck — then whatever was already there looks like a fresh
  copy. On Windows Squint now reads the system's clipboard change counter
  instead, which moves when something is copied and does not move when
  nothing is, whatever the text says.
- **Choosing an engine that cannot run no longer looks like it is
  running.** With "Offline, on this computer" selected and no offline model
  downloaded, every translation quietly went to the free online service —
  the dropdown said one thing and the result card said another. Settings
  now says which, and why, in amber. The same for a keyed engine chosen
  with no key saved.

  The falling back itself is deliberate and stays: it is what keeps the app
  working when a service is down. Doing it silently was the fault.

---

## 1.4.0 — 2026-09-01

### Added

- **A button that installs the Windows text-recognition pack.** When this
  PC cannot read the language you have chosen, Settings → Engines now
  offers to fix it rather than describing where the setting lives. The old
  advice was six steps in somebody else's app, given to someone who had
  just been told the thing they tried does not work.

  This is the rung below every API key and the only one that cannot run
  out: free, no account, no card, no quota, and once the pack is on the
  machine it stays. Windows does the downloading through its own update
  channel — Squint fetches nothing.

  Two things are said before it starts rather than discovered afterwards:
  Windows will ask for permission, and it takes minutes. On a work computer
  the permission may be refused, and that is reported as an answer rather
  than as a fault — nothing an app can do gets round a policy.

---

## 1.3.0 — 2026-09-01

### Fixed

- **The window did not use the space you gave it.** Enlarge it and
  everything stayed pinned to the top left with a band of empty grey
  underneath — at full height, more than half the window was nothing. The
  boxes asked for the height their text needs, which is right and is what
  keeps the window small when there are two words in it, but that request
  was also the ceiling. They now grow into whatever room the window has
  spare, and shrink back when it does.

### Added

- **Squint says when a shortcut is likely to be taken by another app.** One
  modifier and one letter — ⌘E, Ctrl+E — registers perfectly and then loses
  to whichever application is in front, so it works on the desktop and does
  nothing in the browser you were trying to read. That is the most
  confusing way for a shortcut to break, and it looks like the app rather
  than the collision.

  It is a warning, not a refusal: the shortcut does work, and taking away
  one somebody is already using would be worse than the collision.
- **Everything the OS is holding is given back on the way out**, including
  when Squint is killed rather than quit. A global shortcut still
  registered by a dead process does nothing until the machine restarts.
  Also, the tray icon and the hotkeys are now released independently — they
  shared a try block, so one failing on the way out left the other behind.

---

## 1.2.1 — 2026-09-01

### Fixed

- **Testing a key was spending the key's daily allowance.** The retry added
  in 1.1.1 tried three times per model across up to three models, and Save
  & test does that twice — once for translating, once for reading. Up to
  eighteen requests to answer "does this key work", and a request that
  times out on this side has usually still been counted on Google's.
  Pressed repeatedly while chasing a timeout, that is most of a day's free
  allowance gone before the app has translated anything. Testing a key now
  asks once.
- **When the allowance really is gone, Squint stops asking for a quarter of
  an hour.** Every snip was otherwise paying a round-trip to be refused
  before this computer's own reader took over — so the app got slower at
  the exact moment it had stopped being able to use the slow thing. It is a
  rest, not a write-off: limits are per minute as well as per day.

---

## 1.2.0 — 2026-09-01

### Added

- **Settings → Test connection.** Says which layer is refusing, instead of
  leaving you to guess: does the name resolve, does a connection open, does
  the encrypted handshake complete, does Google answer. It needs no key —
  being told off by Google proves everything underneath is working.

  The step that matters on a company network is the third one. A proxy that
  opens encrypted traffic to inspect it presents its own certificate;
  Windows has been told to trust it, so browsers are content, and Python
  has not, so the app fails. That is exactly the shape of "the page opens
  in Brave but Squint times out", and nothing in the app could previously
  tell you so.
- The same report goes into `diagnose.bat` and `diagnose.command`, and into
  the log every time you press the button.

### Fixed



- **"The read operation timed out" was shown as a rejected key.** A read
  timeout is not wrapped the way other network errors are — it arrives as a
  bare socket error partway through reading the reply, so it escaped every
  handler and landed in red beside the key. It is now caught, treated as
  temporary (retried, then handed to the next model, then to another engine
  entirely), and explained.
- **Waiting 20 seconds was not long enough.** That number was inherited
  from the 5-second default used for small REST calls. Generating now waits
  45 seconds, and reading a picture 75.
- **The message now names the address.** Gemini lives on
  `generativelanguage.googleapis.com`, which is a *different* domain from
  the Cloud APIs — so a corporate network can allow Google Translate and
  Cloud Vision while blocking Gemini, and every symptom of that points at
  the key instead. If it times out every single time, that is the thing to
  suspect, and the app now says so.

### Changed

- **Screenshots are scaled down before being sent to Gemini.** A whole 4K
  monitor is several megabytes as PNG and a third bigger again as base64;
  on an office connection that upload was most of the wait. Text stays
  legible far below native resolution, and the coordinates come back on a
  0–1000 scale, so they are mapped back onto the full-size picture and the
  overlay still lands where it should.

---

## 1.1.1 — 2026-09-01

### Fixed

- **"Gemini is currently experiencing high demand" was treated as a broken
  key.** Google's free tier answers HTTP 503 often, and Squint gave up on
  the first one — then Settings printed it in red beside the key, so a key
  made thirty seconds earlier was reported as rejected on the day it was
  made. Nothing was wrong with it. A busy model is now asked again after a
  short pause, then the next model is tried (capacity is per model — "flash
  is busy" says nothing about flash-lite), and if everything really is busy
  the app says so in those words instead of blaming the key.
- **A busy model is no longer forgotten.** The remembered model name was
  being cleared whenever it did not answer, so every busy minute cost an
  extra request to list the models again. It is only cleared when the model
  has actually been retired.

---

## 1.1.0 — 2026-09-01

### Added

- **Gemini can read the screen, not just translate it.** A Gemini key comes
  from Google AI Studio: a Google account, no credit card, about a minute.
  Google Cloud demands card details before it will let anyone use even its
  free tier, which is where four testers stopped. One free key now covers
  both halves of the app.
- **Settings → Get a free key.** Opens the key page, and then fills the key
  in for you: Squint watches its own clipboard while that tab is open and
  types the key into the box when you copy it. Google will not show a key
  twice, and coming back to an empty field with no memory of whether you
  copied it is how people end up with four keys and no idea which is in
  use. The watching stops at the first key, or after a few minutes.
- **Reading text → Gemini (free key, no card)** in the Engines list.

### Changed

- On Automatic with both keys saved, **Cloud Vision still leads.** It
  measures where text sits rather than estimating, and its terms keep your
  text out of Google's training data. Gemini is the rung below it, and the
  whole ladder for anyone without a Cloud key.
- Settings now says plainly that Gemini's free tier may use what it reads
  to improve Google's products, and that this is the reason to use Cloud
  Vision for anything confidential — rather than presenting the paid key as
  an upgrade you are nagged towards.
- **Save & test** now also proves the Gemini key can read a picture. A key
  that translates does not necessarily read one, and finding that out
  mid-snip is finding it out too late.

---

## 1.0.0 — 2026-08-31

The first numbered release. Everything below this line is a date-and-letter
build from before versions had names.

### Fixed

- **Selection translate on macOS — the actual cause.** It was never the
  Accessibility permission. Squint put a "Reading selection…" pill on
  screen *before* sending ⌘C, and on macOS showing a window brings the
  application to the front. The copy then went to whatever was frontmost —
  Squint, and its own pill, which has nothing selected in it. The browser
  one window behind never saw the keystroke.

  It looked exactly like a permission failure and had the same workaround
  (press ⌘C yourself and the shortcut works), which is why it took three
  builds to find: it survived the permission being granted. Nothing is
  drawn before the copy now. The pill still appears for the translation,
  which is the slower half. Windows is unchanged — no such rule there, and
  the wait feels dead without it.

---

## Pre-1.0 build (az) — 2026-08-31

### Fixed

- **Selection translate still fell back to the clipboard on macOS, with no
  way to find out why.** (ay) labelled the fallback honestly — the card
  said `clipboard →` — but the explanation went to a tray notification,
  which on macOS arrives through pystray and, on the Mac this was reported
  from, arrives nowhere at all. So the shortcut over a German paragraph
  returned a GitHub URL, correctly labelled and completely unexplained.
  The explanation is now the card itself, at the pointer.
- **"Switch on the entry for Squint" described a row that did not exist.**
  macOS only lists an app under Accessibility once the app has asked for
  the permission, so the instruction sent people hunting for a Python
  binary inside `.venv`. Squint now asks — macOS puts up its own dialog
  and adds the entry.
- **The release zip is now called `Squint.zip`.** A release went out where
  the zip arrived on GitHub as `Squint2026.08.31ay.zip` while
  version.json pointed at `Squint-2026.08.31-ay.zip` — same file, right
  checksum, 404 on every install. The build number in the filename bought
  nothing the tag did not already carry; it only gave the name four more
  characters to lose.
- **"No release published yet, or the update address is wrong" was shown
  for a missing zip**, in a window that was at that moment displaying the
  new build's release notes. A 404 on the feed and a 404 on the download
  are different problems with fixes in different places, and they now say
  which.

### Added

- **Settings → Shortcuts → Copying for you.** Says whether macOS is
  allowing the clipboard shortcut to press ⌘C, with a button that asks for
  the permission and opens the right pane. Before it fails, rather than
  after — Apple's refusal is silent by design, and the way it otherwise
  surfaces is a translation of something you copied earlier.
- **`make_release.py --verify`** checks a published release the way the app
  will: fetches version.json, downloads the zip it names, compares the
  checksum. Publishing is four manual browser steps and each can
  half-succeed, all with the same symptom.

---

## Pre-1.0 build (ay) — 2026-08-31

### Fixed

- **Selection translation did nothing on macOS, and said it had worked.**
  macOS refuses to let a program press ⌘C on your behalf unless it is
  ticked under Privacy & Security → Accessibility, and it refuses
  *silently*. Squint could not tell that apart from "nothing was
  selected", so it fell back to whatever was already on the clipboard,
  translated that, and labelled the card `selection →`.
- **The same translation coming back over and over.** Same fault: it was
  the same clipboard every time.
- **Your API key appearing as a translation.** Also the same fault — the
  key was the last thing on the clipboard. Anyone who saw this should
  treat that key as exposed and rotate it.
- **Snipping only worked on one of three monitors.** Each display gets its
  own overlay, and the first one was taking a Tk grab — which routes every
  mouse click in the whole app to that one window. Clicks on the second
  and third monitors went to a window that was not under the pointer.

### Added

- Squint now asks macOS whether it is allowed to copy *before* trying, and
  if it is not, says so once, with where to switch it on and that Squint
  has to be restarted afterwards.
- The card says where the text came from: `selection →` when it read your
  selection, `clipboard →` when it fell back to what you had already
  copied. It never claims the first when it did the second.
- This changelog.

---

## Pre-1.0 build (ax) — 2026-08-31

### Added

- **Squint updates itself from GitHub.** Settings → Updates → Check for
  updates downloads the new code and restarts. No reinstall, no second
  setup — an update replaces code and never touches `.venv`, your
  settings, your keys or your downloaded languages.
- **A daily background check.** It fetches one small file once a day and,
  if there is something new, puts a line under the title. It never
  downloads or installs anything by itself and it is not a dialog. Switch
  it off in Settings → Updates.
- **A "Buy me a coffee" button** in the footer, as quiet as the copyright
  line beside it.
- **`tools/make_release.py`** — builds the release zip and the
  `version.json` that points at it, checksum filled in. It refuses to
  build if it finds anything shaped like an API key in a file it is about
  to publish.

---

## Clipboard shortcut rewrite

### Changed

- **The clipboard shortcut copies for you.** Select text, press the
  shortcut, read the translation. It used to translate whatever you had
  already copied, which made reading one sentence three actions — select,
  ⌘C/Ctrl+C, shortcut — and forgetting the middle one produced "copy
  something first". True, and beside the point.
- It waits for the shortcut's own modifier keys to come up before sending
  the copy, and compares the clipboard before and after, because a copy
  can silently do nothing (an image, a locked PDF, a window with no
  selection).
- Your own clipboard is put back afterwards, unless the app was going to
  fill it with the translation anyway.

### Fixed

- **Clipboard translation could not read Chinese on Windows.** Copying
  Chinese from a browser and pressing the shortcut said "Clipboard has no
  text" about a clipboard that plainly had text in it. Tk asks Windows for
  `CF_TEXT` — the pre-Unicode ANSI format — and no English-locale code
  page can hold 前不久. Windows had the real text in `CF_UNICODETEXT` the
  whole time. Same fix applies to the paste button in the Translate pane.
- An empty clipboard now says what to do about it rather than only stating
  the fact.

---

## Setup and multi-monitor

### Fixed

- **The selection box was invisible while snipping.** The multi-monitor
  rewrite gave every display its own overlay and screenshot, but one
  attribute did not come across: `_bright`, the undimmed picture the
  selection patch is cut out of, was read on every mouse-move and set
  nowhere. Tk catches exceptions inside callbacks and prints them to a
  console nobody watches, so the drag handler died on its first line while
  the release handler kept working — a snip that translated correctly with
  no visible box at all.
- **A drag now stays on the display it started on.** Moving the pointer
  onto another monitor swapped the start point and canvas out from under
  the stroke in progress.
- **Four snip tests were proving nothing.** They fed a fake desktop to a
  capture path the picker no longer calls, so they were quietly running
  against the real screen.

### Changed

- **`setup.bat` installs Python again, through winget.** The old version
  fetched `python.exe` into `%TEMP%` with a PowerShell policy override and
  ran it `/quiet` — the exact shape of a malware dropper. Defender blocked
  the download and the zip never reached anyone. winget is Microsoft's
  own package manager, already on the machine, so nothing in the script
  fetches or executes anything. Falls back to python.org if winget is
  missing or blocked by policy.
- Setup puts the new Python on the current window's PATH itself, so you do
  not have to close the console and run setup a second time.

---

## OCR and Google Cloud Vision

### Added

- **Google Cloud Vision reads the screen when the computer cannot.** It
  uses the Google key already saved for translation, needs nothing
  installed, and is only reached after the machine's own reader has failed
  or come back with nonsense. 1,000 screenshots a month are free; the
  count is in Settings. One snip costs one request, not two.
- **Reading text is a dropdown**, beside Translating: automatic (this
  computer, Google behind it), this computer only, or Google Cloud Vision
  for everything. It used to be a plain label with the cloud reader hidden
  behind a switch in another card.
- **Settings → Set up Google.** A checklist of the three things that have
  to be true — a key, Cloud Translation on, Cloud Vision on — each with a
  button to the exact console page that fixes it and a dot that says
  whether it is really done. It asks Google rather than assuming. This
  exists because all four ways it can fail arrive as the same bare 403.
- **Settings → Learn how to add APIs.** What a key is, which one you want,
  what to click, and what each costs. It opens with "you may not need any
  of this".
- **Settings → Engines** lists which languages this PC can read;
  `diagnose.bat` reports the same list.

### Fixed

- **Windows read Chinese with an English recogniser.** Windows does no
  language detection and reports no confidence — it reads one language per
  pass, and with none chosen the app let the PC's display language decide.
  Pointed at Chinese it does not fail, it returns nonsense
  (探店东风风神L8Y came back as iRERJXIJXFL8Y) which was then translated and
  drawn over the page. Every installed pack is now tried and the readings
  compared, with real script beating a Latin misreading.
- **Automatic asks Google sooner.** A Chinese page read as four lines,
  only one obviously nonsense, passed the old 60%-junk test. Any jumbled
  word on a page with no CJK, Cyrillic or Arabic now gets a second
  opinion.
- **Watermarks are left out of the translation.** A document tiled with a
  diagonal grey name and address was being read, translated, and drawn
  back across the sentences underneath — in enormous type, because a
  diagonal box is tall. A line is ignored when two of three are true: it
  repeats three or more times, it is tilted more than six degrees, or it
  is too faint to be ink. Two signals, not one: a repeated line might be a
  table heading and a pale one might be a caption.
- **Save & test now tests the key for reading as well as translating.**
- **A reading that is mostly jumble is never drawn over your screen.**
- **The result card closes when you click somewhere else.** It did not,
  because Tk's app-wide click binding is app-wide in the literal sense: a
  click on Outlook or a browser goes to that program and Tk never hears
  about it. The mouse button is now read from the OS directly.
- **The card no longer floats above every other window.** It opens on top,
  so it cannot appear behind the page it just translated, and becomes an
  ordinary window a second and a half later.

---

## Earlier

### Changed

- Lighter type in the buttons, one height for every control, labels that
  cannot overflow their boxes, and text boxes that follow their contents.

### Removed

- **The offline engine is no longer installed by default.**
  `argostranslate` depends on stanza, which depends on PyTorch: several
  gigabytes of machine-learning framework pulled in so the offline engine
  could split sentences, and on Windows it produced paths deep enough to
  break the installer outright. macOS keeps it, since it is already
  installed there. Windows users who want it: `requirements-offline.txt`.
