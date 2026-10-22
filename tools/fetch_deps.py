"""Fetch the Tesseract OCR engine and its language models.

Run by build.bat, and by fix_ocr.bat when something went wrong. Safe to
re-run: anything already in place is skipped.

The engine is vendored into `vendor/tesseract` rather than `build/`, which is
PyInstaller's own working directory — keeping our payload out of a folder
another tool owns.

Getting the engine is the fragile step, so it is tried several ways: an
existing installation, then winget, then the official installer silently,
then the same installer interactively so Windows can show its elevation
prompt. Whatever happens, the result is verified by actually running
`tesseract --version` rather than by assuming.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app.langs import DEFAULT_TESSDATA, tessdata_path  # noqa: E402

VENDOR_DIR = os.path.join(ROOT, "vendor")
TESS_DIR = os.path.join(VENDOR_DIR, "tesseract")
LEGACY_DIR = os.path.join(ROOT, "build", "tesseract")
TESSDATA_DIR = os.path.join(TESS_DIR, "tessdata")
RELEASES_API = "https://api.github.com/repos/UB-Mannheim/tesseract/releases"
TESSDATA_URLS = (
    "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/"
    "%s.traineddata",
    "https://github.com/tesseract-ocr/tessdata_fast/raw/main/%s.traineddata",
)
UA = {"User-Agent": "Squint-build"}

EXISTING_INSTALLS = [
    r"C:\Program Files\Tesseract-OCR",
    r"C:\Program Files (x86)\Tesseract-OCR",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs",
                 "Tesseract-OCR"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tesseract-OCR"),
    os.path.join(os.environ.get("ProgramW6432", ""), "Tesseract-OCR"),
]


def say(msg=""):
    print("[deps] %s" % msg, flush=True)


def exe_path(directory=None):
    return os.path.join(directory or TESS_DIR, "tesseract.exe")


def works(directory):
    """Proof, not assumption: the binary has to actually run."""
    path = exe_path(directory)
    if not os.path.isfile(path):
        return False
    try:
        out = subprocess.run([path, "--version"], capture_output=True,
                             timeout=60)
        return out.returncode == 0 and b"tesseract" in out.stdout.lower()
    except Exception:
        return False


def download(url, dest, timeout=300):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp, \
            open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)
    return dest


def copy_engine(src):
    """Copy an installed Tesseract tree into vendor/ (without its tessdata)."""
    os.makedirs(TESS_DIR, exist_ok=True)
    for entry in os.listdir(src):
        if entry.lower() == "tessdata":
            continue
        source = os.path.join(src, entry)
        target = os.path.join(TESS_DIR, entry)
        try:
            if os.path.isdir(source):
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                shutil.copy2(source, target)
        except Exception as exc:
            say("  could not copy %s (%s)" % (entry, exc))


# -- acquisition strategies -------------------------------------------
def from_vendor():
    if works(TESS_DIR):
        say("engine already vendored - skipping")
        return True
    if works(LEGACY_DIR):
        say("found an engine in build/ from an older build - moving it")
        copy_engine(LEGACY_DIR)
        return works(TESS_DIR)
    return False


def from_existing_install():
    for candidate in EXISTING_INSTALLS:
        if candidate and works(candidate):
            say("found an existing install at %s" % candidate)
            copy_engine(candidate)
            return works(TESS_DIR)
    return False


def from_winget():
    if not shutil.which("winget"):
        return False
    say("trying winget (Windows may ask for permission) ...")
    try:
        subprocess.run(
            ["winget", "install", "--id", "UB-Mannheim.TesseractOCR", "-e",
             "--silent", "--accept-package-agreements",
             "--accept-source-agreements"],
            timeout=1200)
    except Exception as exc:
        say("  winget failed: %s" % exc)
        return False
    return from_existing_install()


def find_setup_url():
    req = urllib.request.Request(RELEASES_API, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as resp:
        releases = json.load(resp)
    for release in releases:
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            if name.startswith("tesseract-ocr-w64-setup") and \
                    name.endswith(".exe"):
                return asset["browser_download_url"], name
    raise RuntimeError("no w64 setup asset in the UB-Mannheim releases")


def from_installer(interactive=False):
    say("downloading the Tesseract installer (~50 MB) ...")
    try:
        url, name = find_setup_url()
    except Exception as exc:
        say("  could not reach GitHub: %s" % exc)
        return False

    tmp = tempfile.mkdtemp(prefix="snaptess_")
    setup = os.path.join(tmp, name)
    try:
        download(url, setup)
    except Exception as exc:
        say("  download failed: %s" % exc)
        return False
    say("  downloaded %s" % name)

    # NSIS: /D must come last and must not be quoted, so the target path
    # cannot contain spaces.
    target = os.path.join(tempfile.gettempdir(), "squint_tesseract")
    shutil.rmtree(target, ignore_errors=True)
    args = [setup, "/S", "/D=" + target] if not interactive else [setup]
    if interactive:
        say("  the installer needs your confirmation - a window will open.")
        say("  accept the default location and click through it.")
    else:
        say("  installing quietly ...")
    try:
        subprocess.run(args, timeout=1800)
    except Exception as exc:
        say("  installer failed: %s" % exc)
        return False

    if not interactive and works(target):
        copy_engine(target)
        shutil.rmtree(tmp, ignore_errors=True)
        return works(TESS_DIR)
    # Interactive runs land wherever the user chose; look in the usual spots.
    shutil.rmtree(tmp, ignore_errors=True)
    return from_existing_install()


def install_tesseract(interactive_ok=True):
    for strategy in (from_vendor, from_existing_install, from_winget,
                     from_installer):
        try:
            if strategy():
                return True
        except Exception as exc:
            say("  %s failed: %s" % (strategy.__name__, exc))
    if interactive_ok:
        say("silent methods did not work - trying the installer window")
        try:
            if from_installer(interactive=True):
                return True
        except Exception as exc:
            say("  interactive install failed: %s" % exc)
    return False


# -- language models ---------------------------------------------------
def fetch_tessdata(packs=None):
    packs = packs or DEFAULT_TESSDATA
    os.makedirs(TESSDATA_DIR, exist_ok=True)
    missing = []
    for pack in packs:
        dest = os.path.join(TESSDATA_DIR, pack + ".traineddata")
        if os.path.isfile(dest) and os.path.getsize(dest) > 10000:
            continue
        say("downloading model: %s" % pack)
        path = tessdata_path(pack)
        last = None
        for template in TESSDATA_URLS:
            try:
                download(template % path, dest + ".part")
                os.replace(dest + ".part", dest)
                last = None
                break
            except Exception as exc:
                last = exc
                try:
                    os.remove(dest + ".part")
                except OSError:
                    pass
        if last is not None:
            say("  failed (%s)" % last)
            missing.append(pack)
    return missing


def verify():
    """Report what is actually present. Returns True when usable."""
    ok_engine = works(TESS_DIR)
    models = []
    if os.path.isdir(TESSDATA_DIR):
        models = [n[:-len(".traineddata")]
                  for n in sorted(os.listdir(TESSDATA_DIR))
                  if n.endswith(".traineddata")]
    say()
    say("engine : %s" % ("OK  " + exe_path() if ok_engine else "MISSING"))
    say("models : %s" % (", ".join(models) if models else "none"))
    essential = [m for m in ("osd", "eng", "Latin") if m in models]
    ok_models = len(essential) >= 2
    if not ok_models:
        say("         osd, eng and Latin are the ones that matter")
    return ok_engine and ok_models


def windows_ocr_ready():
    """True when Windows can already read text without Tesseract."""
    try:
        sys.path.insert(0, ROOT)
        from app import ocr_windows
        return bool(ocr_windows.AVAILABLE and
                    ocr_windows.available_languages())
    except Exception:
        return False


def main():
    if "--verify" in sys.argv:
        return 0 if verify() else 1

    # Do not fetch Tesseract when Windows can already read text itself.
    #
    # Two reasons, and the second is the one that bites. Windows.Media.Ocr
    # is better than Tesseract on screen text, so the download buys
    # nothing. And fetching an .exe and running it is indistinguishable
    # from a malware dropper as far as Defender is concerned — the same
    # pattern in setup.bat got the whole download blocked before the user
    # ever saw it.
    if sys.platform == "win32" and "--force-tesseract" not in sys.argv:
        if windows_ocr_ready():
            say("Windows OCR is available - skipping the Tesseract "
                "download entirely.")
            return 0

    os.makedirs(VENDOR_DIR, exist_ok=True)
    interactive_ok = "--no-prompt" not in sys.argv
    engine = install_tesseract(interactive_ok=interactive_ok)
    if not engine:
        say()
        say("Could not obtain the Tesseract engine automatically.")
        say("Install it yourself, then run fix_ocr.bat:")
        say("  https://github.com/UB-Mannheim/tesseract/wiki")
        say("Accept the default install location and it will be found.")
        say()
    missing = fetch_tessdata()
    if missing:
        say("models not downloaded: %s" % ", ".join(missing))
    ok = verify()
    say("done" if ok else "INCOMPLETE - see above")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
