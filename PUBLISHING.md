# Publishing a release

Squint updates itself. People who have it press **Settings → Updates →
Check for updates**, and it downloads the new code and restarts. They never
run setup again.

That works because the app runs from source. A build is the code — about
350 KB — while the slow part of an install is the `.venv` full of packages,
and that does not change between builds. The updater replaces code and
leaves the environment alone.

---

## One-time: make the repository

1. Make a GitHub account at [github.com](https://github.com) if you have
   none.
2. **New repository**. Name it `squint`. **Public**. Do not tick any of the
   "initialize with" boxes.
3. You do not have to learn git. Releases can be made entirely in the
   browser — see below.

**Before the first push, read this once.** Everything in the repository is
public and stays public: deleting a file later does not remove it from the
history. Your API keys are not in this folder — they live in
`%APPDATA%\Squint` on Windows and `Application Support` on macOS — and
`make_release.py` refuses to build if it finds anything key-shaped. But the
rule to keep in your head is: if a key is ever in a file here for even a
minute, make a new key.

---

## Every release: five steps

### 1. Pick the version number

Versions are **MAJOR.MINOR.PATCH**.

| | when | example |
|---|---|---|
| **PATCH** | something broken now works, nothing else changed | 1.0.0 → 1.0.1 |
| **MINOR** | something new that was not there before | 1.0.1 → 1.1.0 |
| **MAJOR** | the app works differently enough that a habit has to change | 1.9.0 → 2.0.0 |

Bumping MINOR resets PATCH to 0; bumping MAJOR resets both. There is no
1.0.10 problem — the ordering compares numbers, not text, so 1.10.0 is
correctly newer than 1.9.0.

Put it on the first line of `VERSION.txt`: `Squint 1.0.1`.

### 2. Write down what changed

At the top of `CHANGELOG.md`, a section for the new version:

```
## 1.0.1 — 2026-09-04

### Fixed
- What was broken, in the words someone would use to report it.

### Added
- ...
```

Use **Fixed**, **Added**, **Changed**, **Removed** — only those four.
Removed is the one people leave out and the one that matters most: a
feature that quietly disappears is how a user decides the update broke
something.

This is not paperwork. It is where the release notes come from: the
GitHub description and the panel in Settings both quote this section, so
it gets written once and neither copy can go stale. `make_release.py` will
not build without it, and will not accept the previous version's section
left at the top.

`VERSION.txt` is the long explanation of *why* — the engineering log. The
changelog is the short version of *what*, for the person updating.

### 3. Build it

In the Squint folder:

```
.venv\Scripts\python tools\make_release.py --repo ratanpranay/squint
```

(macOS: `.venv/bin/python tools/make_release.py --repo ratanpranay/squint`)

It prints something like:

```
build   1.0.1
tag     v1.0.1
files   77  (384 KB)
sha256  987b3801cfadc...

wrote   dist\Squint.zip
        dist\version.json
        dist\RELEASE_NOTES.md
```

Three files in `dist`. Two get attached; the third is text to paste.

### 4. Make the release on GitHub

- Your repo → **Releases** → **Draft a new release**
- **Choose a tag** → type the tag it printed, exactly — `v1.0.1` — and pick
  **Create new tag**
- Title: `Squint 1.0.1`
- Description: paste the contents of `dist/RELEASE_NOTES.md`. Do not retype
  it — that is how a release ends up describing a different set of changes
  than the app does, with nothing to say which is right.
- Drag `Squint.zip` and `version.json` into the attachments box
- Wait for both upload bars to finish, then **Publish release**

### 5. Check it

First, from the Squint folder:

```
.venv\Scripts\python tools\make_release.py --verify --repo ratanpranay/squint
```

It does what the app does — reads `version.json`, downloads the zip it
names, compares the checksum — and says which of them is wrong if any is.
Publishing is four manual steps in a browser, every one can half-succeed,
and all the failures look identical from inside the app: the update is
offered and will not install.

Then in Squint: **Settings → Updates → Check for updates**. If it says you
are up to date, you are testing with the build you just published — try it
on another machine, or on an older copy.

---

## Things that go wrong, and what they mean

**"No release published yet, or the update address is wrong."**
The app is looking at `github.com/ratanpranay/squint/releases/latest/download/version.json`.
Either there is no release yet, or the repo name in `--repo` did not match
the real one. Rebuild with the right `--repo` and re-upload `version.json`.

**The update is offered, but installing it fails.**
The release has `version.json` and no zip — one of the two files did not
get attached. The check reads `version.json`, which is why the new build
and its notes appear; the install then asks for a file that is not there.
Edit the release, attach the zip, done. No new tag, no new build.

To see it for yourself, open
`github.com/<you>/squint/releases/download/<tag>/Squint.zip` in a browser:
a 404 is the whole diagnosis. `--verify` does exactly this and says so in
words.

**"The download does not match the checksum the release published."**
`version.json` and the zip are from different builds — usually the zip from
one run and the JSON from another. Rebuild both and replace both. The app
is right to refuse; unpacking a zip that is not the one described is how a
broken update becomes an app that will not start.

**The tag does not match.**
`version.json` contains the download URL, and that URL has the tag in it. A
tag of `v2026.08.31at` when the file says `v2026.08.31-at` gives everyone a
404. `make_release.py` prints the tag to use — copy it.

**Nobody sees the update.**
Releases are ordered by version number, and a version that sorts lower
than what people already have is not offered. Every version outranks every
old date-and-letter build, so anyone still on `(ba)` gets `1.0.0`. To push
a release that sorts lower anyway — pulling back a bad one, say — add
`"force": true` to `version.json` before uploading it.

---

## Rolling back a bad build

1. Fix the problem, bump the PATCH number, and publish normally. This is
   almost always the right answer.
2. If you need to put people back on an older build immediately: republish
   the old zip under a new tag, and edit `version.json` to add
   `"force": true`. Without that flag the older build sorts lower and will
   never be offered.

---

## What the updater will and will not touch

| Replaced | Left alone |
|---|---|
| `app/`, `tools/`, `assets/` | `.venv` — the packages |
| `VERSION.txt`, `CHANGELOG.md` | `languages/` — downloaded models |
| `requirements.txt` | |
| the `.bat` and `.command` scripts | `logs/`, `vendor/` |
| | your settings and API keys, which are not in this folder at all |

If `requirements.txt` changes between builds — rare — the app says so and
asks the user to run `setup.bat` once. Nothing else needs it.
