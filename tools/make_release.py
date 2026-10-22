"""Build a release zip and the version.json that points at it.

Run this, then drag the two files it makes onto a new GitHub release. That
is the whole publishing process.

It exists because the alternative is a checklist — zip the right folders,
work out the checksum, copy it into a JSON file, get the download URL
exactly right — and a checklist done by hand at the end of a long day is
how a release goes out with a checksum that does not match the zip. The
app refuses such a download, correctly, and the failure looks like the
updater being broken.

usage:
    python tools/make_release.py                  # into dist/
    python tools/make_release.py --repo you/repo
"""
import argparse
import hashlib
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.updater import DEFAULT_FEED  # noqa: E402

# What goes in a release: the code, and nothing that belongs to one
# machine. .venv above all — it is the slow part of an install, it is
# specific to the PC that built it, and the updater deliberately never
# replaces it.
# tests travel with every release, so a copy always exists outside the
# workspace they were written in.
INCLUDE_DIRS = ("app", "tools", "assets", "tests")
INCLUDE_FILES = ("VERSION.txt", "requirements.txt", "requirements-offline.txt",
                 "run_app.py", "README.md", "PUBLISHING.md", "CHANGELOG.md",
                 "setup.bat",
                 "build.bat",
                 "debug.bat", "diagnose.bat", "uninstall.bat", "Squint.bat",
                 "setup.command", "check.command", "debug.command",
                 "diagnose.command", "logs.command", "Squint.command",
                 "shortcut-test.command", "time-read.bat",
                 "time-read.command", "glossary.txt")
SKIP = ("__pycache__", ".pytest_cache", ".venv", ".git", "languages",
        "logs", "vendor", "dist", "build")


def build_stamp():
    with open(os.path.join(ROOT, "VERSION.txt"), encoding="utf-8") as fh:
        first = fh.readline().strip()
    for prefix in ("Squint build ", "SnapTranslate build ", "Squint "):
        if first.startswith(prefix):
            return first[len(prefix):].strip()
    return first


def changelog_section(stamp):
    """This version's entry from CHANGELOG.md, kind by kind.

    Release notes are written once, in the changelog, and everything else
    quotes them: the version.json the app displays, and the text pasted
    into the GitHub release. Two hand-maintained copies of the same list
    is one copy and one lie, and it is never the same one that goes stale.

    Returns [("Fixed", [item, ...]), ...] in the order the section has
    them, with each item's wrapped lines joined back into a sentence.
    """
    path = os.path.join(ROOT, "CHANGELOG.md")
    if not os.path.isfile(path):
        return []
    groups, kind, inside = [], None, False
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line.startswith("## "):
                if inside:
                    break                       # the next version's turn
                inside = version_of(line) == version_of(stamp) and \
                    version_of(stamp) is not None
                continue
            if not inside:
                continue
            if re.match(r"^\s*-{3,}\s*$", line):
                # The rule between versions. It is not a list item and it
                # is not prose: without stopping here it was glued onto the
                # end of the last sentence, and every release note ended
                # with a stray "---".
                break
            if line.startswith("### "):
                kind = line[4:].strip()
                groups.append((kind, []))
                continue
            if not groups:
                continue
            if line.startswith("- "):
                groups[-1][1].append(line[2:].strip())
            elif line.strip() and groups[-1][1]:
                # A wrapped continuation, or a second paragraph of the same
                # item. Either way it belongs to the item above it.
                groups[-1][1][-1] += " " + line.strip()
    return [(kind, items) for kind, items in groups if items]


def release_notes(limit=12):
    """This build's lines from VERSION.txt, as plain sentences.

    Two traps, both hit on the first run. Items are told from wrapped
    continuations by indentation, not by a leading dash — a sentence can
    wrap onto a line that happens to start with a dash, and treating that
    as a new item chopped one note in half. And the file keeps every past
    build, so the notes run on into the previous release unless something
    stops them: that is what the `---` line after each build's items is
    for.
    """
    items = []
    started = False
    with open(os.path.join(ROOT, "VERSION.txt"), encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not started:
                started = line.strip().lower().startswith("this build:")
                continue
            if re.match(r"^\s*-{3,}\s*$", line):
                break                       # end of this build's section
            if line.strip().lower().endswith("build:") or \
                    re.match(r"^\S", line):
                break                       # a new build's header
            if re.match(r"^ {2}- ", line):
                if len(items) >= limit:
                    break
                items.append(line.strip()[2:])
            elif line.strip() and items:
                items[-1] += " " + line.strip()
    return items


SEMVER = re.compile(r"^\s*v?(\d+\.\d+\.\d+)")


def version_of(text):
    """The version number in a line, or None. '## 1.0.0 — 2026-08-31' and
    '1.0.0' both give '1.0.0'; a lettered stamp gives None."""
    if not text:
        return None
    match = SEMVER.search(str(text).lstrip("# ").strip())
    return match.group(1) if match else None


def tag_for(stamp):
    """'1.0.0' -> 'v1.0.0'. The old stamps still work: '2026-08-31 (as)'
    -> 'v2026.08.31-as'."""
    version = version_of(stamp)
    if version:
        return "v" + version
    date = re.search(r"(\d{4})-(\d{2})-(\d{2})", stamp)
    letters = re.search(r"\(([a-zA-Z]+)\)", stamp)
    parts = ["v" + (".".join(date.groups()) if date else "0")]
    if letters:
        parts.append(letters.group(1).lower())
    return "-".join(parts)


def collect():
    out = []
    for name in INCLUDE_DIRS:
        base = os.path.join(ROOT, name)
        if not os.path.isdir(base):
            continue
        for folder, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP]
            for filename in files:
                if filename.endswith((".pyc", ".pyo", ".bak")):
                    continue
                path = os.path.join(folder, filename)
                out.append((path, os.path.relpath(path, ROOT)))
    for name in INCLUDE_FILES:
        path = os.path.join(ROOT, name)
        if os.path.isfile(path):
            out.append((path, name))
    return sorted(out, key=lambda pair: pair[1])


# Anything shaped like a credential. The keys live in the user's data
# folder, never in the app folder, so this should never fire — which is
# exactly why it is worth having. A key pasted into a file "just to test
# something" is invisible in a diff and permanent once published.
SECRETS = (
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{30,}")),
    ("Gemini API key", re.compile(r"\bAQ\.[A-Za-z0-9_\-]{20,}")),
    ("DeepL API key", re.compile(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-"
        r"[0-9a-f]{12}:fx\b")),
    ("OpenAI API key", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
)
# Test fixtures use obviously fake keys; they must not stop a release.
FAKE = re.compile(r"AIza(TEST|SOMETHING|THEKEY|FAKE|xxx)", re.I)


def check_for_secrets(files):
    """Refuse to publish anything that looks like a key."""
    found = []
    for path, arcname in files:
        if os.path.splitext(path)[1].lower() in (".png", ".ico", ".zip"):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except Exception:
            continue
        for label, pattern in SECRETS:
            for match in pattern.finditer(text):
                if FAKE.match(match.group(0)):
                    continue
                line = text[:match.start()].count("\n") + 1
                found.append("%s:%d looks like a %s"
                             % (arcname, line, label))
    return found


def changelog_missing(stamp):
    """Why this build has no CHANGELOG.md section, or None if it has one.

    A release with no written record of what changed is a release nobody
    can say anything about six months later — including the person who
    made it. The intention to write it up afterwards is real and the
    write-up never happens, so the check is here, where it can stop the
    build, rather than on a list.

    It looks for the build stamp inside a heading: `## 2026-08-31 (ay)`.
    Matching the stamp and not merely "some heading exists" is the point —
    the way this goes wrong is publishing (az) with (ay)'s notes still at
    the top, which a looser check would wave through.
    """
    path = os.path.join(ROOT, "CHANGELOG.md")
    if not os.path.isfile(path):
        return "there is no CHANGELOG.md"
    with open(path, encoding="utf-8") as fh:
        headings = [line.strip() for line in fh if line.startswith("## ")]
    wanted = version_of(stamp)
    if wanted:
        # Compare the version, not the whole line, so the heading is free
        # to carry a date beside it. Compare it as a version and not as a
        # substring, or 1.0.0 would be satisfied by a section for 11.0.0.
        if any(version_of(line) == wanted for line in headings):
            return None
    elif any(stamp in line for line in headings):
        return None
    return "CHANGELOG.md has no section for %r" % stamp


def plain(text):
    """Markdown emphasis off. This text ends up in a Tk label, where
    **bold** is four asterisks and `code` is two backticks."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text


def notes_text(stamp):
    """The changelog section as plain text, for version.json.

    Kept readable rather than markdown: this is displayed in a Tk label in
    Settings, where asterisks and backticks are just asterisks and
    backticks.
    """
    lines = []
    for kind, items in changelog_section(stamp):
        lines.append("%s:" % kind)
        lines.extend("- " + plain(item) for item in items)
        lines.append("")
    return "\n".join(lines).strip()


# Repeated on every release page on purpose.
#
# The changelog was the whole description, which is right for somebody who
# already has the app and wrong for everybody else — and a release page is
# exactly where a download link lands a stranger. The README says all of
# this, but the README is a click away and the person is here.
#
# The macOS line leads with `bash` rather than a double-click, and that is
# not pedantry: a zip fetched through a browser is quarantined, so
# double-clicking setup.command is refused as "from an unidentified
# developer". Typing bash in front of it sidesteps the refusal entirely.
INSTALL = """## Installing

**Windows**

1. Download `Squint.zip` below and unzip it anywhere.
2. Double-click **`setup.bat`**.
   If Windows says *"Windows protected your PC"*, click **More info >
   Run anyway** — the file is not signed, so this appears for everyone.
3. Wait 3-10 minutes, then say **Y** when it offers to start the app.
4. Press **Ctrl + Alt + X** anywhere: tap X to snip, hold X to see the
   page translated.

**macOS**

1. Download `Squint.zip` below and unzip it anywhere.
2. Open **Terminal**, type `bash ` (with a space), drag
   **`setup.command`** into the window, press **Enter**.
   *Double-clicking it is refused by macOS on a downloaded file. If you
   would rather click: right-click > Open > Open.*
3. Wait a few minutes, then say **y** when it offers to start the app.
4. Press **Control + Command + X** anywhere: tap X to snip, hold X to
   see the page translated.

Full notes, shortcuts and troubleshooting are in the
[README](https://github.com/ratanpranay/squint#readme)."""


def release_body(stamp):
    """The GitHub release description, ready to paste.

    It was being retyped by hand from the changelog for each release,
    which is how a release ends up describing a different set of changes
    than the app does.
    """
    parts = ["## Squint %s" % stamp, ""]
    for kind, items in changelog_section(stamp):
        parts.append("### %s" % kind)
        parts.append("")
        parts.extend("- %s" % item for item in items)
        parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("Already have Squint? **Updates > Check for updates** "
                 "(in versions before 1.48.22: Settings > Updates). "
                 "Everything else here is for a first install.")
    parts.append("")
    parts.append(INSTALL)
    return "\n".join(parts) + "\n"


def verify(repo, expect_sha=None):
    """Check a published release the way the app will, and say what is
    wrong in the app's own terms.

    Publishing is four manual steps in a browser and every one of them can
    half-succeed: the zip left off, an upload still running when Update
    release was pressed, a filename that arrived different from the one
    version.json names. Each of those produces the same symptom — the
    update is offered and will not install — and none of them says which.
    Finding out by hand takes two URLs and a checksum; this is those two
    URLs and that checksum.
    """
    import urllib.error
    import urllib.request

    feed = DEFAULT_FEED % repo
    print("feed    %s" % feed)

    def fetch(url):
        request = urllib.request.Request(
            url, headers={"User-Agent": "squint-verify"})
        return urllib.request.urlopen(request, timeout=30)

    try:
        with fetch(feed) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print("\nFAIL    no version.json on the latest release.")
            print("        Attach it, or the app cannot see the build at "
                  "all.")
        else:
            print("\nFAIL    the feed answered HTTP %s." % exc.code)
        return 1
    except Exception as exc:
        print("\nFAIL    could not reach the feed: %s" % exc)
        return 1

    try:
        release = json.loads(raw)
    except Exception:
        print("\nFAIL    version.json is not readable JSON.")
        return 1

    print("build   %s" % release.get("build"))
    print("url     %s" % release.get("url"))

    try:
        with fetch(release["url"]) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print("\nFAIL    the zip is not at that address.")
            print("        Either it was never attached, or GitHub has it "
                  "under a different name than version.json expects — open "
                  "the release page and compare the asset's filename with "
                  "the url above, character for character.")
            print("        Fixing either end works: re-upload the zip under "
                  "the right name, or edit the url in version.json to the "
                  "name that is really there.")
        else:
            print("\nFAIL    the download answered HTTP %s." % exc.code)
        return 1
    except Exception as exc:
        print("\nFAIL    could not download the zip: %s" % exc)
        return 1

    got = hashlib.sha256(body).hexdigest()
    print("size    %.0f KB" % (len(body) / 1024.0))
    if got != str(release.get("sha256", "")).lower():
        print("\nFAIL    the zip does not match the checksum version.json "
              "publishes.")
        print("        published %s" % release.get("sha256"))
        print("        actual    %s" % got)
        print("        The two files are from different builds. Upload both "
              "from the same dist folder.")
        return 1
    if expect_sha and got != expect_sha:
        print("\nFAIL    the published release is not the build in dist/.")
        print("        dist      %s" % expect_sha)
        print("        published %s" % got)
        return 1

    print("\nOK      the release is complete and installable.")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="ratanpranay/squint",
                        help="GitHub owner/name, for the download URL")
    parser.add_argument("--out", default=os.path.join(ROOT, "dist"))
    parser.add_argument("--verify", action="store_true",
                        help="check the published release instead of "
                             "building one")
    args = parser.parse_args()

    if args.verify:
        expect = None
        built = os.path.join(args.out, "Squint.zip")
        if os.path.isfile(built):
            with open(built, "rb") as fh:
                expect = hashlib.sha256(fh.read()).hexdigest()
        return verify(args.repo, expect)

    stamp = build_stamp()
    tag = tag_for(stamp)
    os.makedirs(args.out, exist_ok=True)
    # Always "Squint.zip", never the build in the filename.
    #
    # A release went out where the zip arrived on GitHub as
    # "Squint2026.08.31ay.zip" while version.json pointed at
    # "Squint-2026.08.31-ay.zip" — the hyphens lost somewhere between the
    # download and the upload. Byte-identical file, right checksum, 404 on
    # every attempt to install it, and nothing on screen said which of the
    # two names was wrong.
    #
    # The build number in the filename bought nothing: the tag already
    # carries it, the release page already shows it, and the file lands in
    # a folder named for the release. All it did was give the name four
    # more characters to get mangled. A constant name cannot drift from
    # what version.json says.
    zip_name = "Squint.zip"
    zip_path = os.path.join(args.out, zip_name)

    unlogged = changelog_missing(stamp)
    if unlogged:
        print("REFUSING TO BUILD — %s.\n" % unlogged)
        print("Add a section at the top of CHANGELOG.md:\n")
        print("    ## %s\n" % stamp)
        print("    ### Fixed")
        print("    - ...\n")
        print("    ### Added")
        print("    - ...\n")
        print("Use Fixed / Added / Changed / Removed, and say what someone "
              "updating would notice. VERSION.txt is for the long "
              "explanation; the changelog is the short one.")
        return 3

    files = collect()

    leaked = check_for_secrets(files)
    if leaked:
        print("REFUSING TO BUILD — this would publish a credential:\n")
        for line in leaked:
            print("   " + line)
        print("\nRemove it and run this again. Then change the key: once a "
              "key has been on disk in a file you were about to publish, "
              "treat it as public.")
        return 2

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, arcname in files:
            archive.write(path, os.path.join("Squint", arcname))

    digest = hashlib.sha256()
    with open(zip_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)

    from app.updater import build_serial
    payload = {
        "build": stamp,
        "serial": build_serial(stamp),
        "url": "https://github.com/%s/releases/download/%s/%s"
               % (args.repo, tag, zip_name),
        "sha256": digest.hexdigest(),
        # Straight from the changelog, kind by kind, so the panel in
        # Settings shows what a release fixed and what it added rather
        # than one undifferentiated wall. Falls back to VERSION.txt for a
        # build made before the changelog existed.
        "notes": notes_text(stamp) or "\n".join(
            "- " + line for line in release_notes()),
    }
    feed_path = os.path.join(args.out, "version.json")
    with open(feed_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    size = os.path.getsize(zip_path) / 1024.0
    # Printed as the three things that get typed into GitHub, in the order
    # the form asks for them. The tag and the title were being worked out
    # by hand from the version, and a tag typed a character differently is
    # a 404 for everyone.
    print("version %s" % stamp)
    print("tag     %s        <- Choose a tag, exactly this" % tag)
    print("title   Squint %s   <- Release title" % stamp)
    print("files   %d  (%.0f KB)" % (len(files), size))
    print("sha256  %s" % payload["sha256"])
    print()
    body_path = os.path.join(args.out, "RELEASE_NOTES.md")
    with open(body_path, "w", encoding="utf-8") as fh:
        fh.write(release_body(stamp))

    print("wrote   %s" % zip_path)
    print("        %s" % feed_path)
    print("        %s" % body_path)
    print()
    print("Next: make a GitHub release tagged exactly  %s" % tag)
    print("      and attach Squint.zip and version.json to it.")
    print("      Paste RELEASE_NOTES.md into the description — it is the")
    print("      changelog section for this version, already written.")
    print("      The tag has to match or the download URL will 404.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
