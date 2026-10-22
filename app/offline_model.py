"""Hy-MT2: Tencent's open translation model, on this computer.

Free, private, no key, 33 languages, and it keeps working with no network —
the answer for when Gemini and Groq are out for the day, the office network
is down, or somebody has chosen "On this computer only".

Nothing of it is in the installer. The person who wants it switches it on in
Settings and chooses a size; the model and a small engine to run it download
in the background, resumably, and are checked before use:

  * the model — one GGUF file from Tencent's page on Hugging Face (Apache
    2.0). Standard is the 4-bit file, about 1.1 GB, close to full quality.
    Compact is Tencent's 2-bit file, about 600 MB. Tencent's notes say some
    of their smallest files need a llama.cpp kernel that is not released
    yet; if this one turns out to be such a file, the engine refuses to
    load it, Squint says so and offers Standard.

  * llama.cpp — the engine, a prebuilt release from its GitHub page for
    this system (Windows x64 CPU, macOS Apple silicon or Intel). It runs as
    `llama-server` on 127.0.0.1 with the model loaded, only while it is
    being used: started on the first offline translation, stopped after
    IDLE_SECONDS without one, so 1.5 GB of memory is not held all day.

Everything lives in data_dir()/offline, where settings and the other
downloads already are — outside the program folder, so updates never touch
it.
"""
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile

from . import config, platform_util

HF = "https://huggingface.co"
MODELS = {
    "standard": {
        "repo": "tencent/Hy-MT2-1.8B-GGUF",
        "file": "Hy-MT2-1.8B-Q4_K_M.gguf",
        "label": "Standard · about 1.1 GB",
        "note": "Recommended — close to full quality",
        "size": 1_130_000_000,
    },
}
ORDER = ("standard",)
# Offered in 1.48.16-18. The stock engine cannot load the 2-bit file, so it
# is gone: a saved choice moves to Standard and the file is deleted.
RETIRED_FILES = ("Hy-MT2-1.8B-2Bit.gguf",)

LLAMA_RELEASES_LIST = ("https://api.github.com/repos/ggml-org/llama.cpp/"
                       "releases?per_page=10")

IDLE_SECONDS = 600
START_TIMEOUT = 90
REQUEST_TIMEOUT = 60
# The server answers SLOTS requests at once (llama.cpp batches them), and
# CONTEXT is shared between them: 2048 tokens each, far more than a few
# lines of a snip need. One request at a time left the CPU waiting on
# memory; several together cost little more than one.
#
# How many side by side depends on the machine - see `slots()`. On a
# graphics chip a small model writes many answers together for little more
# than the cost of one, so more side by side is nearly free speed; on a
# processor it is not, and more only divides the same speed further.
# Each slot keeps 1536 tokens of working memory, three times what a
# sentence and its answer need.
SLOTS = 6
SLOT_CONTEXT = 1536


def _memory_gb():
    try:
        if platform_util.IS_MAC:
            out = subprocess.run(["sysctl", "-n", "hw.memsize"],
                                 capture_output=True, text=True, timeout=5)
            return int(out.stdout.strip()) / 1e9
        if platform_util.IS_WINDOWS:
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            status = Status()
            status.dwLength = ctypes.sizeof(Status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return status.ullTotalPhys / 1e9
    except Exception:
        pass
    return 8.0


def slots(gpu=None):
    """Answers written side by side, for this machine.

    Hold-to-see sends a whole page and the engine was the whole of the wait
    (the log: twelve seconds of translating finished in five with three at
    once). With a graphics chip: 8 on 16 GB or more, 6 on less. On the
    processor alone: 4 - more would only share out the same speed.

    It was 16 for a day. The log from a 16 GB Mac said no: a two-line
    sentence that took 0.3 s with three at once took 3.7-6.5 s with
    sixteen, and 21 sentences took 17 s. The graphics chip was not waiting
    between answers; it was full. Eight, and six on less memory.

    Not 30. Past about 16 a model this size stops getting faster on a
    laptop's graphics chip - the chip is busy, not waiting - and the
    working memory, which is set aside while the engine is loaded, keeps
    growing: 16 slots would be about 1.5 GB on top of the 1.1 GB model."""
    if gpu is None:
        gpu = _uses_gpu()
    if not gpu:
        return 4
    return 8 if _memory_gb() >= 15 else 6
def cache_ram():
    """Megabytes the engine may keep of earlier requests, to reuse them.

    Left to itself it keeps up to 8 GB and grows until the computer runs out
    of memory: on a test machine it was stopped by the system for it. The
    whole engine - the 1.1 GB model, its working memory and this - stays
    under 4 GB (model 1.1, working memory up to 0.8, this, and about 0.3
    for the sums): 1.5 GB kept on 16 GB or more, 1 GB on less. Keeping less made
    no difference to speed."""
    return 1536 if _memory_gb() >= 15 else 1024


# A snip is sent in small groups of lines rather than all at once: a group
# keeps the context a sentence broken across lines needs, a small model
# keeps its line count straight far more often over 6 lines than over 30,
# and the groups run side by side.
GROUP_LINES = 6
GROUP_CHARS = 400

# Tencent's own recommendation for the 1.8B model, except the sampling:
# theirs is temperature 0.7, which is for variety. A translation wants the
# same answer every time - the same sentence came back worded differently
# in a snip and in hold-to-see at 0.2 - so the most likely word is always
# taken (temperature 0, one candidate) and the seed is fixed.
SAMPLING = {"temperature": 0.0, "top_k": 1, "top_p": 1.0, "seed": 1,
            "repeat_penalty": 1.05}

_lock = threading.Lock()
_server = {"proc": None, "port": None, "model": None, "used": 0.0,
           "timer": None, "gpu": False}
_download = {"thread": None, "stop": False, "state": "idle",
             "done": 0, "total": 0, "error": "", "which": None}


# -- where things are ------------------------------------------------------

def folder():
    return os.path.join(config.data_dir(), "offline")


def model_path(which):
    return os.path.join(folder(), MODELS[which]["file"])


def engine_dir():
    return os.path.join(folder(), "llama")


def _server_name():
    return "llama-server.exe" if platform_util.IS_WINDOWS else "llama-server"


def engine_path():
    """The llama-server binary, wherever the release zip put it."""
    base = engine_dir()
    if not os.path.isdir(base):
        return None
    for root, _dirs, files in os.walk(base):
        if _server_name() in files:
            return os.path.join(root, _server_name())
    return None


def installed(which=None):
    """Which model is on disk and ready, or None."""
    names = [which] if which else list(ORDER[::-1])
    for name in names:
        path = model_path(name)
        if os.path.isfile(path) and os.path.getsize(path) > 50_000_000:
            return name
    return None


def ready():
    """Switched on, a model on disk, and the engine beside it."""
    if not config.CONFIG.get("offline_enabled", False):
        return False
    return bool(installed(chosen()) and engine_path())


def chosen():
    which = config.CONFIG.get("offline_model", "standard")
    return which if which in MODELS else "standard"


def retire_old():
    """Move a saved Compact choice to Standard and delete its file."""
    if config.CONFIG.get("offline_model", "standard") not in MODELS:
        config.CONFIG.set("offline_model", "standard")
        config.CONFIG.set("offline_tested", {})
    for name in RETIRED_FILES:
        for path in (os.path.join(folder(), name),
                     os.path.join(folder(), name) + ".part"):
            try:
                os.remove(path)
            except OSError:
                pass


# -- downloading -----------------------------------------------------------

def _get(url, headers=None, timeout=30):
    request = urllib.request.Request(url, headers=dict(
        {"User-Agent": "Squint"}, **(headers or {})))
    from .translator import ssl_context
    return urllib.request.urlopen(request, timeout=timeout,
                                  context=ssl_context())


def _expected_sha256(which):
    """The checksum Hugging Face publishes for the file, or None."""
    info = MODELS[which]
    url = "%s/api/models/%s/tree/main" % (HF, info["repo"])
    try:
        with _get(url) as reply:
            listing = json.loads(reply.read().decode("utf-8"))
        for entry in listing:
            if entry.get("path") == info["file"]:
                return ((entry.get("lfs") or {}).get("oid")
                        or (entry.get("lfs") or {}).get("sha256"))
    except Exception:
        return None
    return None


def _fetch_to(url, target, progress, expected_size=0):
    """Download `url` to `target`, resuming a `.part` left from before."""
    part = target + ".part"
    have = os.path.getsize(part) if os.path.exists(part) else 0
    headers = {"Range": "bytes=%d-" % have} if have else {}
    try:
        reply = _get(url, headers=headers, timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code == 416:          # already whole
            reply = None
        else:
            raise
    if reply is not None:
        with reply:
            if have and reply.status != 206:
                have = 0             # the server started again from zero
            total = have + int(reply.headers.get("Content-Length") or 0)
            total = total or expected_size
            with open(part, "ab" if have else "wb") as out:
                while True:
                    if _download["stop"]:
                        raise InterruptedError("paused")
                    chunk = reply.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
                    have += len(chunk)
                    progress(have, total)
    os.replace(part, target)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# Which llama.cpp build: on Windows the Vulkan one, which runs the model on
# the graphics chip — any make, built into the processor or not — and
# still runs on the processor when there is none. The plain CPU build it
# replaces left the graphics chip idle and a snip took ten seconds. On a
# Mac the standard build already has Metal.
def _flavor_wanted():
    return "vulkan" if platform_util.IS_WINDOWS else "standard"


def _engine_wanted(flavor=None):
    """What this system's build is called: the words its name contains,
    and the ones it must not (other accelerators, other chips)."""
    flavor = flavor or _flavor_wanted()
    if platform_util.IS_WINDOWS and flavor == "vulkan":
        return ("win", "x64", "vulkan"), ("cuda", "cpu", "hip", "sycl",
                                          "opencl", "arm64", "kompute")
    if platform_util.IS_WINDOWS:
        return ("win", "x64", "cpu"), ("cuda", "vulkan", "hip", "sycl",
                                       "opencl", "arm64", "kompute")
    if platform_util.IS_MAC:
        import platform
        chip = "arm64" if platform.machine() == "arm64" else "x64"
        return ("macos", chip), ("iOS", "xcframework")
    return ("ubuntu", "x64"), ("vulkan", "cuda", "rocm", "arm64", "s390x")


def _engine_asset(release, flavor=None):
    """The llama.cpp archive for this system, from one release listing."""
    need, avoid = _engine_wanted(flavor)
    for asset in release.get("assets") or []:
        name = asset.get("name", "")
        low = name.lower()
        if not (low.endswith(".zip") or low.endswith(".tar.gz")):
            continue
        if not low.startswith("llama-") or "cudart" in low:
            continue
        if all(word in low for word in need) and not any(
                word.lower() in low for word in avoid):
            return asset.get("browser_download_url"), name
    return None, None


# A known build to fall back on: llama.cpp publishes a release many times a
# day and the newest one's files arrive minutes after it does, so "latest"
# can be a release with nothing in it yet.
PINNED_TAG = "b7648"


RELEASES = "https://github.com/ggml-org/llama.cpp/releases"


def _asset_names(tag, flavor=None):
    """What this system's build is called in release `tag`, in the order
    to try. The Mac builds are .tar.gz and the Windows ones .zip; both are
    tried, because that has changed before and a guessed extension is a
    404 — which is what a Mac got from the pinned fallback."""
    flavor = flavor or _flavor_wanted()
    need, _avoid = _engine_wanted(flavor)
    if platform_util.IS_WINDOWS:
        base = "llama-%s-bin-win-%s-x64" % (
            tag, "vulkan" if flavor == "vulkan" else "cpu")
        return [base + ".zip", base + ".tar.gz"]
    if platform_util.IS_MAC:
        base = "llama-%s-bin-macos-%s" % (tag, need[1])
    else:
        base = "llama-%s-bin-ubuntu-x64" % tag
    return [base + ".tar.gz", base + ".zip"]


def _exists(url):
    try:
        request = urllib.request.Request(url, method="HEAD",
                                         headers={"User-Agent": "Squint"})
        from .translator import ssl_context
        with urllib.request.urlopen(request, timeout=20,
                                    context=ssl_context()) as reply:
            return reply.status < 400
    except Exception:
        return False


def _latest_tag():
    """The newest release's tag, from the page's own redirect rather than
    the API: the API allows sixty requests an hour per address, and an
    office behind one address runs out."""
    try:
        request = urllib.request.Request(RELEASES + "/latest", method="HEAD",
                                         headers={"User-Agent": "Squint"})
        from .translator import ssl_context
        with urllib.request.urlopen(request, timeout=20,
                                    context=ssl_context()) as reply:
            final = reply.geturl()
        match = re.search(r"/tag/(b\d+)", final or "")
        return match.group(1) if match else None
    except Exception:
        return None


def _asset_in(tag, flavor=None):
    for name in _asset_names(tag, flavor):
        url = "%s/download/%s/%s" % (RELEASES, tag, name)
        if _exists(url):
            return url, name
    return None, None


def _pinned_asset(flavor=None):
    names = _asset_names(PINNED_TAG, flavor)
    return ("%s/download/%s/%s" % (RELEASES, PINNED_TAG, names[0]),
            names[0])


def _find_engine(flavor=None):
    """The newest release that has this system's build: from the release
    list, else from the latest release's page, else a pinned release —
    each file checked to exist before it is downloaded."""
    seen = []
    try:
        with _get(LLAMA_RELEASES_LIST) as reply:
            releases = json.loads(reply.read().decode("utf-8"))
        for release in releases:
            if release.get("draft") or release.get("prerelease"):
                continue
            url, name = _engine_asset(release, flavor)
            if url:
                return url, name
            seen.extend(a.get("name", "") for a in
                        (release.get("assets") or [])[:3])
    except Exception as exc:
        seen.append("listing failed: %s" % str(exc)[:80])
    tag = _latest_tag()
    if tag:
        url, name = _asset_in(tag, flavor)
        if url:
            _note("offline: engine from %s (release list unavailable: %s)"
                  % (name, ", ".join(seen[:3]) or "no match"))
            return url, name
    url, name = _asset_in(PINNED_TAG, flavor)
    if url:
        _note("offline: engine from pinned %s" % name)
        return url, name
    raise RuntimeError(
        "could not find the offline engine for this computer on GitHub "
        "(%s). Check the internet connection and try again."
        % (", ".join(seen[:2]) or "no match"))


def _unpack(archive, target):
    if archive.lower().endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(target)
    else:
        import tarfile
        with tarfile.open(archive) as tf:
            try:
                tf.extractall(target, filter="tar")
            except TypeError:
                tf.extractall(target)


def engine_flavor():
    """Which build is on disk: "vulkan", "cpu" or "standard"."""
    try:
        with open(os.path.join(engine_dir(), "flavor.txt")) as fh:
            return fh.read().strip() or "cpu"
    except Exception:
        # Installed before this was written down: the CPU build on
        # Windows, the standard one elsewhere.
        return "cpu" if platform_util.IS_WINDOWS else "standard"


def _install_engine(progress, flavor=None, replace=False):
    if engine_path() and not replace:
        return
    flavor = flavor or _flavor_wanted()
    url, name = _find_engine(flavor)
    os.makedirs(folder(), exist_ok=True)
    archive = os.path.join(folder(), name)
    _fetch_to(url, archive, progress)
    target = engine_dir()
    fresh = target + "-new"
    shutil.rmtree(fresh, ignore_errors=True)
    _unpack(archive, fresh)
    os.remove(archive)
    if not _server_in(fresh):
        shutil.rmtree(fresh, ignore_errors=True)
        raise RuntimeError("the llama.cpp download had no llama-server")
    stop()
    shutil.rmtree(target, ignore_errors=True)
    os.replace(fresh, target)
    with open(os.path.join(target, "flavor.txt"), "w") as fh:
        fh.write(flavor)
    server = engine_path()
    if not platform_util.IS_WINDOWS:
        os.chmod(server, 0o755)
    else:
        # llama.cpp's Windows build is made with MSVC and wants its runtime
        # beside it. The Python Squint runs under has that same DLL; a PC
        # without the Visual C++ redistributable otherwise gets nothing.
        for dll in ("vcruntime140.dll", "vcruntime140_1.dll",
                    "msvcp140.dll"):
            for base in (os.path.dirname(sys.executable), sys.base_prefix):
                source = os.path.join(base, dll)
                if os.path.isfile(source):
                    try:
                        shutil.copy2(source, os.path.dirname(server))
                    except Exception:
                        pass
                    break


def _server_in(base):
    for _root, _dirs, files in os.walk(base):
        if _server_name() in files:
            return True
    return False


_upgrading = {"thread": None}


def upgrade_engine():
    """Swap an older CPU-only engine for the graphics-chip build, in the
    background, once. The model itself is not downloaded again."""
    if not platform_util.IS_WINDOWS or not engine_path():
        return False
    if engine_flavor() == _flavor_wanted():
        return False
    if config.CONFIG.get("offline_gpu_failed"):
        return False
    thread = _upgrading.get("thread")
    if thread is not None and thread.is_alive():
        return False

    def work():
        try:
            _install_engine(lambda d, t: None, replace=True)
            config.CONFIG.set("offline_tested", {})
            _note("offline: engine replaced with the %s build"
                  % _flavor_wanted())
        except Exception as exc:
            _note("offline: engine upgrade failed: %s" % str(exc)[:120])

    thread = threading.Thread(target=work, daemon=True)
    _upgrading["thread"] = thread
    thread.start()
    return True


def _note(message):
    try:
        from .main import log
        log(message)
    except Exception:
        pass


def start_download(which, on_progress=None, on_done=None):
    """Fetch the engine and the model in the background. Resumable: a
    download stopped half way carries on from where it stopped."""
    if which not in MODELS:
        raise ValueError(which)
    thread = _download.get("thread")
    if thread is not None and thread.is_alive():
        return False
    _download.update(stop=False, state="downloading", done=0,
                     total=MODELS[which]["size"], error="", which=which)

    def progress(done, total):
        _download["done"], _download["total"] = done, total or 1
        if on_progress:
            try:
                on_progress(done, total)
            except Exception:
                pass

    def work():
        try:
            try:
                _install_engine(lambda d, t: None)
            except InterruptedError:
                raise
            except Exception as exc:
                raise RuntimeError("the offline engine: %s" % exc)
            info = MODELS[which]
            target = model_path(which)
            if not installed(which):
                url = "%s/%s/resolve/main/%s" % (HF, info["repo"],
                                                 info["file"])
                _fetch_to(url, target, progress, info["size"])
                expected = _expected_sha256(which)
                got = _sha256(target)
                if expected and got != expected:
                    os.remove(target)
                    raise RuntimeError("the download was damaged; try again")
                _remember_sha(which, got)
            _download["state"] = "ready"
        except InterruptedError:
            _download["state"] = "paused"
        except Exception as exc:
            _download["state"] = "failed"
            _download["error"] = str(exc)[:200]
        if on_done:
            try:
                on_done(_download["state"], _download["error"])
            except Exception:
                pass

    _lower_priority()
    thread = threading.Thread(target=work, daemon=True)
    _download["thread"] = thread
    thread.start()
    return True


# -- updates ---------------------------------------------------------------
# Tencent can replace the file under the same name. Once a week the
# checksum Hugging Face publishes is compared with the one on disk; an
# update is only downloaded when the user presses Update, beside the old
# file, which keeps working until the new one has arrived whole and
# checked. Then one replaces the other, and the engine is refreshed too.
UPDATE_EVERY = 7 * 24 * 3600


def _signature(path):
    return "%d:%d" % (os.path.getsize(path), int(os.path.getmtime(path)))


def _remember_sha(which, sha):
    try:
        stored = dict(config.CONFIG.get("offline_sha", {}) or {})
        stored[which] = {"sig": _signature(model_path(which)), "sha": sha}
        config.CONFIG.set("offline_sha", stored)
    except Exception:
        pass


def local_sha(which=None):
    """The checksum of the model on disk; worked out once and kept."""
    which = which or chosen()
    path = model_path(which)
    entry = (config.CONFIG.get("offline_sha", {}) or {}).get(which) or {}
    if entry.get("sig") == _signature(path) and entry.get("sha"):
        return entry["sha"]
    sha = _sha256(path)
    _remember_sha(which, sha)
    return sha


def update_check_due(now=None):
    if not installed(chosen()):
        return False
    if not config.CONFIG.get("check_offline_updates", True):
        return False
    now = time.time() if now is None else now
    try:
        last = float(config.CONFIG.get("offline_update_checked", 0) or 0)
    except Exception:
        last = 0
    return not last or last > now or (now - last) >= UPDATE_EVERY


def update_available():
    return bool(installed(chosen())
                and config.CONFIG.get("offline_update_available"))


def check_for_update():
    """True when Hugging Face has a different file from the one here.
    Raises when it cannot be asked."""
    which = chosen()
    if not installed(which):
        config.CONFIG.set("offline_update_available", False)
        return False
    remote = _expected_sha256(which)
    config.CONFIG.set("offline_update_checked", time.time())
    if not remote:
        raise RuntimeError("could not reach Hugging Face")
    available = remote != local_sha(which)
    config.CONFIG.set("offline_update_available", bool(available))
    return available


def start_update(on_done=None):
    """Download the new model beside the old one, check it, swap them, and
    refresh the engine. The old model answers until the swap."""
    which = chosen()
    thread = _download.get("thread")
    if thread is not None and thread.is_alive():
        return False
    _download.update(stop=False, state="updating", done=0,
                     total=MODELS[which]["size"], error="", which=which)

    def progress(done, total):
        _download["done"], _download["total"] = done, total or 1

    def work():
        info = MODELS[which]
        fresh = model_path(which) + ".new"
        try:
            url = "%s/%s/resolve/main/%s" % (HF, info["repo"], info["file"])
            _fetch_to(url, fresh, progress, info["size"])
            expected = _expected_sha256(which)
            got = _sha256(fresh)
            if expected and got != expected:
                os.remove(fresh)
                raise RuntimeError("the download was damaged; try again")
            stop()
            os.replace(fresh, model_path(which))
            _remember_sha(which, got)
            try:
                _install_engine(lambda d, t: None, replace=True)
            except Exception as exc:
                _note("offline: engine refresh failed, kept the old one: %s"
                      % str(exc)[:120])
            config.CONFIG.set("offline_update_available", False)
            config.CONFIG.set("offline_tested", {})
            _download["state"] = "ready"
            _note("offline: model updated")
        except InterruptedError:
            _download["state"] = "paused"
        except Exception as exc:
            _download["state"] = "failed"
            _download["error"] = str(exc)[:200]
        if on_done:
            try:
                on_done(_download["state"], _download["error"])
            except Exception:
                pass

    _lower_priority()
    thread = threading.Thread(target=work, daemon=True)
    _download["thread"] = thread
    thread.start()
    return True


# Free disk space asked for before fetching on its own: the model, the
# engine, and room to spare so the computer is not filled up.
AUTO_FREE_BYTES = 3 * 1024 ** 3


def auto_setup(on_ready=None):
    """Set up offline translation without being asked, in the background.

    It used to wait for someone to find Settings › Offline translation and
    press Download; until then a new install had no offline translator,
    which is the one thing that makes it work without keys or quota. Now
    the first start fetches it (resumably, at low priority) and switches it
    on when it has arrived and translates a test line; online engines
    translate in the meantime.

    Left alone: a model already here (its switch is the user's), someone
    who switched it off or removed it, and a disk without room. Returns
    what it did, for the log."""
    try:
        which = chosen()
        if config.CONFIG.get("offline_declined"):
            return "declined"
        if config.CONFIG.get("offline_paused"):
            return "paused"
        if installed(which) and engine_path():
            if not config.CONFIG.get("offline_auto_done"):
                config.CONFIG.set("offline_auto_done", True)
            return "present"
        if config.CONFIG.get("offline_auto_done") and \
                not config.CONFIG.get("offline_enabled"):
            return "switched off"
        thread = _download.get("thread")
        if thread is not None and thread.is_alive():
            return "already downloading"
        try:
            import shutil
            os.makedirs(folder(), exist_ok=True)
            if shutil.disk_usage(folder()).free < AUTO_FREE_BYTES:
                return "not enough disk space"
        except Exception:
            pass
        config.CONFIG.set("offline_auto_done", True)
        config.CONFIG.set("offline_enabled", True)

        def done(state, error):
            if state != "ready":
                _note("offline    : download %s %s" % (state, error))
                return
            try:
                ok, message = self_test()
                _note("offline    : downloaded; %s" % message)
            except Exception as exc:
                _note("offline    : downloaded; test failed: %s" % exc)
            if on_ready:
                try:
                    on_ready()
                except Exception:
                    pass
        start_download(which, on_done=done)
        return "downloading"
    except Exception as exc:
        return "failed: %s" % exc


def pause_download():
    _download["stop"] = True


def download_state():
    return dict((k, v) for k, v in _download.items() if k != "thread")


def remove(which):
    stop()
    config.CONFIG.set("offline_update_available", False)
    for path in (model_path(which), model_path(which) + ".part",
                 model_path(which) + ".new.part"):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def _lower_priority():
    """Downloads are background work: nothing here should make the
    snipping feel slower while they run."""
    try:
        if platform_util.IS_WINDOWS:
            import ctypes
            ctypes.windll.kernel32.SetThreadPriority(
                ctypes.windll.kernel32.GetCurrentThread(), -1)
    except Exception:
        pass


# -- running ---------------------------------------------------------------

def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _threads():
    """Physical cores, not logical ones. llama.cpp on a CPU is limited by
    memory, and a thread on each hyper-thread of a core fights its twin:
    counting them made generation slower, not faster."""
    logical = os.cpu_count() or 4
    physical = _physical_cores()
    if not physical:
        physical = logical // 2 if logical >= 4 else logical
    return max(2, min(8, physical))


def _physical_cores():
    try:
        if platform_util.IS_WINDOWS:
            import ctypes
            from ctypes import wintypes
            size = wintypes.DWORD(0)
            kernel = ctypes.windll.kernel32
            kernel.GetLogicalProcessorInformation(None, ctypes.byref(size))
            buffer = ctypes.create_string_buffer(size.value)
            if not kernel.GetLogicalProcessorInformation(
                    buffer, ctypes.byref(size)):
                return None
            # SYSTEM_LOGICAL_PROCESSOR_INFORMATION: a pointer-sized mask,
            # then the relationship; RelationProcessorCore is 0.
            step = 32 if ctypes.sizeof(ctypes.c_void_p) == 8 else 24
            offset = ctypes.sizeof(ctypes.c_void_p)
            cores = 0
            for start in range(0, size.value - step + 1, step):
                kind = int.from_bytes(
                    buffer.raw[start + offset:start + offset + 4], "little")
                cores += kind == 0
            return cores or None
        if platform_util.IS_MAC:
            reply = subprocess.run(["sysctl", "-n", "hw.perflevel0.physicalcpu"],
                                   capture_output=True, text=True, timeout=3)
            if reply.returncode != 0 or not reply.stdout.strip():
                reply = subprocess.run(["sysctl", "-n", "hw.physicalcpu"],
                                       capture_output=True, text=True,
                                       timeout=3)
            return int(reply.stdout.strip()) or None
    except Exception:
        return None
    return None


def _alive():
    proc = _server["proc"]
    return proc is not None and proc.poll() is None


def _uses_gpu():
    return (engine_flavor() in ("vulkan", "standard")
            and not config.CONFIG.get("offline_gpu_failed"))


def on_graphics_chip():
    """Whether the engine runs (or will run) on the graphics chip."""
    try:
        if _alive():
            return bool(_server.get("gpu"))
        return _uses_gpu()
    except Exception:
        return True


def _start(which):
    server = engine_path()
    if not server:
        raise RuntimeError("the offline engine is not downloaded")
    gpu = _uses_gpu()
    try:
        _launch(server, which, gpu)
    except RuntimeError:
        if not gpu:
            raise
        # A graphics driver that will not run it: the processor will, and
        # is remembered as the way to go on this computer.
        _note("offline: the graphics chip would not run the model; "
              "using the processor")
        config.CONFIG.set("offline_gpu_failed", True)
        _launch(server, which, False)


def _launch(server, which, gpu):
    port = _free_port()
    command = [server, "-m", model_path(which), "--host", "127.0.0.1",
               "--port", str(port),
               "-c", str(SLOT_CONTEXT * slots(gpu)),
               "-np", str(slots(gpu)), "-t", str(_threads()),
               "-tb", str(max(2, min(16, os.cpu_count() or 4))),
               "--jinja", "--cache-ram", str(cache_ram())]
    command += ["-ngl", "99"] if gpu else ["-ngl", "0"]
    if not gpu and engine_flavor() == "vulkan":
        command += ["--device", "none"]
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "cwd": os.path.dirname(server)}
    if platform_util.IS_WINDOWS:
        kwargs["creationflags"] = 0x08000000 | 0x00004000  # no window, low
    proc = subprocess.Popen(command, **kwargs)
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                "the offline engine could not load this model — it may "
                "need a newer engine than is released.")
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/health" % port, timeout=2) as reply:
                if reply.status == 200:
                    break
        except Exception:
            time.sleep(0.4)
    else:
        proc.kill()
        raise RuntimeError("the offline engine took too long to start")
    _server.update(proc=proc, port=port, model=which, gpu=gpu,
                   slots=slots(gpu))


def _schedule_idle_stop():
    timer = _server.get("timer")
    if timer is not None:
        timer.cancel()
    timer = threading.Timer(IDLE_SECONDS, _stop_if_idle)
    timer.daemon = True
    _server["timer"] = timer
    timer.start()


def _stop_if_idle():
    if time.monotonic() - _server["used"] >= IDLE_SECONDS - 1:
        stop()


def stop():
    with _lock:
        proc = _server["proc"]
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        _server.update(proc=None, port=None, model=None)


def warm():
    """Start the model in the background if it will be wanted.

    Loading 1.1 GB takes seconds, and after ten idle minutes the server is
    stopped to give the memory back. Called when a snip begins, so the load
    happens while the area is being dragged, not after it."""
    if not ready():
        return False
    upgrade_engine()
    if _alive():
        return False

    def work():
        try:
            _ensure_running()
        except Exception:
            pass
    threading.Thread(target=work, daemon=True).start()
    return True


def _ensure_running():
    which = chosen()
    if not installed(which):
        raise RuntimeError("the offline model is not downloaded")
    with _lock:
        if not _alive() or _server["model"] != which:
            if _alive():
                _server["proc"].terminate()
            _start(which)
        _server["used"] = time.monotonic()
    _schedule_idle_stop()
    return _server["port"]


# The languages the model writes well: its makers' list, checked here by
# translating the same German sentence into each. Asked for others it does
# not refuse - it writes the wrong language (Malayalam and Punjabi came back
# in Gujarati, Slovak in Czech, Filipino in English), gets the meaning
# wrong (Swedish, Danish, Finnish, Hungarian) or repeats itself until it
# runs out (Norwegian). So for those, Automatic does not ask it.
WRITES = {"en", "zh", "zh-cn", "zh-tw", "fr", "pt", "es", "ja", "tr", "ru",
          "ar", "ko", "th", "it", "de", "vi", "ms", "id", "hi", "pl", "cs",
          "nl", "fa", "gu", "ur", "te", "mr", "he", "bn", "ta", "uk", "km",
          "my"}


def writes(target):
    """Whether the model translates into `target` well."""
    code = str(target or "").lower()
    return code in WRITES or code.split("-")[0] in WRITES


# Tencent's own prompt for the model: the whole instruction is the user
# turn, there is no system prompt, and a language is named in full.
PROMPT = ("Translate the following segment into %s, without additional "
          "explanation.\n\n%s")
PROMPT_LINES = ("Please accurately translate the following text into %s. "
                "Keep every line break: the translation must have exactly "
                "the same number of lines, in the same order.\n\n%s")


_last = {"error": ""}


def last_error():
    return _last["error"]


def self_test():
    """Load the chosen model and translate one short line. Returns
    (ok, message) and keeps the verdict, so Settings can say whether the
    model actually runs here — a finished download is not the same thing."""
    which = chosen()
    try:
        out = translate("Guten Morgen", "en")
        verdict = (True, "works on the %s — “Guten Morgen” → “%s”" % (
            "graphics chip" if _server.get("gpu") else "processor",
            out[:30]))
    except Exception as exc:
        verdict = (False, str(exc)[:200])
    tested = dict(config.CONFIG.get("offline_tested", {}) or {})
    tested[which] = list(verdict)
    config.CONFIG.set("offline_tested", tested)
    return verdict


def tested(which=None):
    """(ok, message) from the last self-test of this model, or None."""
    entry = (config.CONFIG.get("offline_tested", {}) or {}).get(
        which or chosen())
    return tuple(entry) if entry else None


def translate(text, target):
    """One request to the local model. Raises on anything unusable."""
    try:
        out = _translate(text, target)
        _last["error"] = ""
        return out
    except Exception as exc:
        _last["error"] = str(exc)[:200]
        raise


def _translate(text, target):
    from .langs import name_for
    language = name_for(target) or target
    template = PROMPT_LINES if "\n" in text.strip() else PROMPT
    out = _ask(template % (language, text), _budget(text))
    wanted = len(text.split("\n"))
    if wanted > 1 and len(out.split("\n")) != wanted:
        raise RuntimeError("returned %d lines for %d"
                           % (len(out.split("\n")), wanted))
    return out


# The model's own template for translating with context: the context first, then the
# instruction not to translate it, then the text. Its instruction is in
# Chinese, with the language named in Chinese.
PROMPT_CONTEXT = (u"%s\n参考上面的信息，把下面的文本翻译成%s，注意不需要翻译上文，"
                  u"也不要额外解释：\n%s")
CHINESE_NAMES = {
    "en": u"英语", "de": u"德语", "fr": u"法语", "es": u"西班牙语",
    "it": u"意大利语", "pt": u"葡萄牙语", "ru": u"俄语", "ja": u"日语",
    "ko": u"韩语", "zh": u"中文", "zh-TW": u"繁体中文", "nl": u"荷兰语",
    "pl": u"波兰语", "tr": u"土耳其语", "ar": u"阿拉伯语", "th": u"泰语",
    "vi": u"越南语", "uk": u"乌克兰语", "hi": u"印地语", "id": u"印尼语",
}
PROMPT_LIST = ("Translate each numbered item below into %s. The items are "
               "separate labels from one page: keep each on its own numbered "
               "line, in the same order, without additional explanation."
               "\n\n%s")


def translate_with_context(text, target, context):
    """A short item, with the text around it on the page to settle what
    it means. Falls back to the plain request when the answer looks like
    it took the context in too."""
    name = CHINESE_NAMES.get(target) or CHINESE_NAMES.get(
        str(target).split("-")[0])
    if not context or not name:
        return translate(text, target)
    try:
        out = _ask(PROMPT_CONTEXT % (context, name, text), _budget(text))
    except Exception:
        return translate(text, target)
    borrowed = any(len(piece) >= 6 and piece in out and piece not in text
                   for piece in context.split(" / "))
    if context == LABEL_CONTEXT and any(
            word in out and word not in text
            for word in (u"标签", u"按钮", u"菜单", u"单元格")):
        borrowed = True
    if borrowed or "\n" in out or len(out) > 3 * len(text) + 30:
        return translate(text, target)
    return out


# What a short item on its own is, said the same way every time. A word
# alone was translated as a word in a dictionary - "Accueil" as "Welcome",
# "Home" as "Zuhause", "Verbergen" as "Whisper", "Buscar" as "Search for" -
# where on a page it is a button, a menu item or a heading ("Home",
# "Startseite", "Hide", "Search"). Told that, measured on 27 labels from
# seven languages into the other six: more of them came back as the label
# they are, none as a wrong word that had been right. Always the same
# sentence, not the items around it, so a label reads the same in a snip
# and in hold-to-see. In the model's own form for context (PROMPT_CONTEXT);
# said inside the request instead, the model translated the explanation.
LABEL_CONTEXT = (u"（以下是网页、应用或文档中的一个简短标签：按钮、菜单项、"
                 u"标题或表格单元格。）")


def translate_label(text, target):
    """A short item - a button, menu item, heading or cell - translated
    as one (LABEL_CONTEXT)."""
    return translate_with_context(text, target, LABEL_CONTEXT)


def translate_list(items, target):
    """Several short labels in one request, one answer each - or None
    when the answer does not come back as exactly one numbered line per
    item (then each is asked on its own)."""
    from .langs import name_for
    language = name_for(target) or target
    numbered = "\n".join("%d. %s" % (n + 1, " ".join(item.split()))
                          for n, item in enumerate(items))
    try:
        out = _ask(PROMPT_LIST % (language, numbered),
                   _budget(numbered) + 8 * len(items))
    except Exception:
        return None
    found = {}
    for row in out.split("\n"):
        match = re.match(r"\s*(\d+)\s*[.)、:：]\s*(.*\S)\s*$", row)
        if match:
            found.setdefault(int(match.group(1)), match.group(2))
    if sorted(found) != list(range(1, len(items) + 1)):
        return None
    return [found[n + 1] for n in range(len(items))]


def _ask(content, budget):
    """One request to the local model with this user turn; the answer."""
    if not ready():
        raise RuntimeError("offline translation is not set up")
    port = _ensure_running()
    body = dict(SAMPLING, messages=[{"role": "user", "content": content}],
                max_tokens=budget)
    request = urllib.request.Request(
        "http://127.0.0.1:%d/v1/chat/completions" % port,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as reply:
        payload = json.loads(reply.read().decode("utf-8"))
    _server["used"] = time.monotonic()
    out = ((payload.get("choices") or [{}])[0].get("message") or {}).get(
        "content") or ""
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip()
    if not out:
        raise RuntimeError("the offline model gave no answer")
    return out


def _budget(text):
    """Enough tokens for any honest translation of `text`, and no more.

    A small model occasionally repeats itself until it is stopped; with
    room for 2048 tokens that was a snip taking most of a minute on a
    laptop. Chinese runs to about two tokens of English a character."""
    return max(48, min(1024, 32 + len(text) * 2))


def _groups(indexes, lines):
    groups, current, size = [], [], 0
    for index in indexes:
        length = len(lines[index])
        if current and (len(current) >= GROUP_LINES
                        or size + length > GROUP_CHARS):
            groups.append(current)
            current, size = [], 0
        current.append(index)
        size += length
    if current:
        groups.append(current)
    return groups


UNIT_CHARS = 700


def _units(indexes, lines):
    """Runs of lines that make one sentence (or a few), in page order.

    A snip hands over what was on screen line by line, and a sentence
    wrapped across three lines arrived as three separate things to
    translate. Hy-MT2 then translated "also in" and "a perfect condition"
    apart, and wrote "a completely bad state". Joined back into the
    sentence it was, it is translated whole and shared out again.

    A run ends at a line that finishes a sentence, at a gap in the page,
    and at a line much shorter than those around it — a heading, or the
    last line of a paragraph that did not end in a full stop.
    """
    lengths = sorted(len(lines[i].strip()) for i in indexes)
    typical = lengths[len(lengths) // 2] if lengths else 0
    units, current, size = [], [], 0
    for i in indexes:
        if current and i != current[-1] + 1:
            units.append(current)
            current, size = [], 0
        current.append(i)
        text = lines[i].strip()
        size += len(text)
        short = typical and len(text) < typical * 0.6
        # A run is a paragraph: wrapped lines carry on into the next one
        # even past a full stop (the paragraph is cut into sentences
        # later, see _pieces), and end at a short line, a gap or a line
        # with a new sentence starting inside it.
        if _SENTENCE_SPLIT.search(text) or short or size > UNIT_CHARS:
            units.append(current)
            current, size = [], 0
    if current:
        units.append(current)
    return units


def _share_out(text, sources):
    """One translation spread back over the lines it came from, in
    proportion to how long each of them was, breaking between words."""
    text = " ".join(str(text or "").split())
    if len(sources) == 1:
        return [text]
    total = sum(max(1, len(s)) for s in sources)
    words = text.split(" ")
    if len(words) < len(sources):
        # A language written without spaces: share out the characters.
        words, joiner = list(text), ""
    else:
        joiner = " "
    parts, start, seen = [], 0, 0
    for source in sources[:-1]:
        seen += max(1, len(source))
        cut = int(round(len(words) * seen / float(total)))
        cut = max(start, min(cut, len(words)))
        parts.append(joiner.join(words[start:cut]).strip())
        start = cut
    parts.append(joiner.join(words[start:]).strip())
    return parts


# A short label: few words, or few characters in a language written
# without spaces. These go several to a request (translate_list), in the
# order they are on the page, which also gives each the others as context.
SHORT_WORDS = 3
SHORT_CHARS = 24
SHORT_CJK = 8
# Labels are asked one at a time, each with the items beside it as
# context. They went eight to a request, and where the eight began
# depended on how much of the page was snipped: the same label on the same
# page came back as "Building" in one snip and "East" in hold-to-see,
# because it was in a different eight. One label and its neighbours is
# the same question however the page is framed.
LIST_ITEMS = 1


def _is_short(text):
    text = text.strip()
    cjk = sum(1 for c in text if 0x3040 <= ord(c) <= 0x9FFF
              or 0xAC00 <= ord(c) <= 0xD7AF)
    if cjk:
        return len(text) <= SHORT_CJK
    return len(text.split()) <= SHORT_WORDS and len(text) <= SHORT_CHARS


# A long paragraph is translated a few sentences at a time, the pieces side
# by side, and put back together. As one request it was the whole wait: the
# engine writes one word after another, so a paragraph of 250 words took as
# long as all of them in a row while the other slots sat idle - 8 to 11
# seconds on a page of three paragraphs. Split at sentence ends only, so
# each piece is still whole sentences, and always the same way, so the same
# paragraph gets the same translation in a snip and in hold-to-see.
PIECE_CHARS = 160          # a piece is about this long, never split below
PIECE_CJK = 90             # the same for Chinese and Japanese

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])[\"'”»)\]]*\s+(?=[\"'„“«(\[]?[A-ZÀ-ÞĀ-Ž0-9])"
                           # "verkaufen....Das Rad": dots typed straight
                           # into the next sentence, no space.
                           r"|(?<=\.\.)(?=[A-ZÀ-ÞĀ-Ž][a-zà-ÿā-ž])"
                           r"|(?<=…)(?=[A-ZÀ-ÞĀ-Ž][a-zà-ÿā-ž])"
                           u"|(?<=[。！？])")
_NOT_AN_END = re.compile(
    r"(?:\b(?:[A-Za-zÀ-ÿ]|\d+|z|B|ca|bzw|usw|etc|Dr|Prof|Nr|St|Jr|Sr|Mr|"
    r"Mrs|Ms|vs|Abs|Art|Bd|Hrsg|vgl|ggf|inkl|zzgl|Mio|Mrd|Str|No|Vol|"
    r"p|pp|S|u|a|o|e|i|d|h|v|Chr|geb|gest)\.)$")


_CLAUSE = re.compile(u"(?<=[;；])\\s+")


def _sentences(text):
    """`text` cut at the ends of its sentences, each piece with its own end
    punctuation. A full stop after a number ("am 30. September"), an
    initial or a common abbreviation is not an end."""
    pieces, start = [], 0
    for match in _SENTENCE_SPLIT.finditer(text):
        end = match.start()
        head = text[start:end].rstrip()
        if not head:
            continue
        if _NOT_AN_END.search(head.split()[-1] if head.split() else ""):
            continue
        pieces.append(text[start:match.end()].strip())
        start = match.end()
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    return [p for p in pieces if p]


def _pieces(text):
    """A long paragraph as runs of whole sentences of about PIECE_CHARS,
    or [text] when it is short or is one sentence."""
    text = text.strip()
    cjk = sum(1 for c in text if 0x3040 <= ord(c) <= 0x9FFF)
    limit = PIECE_CJK if cjk > len(text) * 0.3 else PIECE_CHARS
    if len(text) <= limit * 1.3:
        return [text]
    sentences = []
    for sentence in _sentences(text):
        # One sentence longer than a piece is cut where it has parts of
        # its own - after a semicolon - so that the longest wait is still a
        # short one. Not at commas, colons or dashes: those join parts that
        # need each other (a pair of dashes holds a clause inside the
        # sentence, and cut there the verb lost its subject).
        if len(sentence) > limit * 1.3:
            parts = [p for p in _CLAUSE.split(sentence) if p.strip()]
            sentences.extend(parts if len(parts) > 1 else [sentence])
        else:
            sentences.append(sentence)
    if len(sentences) < 2:
        return [text]
    pieces, current = [], ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > limit:
            pieces.append(current)
            current = sentence
        else:
            current = (current + (" " if current and not cjk else "")
                       + sentence) if current else sentence
    if current:
        # A short last sentence goes with the one before it.
        if pieces and len(current) < limit * 0.3:
            pieces[-1] = pieces[-1] + ("" if cjk else " ") + current
        else:
            pieces.append(current)
    return pieces


def _join(parts, target):
    closed = str(target or "").lower()[:2] in ("zh", "ja")
    return ("" if closed else " ").join(p.strip() for p in parts if p.strip())


def translate_lines(lines, target, left_behind=None, cancel=None,
                    workers=None, whole=False, progress=None, context=None):
    """A snip's lines, a sentence at a time, side by side; one line back
    for every line in.

    Lines are joined into the sentences they were wrapped from (`_units`),
    each sentence is translated whole, several at once, and the answer is
    shared back over its lines (`_share_out`).

    With `whole`, each item is a paragraph or a cell of its own: short
    labels next to each other go several to a request, and a short one on
    its own goes with `context[text]` (the items around it). `progress(i,
    text)` is told each item as soon as it is done. The work is handed
    out longest first, so the longest wait starts at once. Raises only
    when nothing at all could be translated."""
    from concurrent.futures import ThreadPoolExecutor
    started = time.monotonic()
    out = ["" for _ in lines]
    wanted = [i for i, line in enumerate(lines) if line.strip()]
    if not wanted:
        return out
    _ensure_running()
    loaded = time.monotonic()
    answered, errors = set(), []
    context = context or {}

    def tell(i):
        if progress is not None:
            try:
                progress(i, out[i])
            except Exception:
                pass
    # `whole`: each item is already a paragraph or a cell, grouped from the
    # page - never joined with the next. Joined, the labels of a car portal
    # (a model name, "报价 图库 论坛" under it, the next model) went to the
    # engine as one "sentence" and came back spread over the wrong boxes:
    # "Quotation Database Forum" split as "Quot ation", model codes lost.
    pieces = {}                       # index -> its pieces' answers
    pieces_lock = threading.Lock()
    if whole:
        units, run = [], []
        for i in wanted:
            if _is_short(lines[i]):
                run.append(i)
                if len(run) >= LIST_ITEMS:
                    units.append(("list", run))
                    run = []
                continue
            if run:
                units.append(("list", run))
                run = []
            parts = _pieces(lines[i])
            if len(parts) > 1:
                pieces[i] = [None] * len(parts)
                for k, part in enumerate(parts):
                    units.append(("piece", [i, k, part]))
            else:
                units.append(("one", [i]))
        if run:
            units.append(("list", run))
    else:
        units = [("join", u) for u in _units(wanted, lines)]

    def single(i):
        text = lines[i].strip()
        near = context.get(text) if _is_short(text) else None
        if near:
            return translate_with_context(text, target, near)
        if _is_short(text):
            answer = translate_label(text, target)
            if " ".join(str(answer).split()).lower() == \
                    " ".join(text.split()).lower() and \
                    sum(1 for c in text if c.isalpha()) >= 2 and \
                    not text.strip()[:1].islower():
                # Handed back as it was: asked as a label, "Motorrad" and
                # "Auto" came back unchanged where on their own they are
                # "Motorcycle" and "Car". Asked plainly once more - not a
                # lone letter, a piece of a word the reader cut off, nor a
                # word in small letters, the end of a phrase cut in two
                # ("comune" became "common"): asked plainly those come
                # back as guesses.
                plain = translate(text, target)
                if plain and plain.strip():
                    return plain
            return answer
        return translate(text, target)

    def unit(item):
        kind, indexes = item
        if cancel is not None and cancel.is_set():
            return
        if kind == "piece":
            i, k, part = indexes
            try:
                answer = translate(part, target)
            except Exception as exc:
                errors.append(exc)
                answer = None
            with pieces_lock:
                got = pieces[i]
                got[k] = answer if answer is not None else False
                finished = all(g is not None for g in got)
            if finished:
                if all(g is not False for g in got):
                    out[i] = _join(got, target)
                    answered.add(i)
                    tell(i)
            return
        try:
            if kind == "list" and len(indexes) > 1:
                got = translate_list([lines[i] for i in indexes], target)
                if got is not None:
                    for i, text in zip(indexes, got):
                        out[i] = text
                        answered.add(i)
                        tell(i)
                    return
            if kind in ("list", "one"):
                for i in indexes:
                    if cancel is not None and cancel.is_set():
                        return
                    try:
                        out[i] = single(i)
                        answered.add(i)
                        tell(i)
                    except Exception as exc:
                        errors.append(exc)
                return
            sources = [lines[i].strip() for i in indexes]
            answer = translate(" ".join(sources), target)
        except Exception as exc:
            errors.append(exc)
            return
        for i, part in zip(indexes, _share_out(answer, sources)):
            out[i] = part
            answered.add(i)
            tell(i)

    # `workers`: fewer for work done in the background beside an online
    # engine. A request already sent cannot be taken back, so with every
    # slot in use at once, cancelling when the online answer came stopped
    # nothing - the graphics chip went on with a whole page nobody would
    # see, and the next translation queued behind it.
    #
    # No second try for answers still in the original language: the model
    # answers the same text the same way every time now (SAMPLING), so
    # asking again only took the time twice.
    # Longest first. The model writes one word after another, so a piece
    # of a long paragraph is the longest wait on the page; started behind
    # a row of short labels, it began only when a slot came free and the
    # page waited for it at the end. Started first, it runs while the
    # short ones go through the other slots.
    def length(item):
        kind, indexes = item
        if kind == "piece":
            return len(indexes[2])
        return sum(len(lines[i]) for i in indexes)
    timings = []

    def timed(item):
        began = time.monotonic()
        try:
            unit(item)
        finally:
            timings.append((time.monotonic() - began, item[0],
                            length(item)))
    order = sorted(units, key=length, reverse=True)
    with ThreadPoolExecutor(max_workers=workers or _server.get("slots")
                            or SLOTS) as pool:
        list(pool.map(timed, order))
    if not answered:
        raise RuntimeError(str(errors[-1]) if errors
                           else "the offline model gave no answer")
    _timing(len(wanted), len(units), loaded - started,
            time.monotonic() - loaded, timings)
    return out


# The last translate_lines: how long the model took to start, and how long
# to translate once it had. Speed is learned from the second only - the
# first is once per start of the app, not a property of the page.
last_run = {"load": 0.0, "work": 0.0}


def _timing(lines, singles, load, work, timings=()):
    last_run.update(load=load, work=work)
    try:
        from .main import log
        slowest = ""
        if timings:
            took, kind, size = max(timings)
            slowest = ", slowest %s %.1fs (%d chars)" % (
                {"piece": "piece of a paragraph", "list": "label",
                 "one": "paragraph", "join": "sentence"}.get(kind, kind),
                took, size)
        log("hymt: %d lines in %d sentences, load %.1fs, translate %.1fs, "
            "%s, %s build, %d threads, %d side by side%s"
            % (lines, singles, load, work,
               "graphics chip" if _server.get("gpu") else "processor",
               engine_flavor(), _threads(), _server.get("slots") or SLOTS,
               slowest))
    except Exception:
        pass


import atexit
atexit.register(stop)
