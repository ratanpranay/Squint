"""Offline translation, on this machine, with no account and no cost.

Every web service tried so far has the same three problems: it is rate-limited
per IP address (a shared office connection gets 429 all day), it needs a key
to be reliable, and it sends the text you are translating to someone else's
server. A local model has none of those, and it works on a plane.

The engine is Argos Translate — CTranslate2 models under the hood, MIT/CC0
licensed, so it can be bundled and redistributed freely. Each language pair
is a separate download of roughly 100 MB, kept in the app's own data folder
rather than scattered in the user's home directory.

Import never raises: if the package is missing, `available()` is False and
the caller falls back to the web services.
"""
import os
import threading

from . import config

# Argos reads this at import time, so it has to be set first.
#
# The models live in a "languages" folder beside the app rather than buried
# in Application Support: they are big, they are the thing people want to
# check on or delete, and a folder you can open in Finder beats a hidden
# library path.
_MODELS = os.path.join(config.app_dir(), "languages")
_LEGACY = os.path.join(config.data_dir(), "models")
os.environ.setdefault("ARGOS_TRANSLATE_PACKAGE_DIR", _MODELS)
try:
    os.makedirs(_MODELS, exist_ok=True)
    # Anything downloaded by an earlier version moves across, so a 100 MB
    # download is not repeated just because the folder changed.
    if os.path.isdir(_LEGACY):
        import shutil
        for entry in os.listdir(_LEGACY):
            source = os.path.join(_LEGACY, entry)
            destination = os.path.join(_MODELS, entry)
            if not os.path.exists(destination):
                shutil.move(source, destination)
        if not os.listdir(_LEGACY):
            os.rmdir(_LEGACY)
except Exception:
    pass

AVAILABLE = False
_import_error = None
try:
    import argostranslate.package as _package
    import argostranslate.translate as _translate
    AVAILABLE = True
except Exception as exc:      # pragma: no cover - depends on install
    _import_error = exc
    _package = _translate = None

_lock = threading.Lock()
_index_cache = None


def available():
    return AVAILABLE


def unavailable_reason():
    if AVAILABLE:
        return ""
    return "offline engine not installed (%s)" % (_import_error or "unknown")


def models_dir():
    return _MODELS


def installed_pairs():
    """[(from_code, to_code)] for every model already on this machine."""
    if not AVAILABLE:
        return []
    try:
        return sorted({(str(p.from_code), str(p.to_code))
                       for p in _package.get_installed_packages()})
    except Exception:
        return []


def language_size(code, other="en"):
    """Bytes on disk for both directions of a language, 0 if unknown.

    What a model costs is the question anybody asks before deciding
    whether to keep it, and it is the one number the panel could not
    answer: the package objects report where they live, not how big
    they are, so it is measured.
    """
    if not AVAILABLE:
        return 0
    code = (code or "").split("-")[0]
    other = (other or "en").split("-")[0]
    total = 0
    try:
        packages = _package.get_installed_packages()
    except Exception:
        return 0
    for package in packages:
        pair = (str(package.from_code), str(package.to_code))
        if pair not in ((code, other), (other, code)):
            continue
        path = getattr(package, "package_path", None)
        if not path:
            continue
        try:
            for root, _dirs, files in os.walk(str(path)):
                for name in files:
                    try:
                        total += os.path.getsize(os.path.join(root, name))
                    except OSError:
                        pass
        except Exception:
            continue
    return total


def has_pair(from_code, to_code):
    from_code = (from_code or "").split("-")[0]
    to_code = (to_code or "").split("-")[0]
    return (from_code, to_code) in installed_pairs()


def available_pairs(refresh=False):
    """What could be downloaded. Needs the network once, then cached."""
    global _index_cache
    if not AVAILABLE:
        return []
    with _lock:
        if _index_cache is not None and not refresh:
            return _index_cache
        try:
            _package.update_package_index()
            _index_cache = [
                {"from_code": str(p.from_code), "from_name": str(p.from_name),
                 "to_code": str(p.to_code), "to_name": str(p.to_name)}
                for p in _package.get_available_packages()]
        except Exception:
            _index_cache = []
        return _index_cache


def is_installed(code, other="en"):
    """True if this language can be used in either direction."""
    code = (code or "").split("-")[0]
    return has_pair(code, other) or has_pair(other, code)


def remove_language(code, other="en", progress=None):
    """Delete both directions of a language from this machine."""
    if not AVAILABLE:
        return False, unavailable_reason()
    code = (code or "").split("-")[0]
    removed, errors = 0, []
    try:
        packages = _package.get_installed_packages()
    except Exception as exc:
        return False, str(exc)[:160]
    for package in packages:
        pair = (str(package.from_code), str(package.to_code))
        if pair not in ((code, other), (other, code)):
            continue
        if progress:
            progress("removing %s\u2192%s\u2026" % pair)
        try:
            _package.uninstall(package)
            removed += 1
        except Exception as exc:
            errors.append(str(exc)[:80])
    _forget_installed()
    if errors:
        return False, "; ".join(errors)
    if not removed:
        return False, "not installed"
    return True, "removed"


def _forget_installed():
    """Drop the cached list of installed models.

    The translation layer memoises what is installed, so a model added or
    deleted stays invisible — or stays usable after deletion — until the
    app is restarted.
    """
    try:
        _translate.get_installed_languages.cache_clear()
    except Exception:
        pass


def install_language(code, other="en", progress=None, force=False):
    """Install BOTH directions for a language.

    A model is one-way: downloading "German" gets de→en, and translating
    English *into* German needs the separate en→de model. Choosing a
    language in the UI clearly means "let me work with German", so both
    directions are fetched — otherwise the app reports German as not
    installed straight after installing it, which is exactly what happened.
    """
    messages, ok_any = [], False
    for source, target in ((code, other), (other, code)):
        ok, message = install_pair(source, target, progress=progress,
                                   force=force)
        ok_any = ok_any or ok
        messages.append("%s→%s %s" % (source, target, message))
    return ok_any, "; ".join(messages)


def install_pair(from_code, to_code, progress=None, force=False):
    """Download and install one language pair. Returns (ok, message).

    `force` re-fetches a pair that is already here, which is what "Update"
    does: the models are revised from time to time and there is no version
    to compare against, so updating means fetching the current one again.
    """
    if not AVAILABLE:
        return False, unavailable_reason()
    from_code = (from_code or "").split("-")[0]
    to_code = (to_code or "").split("-")[0]
    if has_pair(from_code, to_code) and not force:
        return True, "already installed"
    try:
        if progress:
            progress("looking up %s → %s…" % (from_code, to_code))
        _package.update_package_index()
        matches = [p for p in _package.get_available_packages()
                   if str(p.from_code) == from_code
                   and str(p.to_code) == to_code]
        if not matches:
            return False, "no offline model exists for %s → %s" % (
                from_code, to_code)
        if progress:
            progress("downloading (about 100 MB)…")
        path = matches[0].download()
        if progress:
            progress("installing…")
        _package.install_from_path(path)
        _forget_installed()
        return True, "updated" if force else "installed"
    except Exception as exc:
        return False, str(exc)[:160]


def translate(text, from_code, to_code):
    """Translate one string. Raises if the pair is not installed."""
    if not AVAILABLE:
        raise RuntimeError(unavailable_reason())
    from_code = (from_code or "").split("-")[0]
    to_code = (to_code or "").split("-")[0]
    if from_code == to_code:
        raise RuntimeError("source and target are the same language")
    out = _translate.translate(text, from_code, to_code)
    if not out or not str(out).strip():
        raise RuntimeError("the local model returned nothing")
    return str(out)


def translate_many(texts, from_code, to_code, workers=4):
    """Translate several strings at once.

    CTranslate2 releases the GIL while it runs, so threads genuinely help
    here — unlike most Python work. Order is preserved because the overlay
    maps each result back to the box it came from.
    """
    if not texts:
        return []
    if len(texts) == 1:
        return [translate(texts[0], from_code, to_code)]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(workers, len(texts))) as pool:
        futures = [pool.submit(translate, t, from_code, to_code)
                   for t in texts]
        return [f.result() for f in futures]
