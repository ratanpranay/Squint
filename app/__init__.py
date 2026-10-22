"""Squint — instant screen and document translation for Windows."""
import os as _os
import sys as _sys


def _point_tk_at_its_scripts():
    """On the Mac app after the Tk 8.6 swap (see mac_toolkit), tell Tcl and
    Tk where their script folders are. Tk 9 carries its scripts inside the
    library; 8.6 reads them from disk, and the interpreter the app runs is
    inside the app bundle, where Tcl would look for them by default.
    Here, before anything imports tkinter; only once the swap is in place.
    """
    if _sys.platform != "darwin":
        return
    root = _os.path.realpath(_sys.prefix)
    if "Application Support/Squint/Program/.venv" not in root:
        return
    swapped = _os.path.join(
        root, "lib", "python3.12", "lib-dynload",
        "_tkinter.cpython-312-darwin.so.tk9")
    tcl = _os.path.join(root, "lib", "tcl8.6")
    tk = _os.path.join(root, "lib", "tk8.6")
    tk9 = _os.path.join(root, "lib", "libtcl9tk9.0.dylib")
    uses_86 = _os.path.exists(swapped) or not _os.path.exists(tk9)
    if uses_86 and _os.path.isdir(tcl) and _os.path.isdir(tk):
        _os.environ.setdefault("TCL_LIBRARY", tcl)
        _os.environ.setdefault("TK_LIBRARY", tk)


try:
    _point_tk_at_its_scripts()
except Exception:
    pass

from .config import build_id  # noqa: E402

# One version, read from VERSION.txt like everything else.
#
# This was a literal "1.2.0" for twenty-one releases. Nothing depended on
# it except the first line of the log — which is exactly the sort of place
# a wrong number does damage, because a log is read when something is
# already broken and every fact in it is being trusted. A Mac that would
# not start was diagnosed against a log claiming to be version 1.2.0.
#
# `tools/make_app.py` had already learned this and written it down: the
# bundle's version "sat at 1.2.0 through eight releases", so it reads
# VERSION.txt now. The lesson was recorded in one file and left standing
# in another.
__version__ = build_id()
