"""Build Squint-Setup-<version>.exe: the app, its own Python, one file.

    python3.12 tools/make_installer.py          # into dist-installer/

Needs `makensis` (NSIS 3) and `uv` on the PATH, and Python 3.12 to run it —
3.12 because the files it compiles are for the 3.12 inside the installer,
and compiled Python is specific to the minor version.

What goes in, and why each piece is the way it is:

**Python itself.** The official Windows embeddable build of CPython 3.12,
with the standard library already compiled into a zip. It is not
installed on the machine in any sense Windows knows about — no registry,
no PATH, no "Python" in Apps — it is a folder the app runs from, so it
cannot collide with a Python the user already has or will install later.
The embeddable build leaves out Tk, which the app's whole interface is
drawn with, so Tk and tkinter are added from a second package. Both are
fetched from PyPI by exact checksum, and every binary in them carries its
publisher's signature (checked when this script is run with
--check-signatures and osslsigncode is available).

**The packages.** Installed for Windows, from Windows wheels, by `uv` —
which, unlike pip, evaluates each package's platform conditions for the
machine the packages are *for*, not the one building them. The one pure
Python package published only as source (the language guesser) is built
here; anything with compiled code must arrive as a Windows wheel, and the
build stops if a Linux or macOS binary gets in.

**Compiled in advance.** Every .py is compiled here, with hash-checked
.pyc files: Python checks the source still matches by hashing it rather
than by comparing timestamps, which do not survive being packed and
unpacked. A new machine therefore never compiles anything on first run —
which was a large part of the first launch being slow — and an update that
replaces a .py still gets it recompiled, because the hash no longer
matches.

**Layout.** The app's folder is laid out the way setup.bat lays it out,
with Python in `.venv`, so the updater, the scripts in the folder and the
log all work unchanged. The difference is that `.venv` is Python itself
rather than a virtual environment pointing elsewhere; `python312._pth`
tells it where its packages and the app are.
"""
import argparse
import compileall
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.make_release import (INCLUDE_DIRS, INCLUDE_FILES, SKIP,  # noqa: E402
                                build_stamp, version_of)

BUILD = os.path.join(ROOT, "build", "installer")
OUT_DIR = os.path.join(ROOT, "dist-installer")

# The embeddable CPython 3.12.9 (python.org's own build, signed by the
# Python Software Foundation) and Tcl/Tk 8.6 with tkinter for it. Pinned by
# checksum: a different file under the same name is a build failure, not a
# different installer.
RUNTIME = (
    ("python-embed", "3.12.0",
     "https://files.pythonhosted.org/packages/59/87/"
     "c9587bdcabe59533841345719562e4428b4e50cdaa113bbef4e19118150c/"
     "python_embed-3.12.0.tar.gz",
     "4715740bd3d1a2b1efc5c28b2e9b3c68bcde29c610593e73379d14897a3dc87d"),
    ("tkinter-embed", "3.12.0",
     "https://files.pythonhosted.org/packages/3b/21/"
     "d2b18c7be4dc27ba2ddf92c0af1e37ced502a8754c04cf2eabf02c7a5d67/"
     "tkinter_embed-3.12.0.tar.gz",
     "907680e9f197ae06f22b82494fc3b08245b3580d2cbf26acb2b81337d759351c"),
)

# Parts of the Tcl/Tk package that are build leftovers — import
# libraries, pkg-config and CMake files, and extensions nothing loads.
TCL_JUNK = (".lib", ".def", ".exp", ".sh")
TCL_JUNK_DIRS = ("cmake", "nmake", "pkgconfig", "sqlite3.44.2", "itcl4.2.4")

# Mac-only files have no business on a Windows machine.
NOT_ON_WINDOWS = (".command",)

PTH = """python312.zip
.
Lib\\site-packages
..
import site
"""


def say(message):
    print("[installer] %s" % message, flush=True)


def fetch(url, sha256, cache):
    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, url.rsplit("/", 1)[1])
    if not os.path.isfile(path):
        say("downloading %s" % os.path.basename(path))
        with urllib.request.urlopen(url, timeout=300) as response, \
                open(path + ".part", "wb") as out:
            shutil.copyfileobj(response, out)
        os.replace(path + ".part", path)
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if digest != sha256:
        raise SystemExit("checksum mismatch for %s: %s" % (path, digest))
    return path


def unpack_runtime(archive, dest):
    """The files for cp312 out of one of the two runtime packages."""
    with tarfile.open(archive) as tar:
        member = next(m for m in tar.getmembers()
                      if m.name.endswith("/data.zip"))
        data = tar.extractfile(member).read()
    tmp = os.path.join(BUILD, "data.zip")
    with open(tmp, "wb") as fh:
        fh.write(data)
    with zipfile.ZipFile(tmp) as zf:
        for name in zf.namelist():
            if not name.startswith("cp312/") or name.endswith("/"):
                continue
            target = os.path.join(dest, *name[len("cp312/"):].split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(name) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    os.remove(tmp)


def trim_tcl(tcl):
    for name in os.listdir(tcl):
        path = os.path.join(tcl, name)
        if os.path.isdir(path) and name in TCL_JUNK_DIRS:
            shutil.rmtree(path)
        elif os.path.isfile(path) and name.endswith(TCL_JUNK):
            os.remove(path)


def windows_requirements():
    """requirements.txt as it reads on Windows, plus pip for the updater."""
    wanted = []
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            spec, _, marker = line.partition(";")
            marker = marker.replace(" ", "")
            if marker and 'sys_platform=="win32"' not in marker:
                continue
            wanted.append(spec.strip())
    wanted.append("pip")
    return wanted


def install_packages(site):
    listing = os.path.join(BUILD, "requirements-windows.txt")
    with open(listing, "w", encoding="utf-8") as fh:
        fh.write("\n".join(windows_requirements()) + "\n")
    subprocess.run(["uv", "pip", "install", "--quiet", "--target", site,
                    "--python-platform", "x86_64-pc-windows-msvc",
                    "--python-version", "3.12", "-r", listing], check=True)
    # Only Windows binaries.
    wrong = [os.path.join(d, f) for d, _, files in os.walk(site)
             for f in files if f.endswith((".so", ".dylib"))
             and "tkdnd" not in d]
    if wrong:
        raise SystemExit("non-Windows binaries in the package set: %s"
                         % wrong[:5])
    # Command-line wrappers, written for the machine that built this.
    shutil.rmtree(os.path.join(site, "bin"), ignore_errors=True)
    # tkinterdnd2 ships its extension for every platform; keep Windows x64.
    tkdnd = os.path.join(site, "tkinterdnd2", "tkdnd")
    if os.path.isdir(tkdnd):
        for name in os.listdir(tkdnd):
            if name != "win-x64":
                shutil.rmtree(os.path.join(tkdnd, name))


def copy_app(dest):
    """The same files a release zip carries, less the Mac ones."""
    def keep(name):
        return name not in SKIP and not name.endswith(NOT_ON_WINDOWS)

    for folder in INCLUDE_DIRS:
        src = os.path.join(ROOT, folder)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dest, folder),
                            ignore=lambda d, names: [n for n in names
                                                     if not keep(n)])
    for name in INCLUDE_FILES:
        src = os.path.join(ROOT, name)
        if os.path.isfile(src) and keep(name):
            shutil.copy2(src, os.path.join(dest, name))


def compile_all(*folders):
    """Hash-checked .pyc for everything, so nothing compiles on first run."""
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("run this with Python 3.12 - the .pyc files it "
                         "writes are for the 3.12 inside the installer")
    import py_compile
    mode = py_compile.PycInvalidationMode.CHECKED_HASH
    for folder in folders:
        ok = compileall.compile_dir(folder, quiet=1, workers=0,
                                    invalidation_mode=mode)
        if not ok:
            say("note: some files in %s did not compile (usually test "
                "fixtures written for another Python); they are left as "
                "source" % os.path.relpath(folder, BUILD))


def check_signatures(python):
    if not shutil.which("osslsigncode"):
        say("osslsigncode not found - signatures not checked")
        return
    for name in sorted(os.listdir(python)):
        if not name.endswith((".exe", ".dll", ".pyd")):
            continue
        done = subprocess.run(["osslsigncode", "verify", "-in",
                               os.path.join(python, name)],
                              capture_output=True, text=True)
        signer = next((line.split("CN=")[-1] for line in
                       done.stdout.splitlines()
                       if "Subject:" in line and "CN=" in line), "")
        # The file is unchanged since it was signed. (Whether the chain
        # reaches a root is not asked: the code-signing roots are Windows'
        # own and a Linux build machine does not carry them.)
        digests = {}
        for line in done.stdout.splitlines():
            for label in ("Current message digest", "Calculated message digest"):
                if line.strip().startswith(label):
                    digests[label] = line.split(":", 1)[1].strip()
        intact = len(digests) == 2 and len(set(digests.values())) == 1
        say("  %-22s %s" % (name, signer or "UNSIGNED"))
        if not signer or not intact:
            raise SystemExit("%s is not signed as expected" % name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-signatures", action="store_true")
    args = parser.parse_args()

    version = version_of(build_stamp())
    if not version:
        raise SystemExit("VERSION.txt has no version")
    for tool in ("makensis", "uv"):
        if not shutil.which(tool):
            raise SystemExit("%s is needed on the PATH" % tool)

    stage = os.path.join(BUILD, "stage", "Squint")
    shutil.rmtree(os.path.join(BUILD, "stage"), ignore_errors=True)
    os.makedirs(stage)
    python = os.path.join(stage, ".venv")
    os.makedirs(python)

    say("Squint %s" % version)
    for _name, _ver, url, sha in RUNTIME:
        unpack_runtime(fetch(url, sha, os.path.join(BUILD, "cache")), python)
    trim_tcl(os.path.join(python, "tcl"))
    with open(os.path.join(python, "python312._pth"), "w",
              newline="\r\n") as fh:
        fh.write(PTH)
    if args.check_signatures:
        check_signatures(python)

    site = os.path.join(python, "Lib", "site-packages")
    say("packages")
    install_packages(site)
    say("app")
    copy_app(stage)
    say("compiling")
    compile_all(site, os.path.join(stage, "app"),
                os.path.join(stage, "tools"), os.path.join(python, "tkinter"))

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "Squint-Setup-%s.exe" % version)
    say("packing")
    subprocess.run(["makensis", "-V2", "-DVERSION=%s" % version,
                    "-DSTAGE=%s" % stage, "-DOUTFILE=%s" % out,
                    os.path.join(ROOT, "installer", "squint.nsi")],
                   check=True)
    digest = hashlib.sha256(open(out, "rb").read()).hexdigest()
    say("wrote %s (%.1f MB)" % (out, os.path.getsize(out) / 1e6))
    say("sha256 %s" % digest)


if __name__ == "__main__":
    main()
