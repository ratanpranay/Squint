"""Files: PDF tools, zip, conversion and pulling media out of documents.

Every function here that touches files works without a window, so it can
be tested on its own; the `*_cmd` functions are what the menu calls, and
add the choosing and the asking."""
import os
import shutil
import tempfile
import zipfile

from . import common

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff",
             ".webp", ".heic")
OFFICE_EXT = (".doc", ".docx", ".rtf", ".odt", ".ppt", ".pptx", ".odp",
              ".xls", ".xlsx", ".ods")
if common.IS_MAC:
    OFFICE_EXT += (".pages", ".key", ".numbers")
VIDEO_EXT = (".mov", ".mkv", ".avi", ".wmv", ".webm", ".flv", ".f4v",
             ".m4v", ".mpg", ".mpeg", ".m2v", ".ts", ".mts", ".m2ts",
             ".vob", ".3gp", ".3g2", ".ogv", ".asf", ".divx", ".rm",
             ".rmvb", ".mxf", ".mp4")

PDF_TYPES = [("PDF", "*.pdf")]
ANY_TYPES = [("All files", "*.*")]
TO_PDF_TYPES = [("Documents, slides, sheets, pictures and PDFs",
                 " ".join("*" + e for e in IMAGE_EXT + (".pdf",) + OFFICE_EXT)),
                ("All files", "*.*")]


def _fitz():
    try:
        import pymupdf as fitz
    except Exception:
        import fitz
    return fitz


# -- PDF ---------------------------------------------------------------

def save_pdf(doc, path, password=""):
    fitz = _fitz()
    kw = {"garbage": 3, "deflate": True}
    if password:
        kw.update(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=password,
                  user_pw=password,
                  permissions=int(fitz.PDF_PERM_ACCESSIBILITY
                                  | fitz.PDF_PERM_PRINT | fitz.PDF_PERM_COPY))
    doc.save(path, **kw)
    return path


def office_to_pdf(src, out_dir=None):
    """An Office file as PDF, through Office itself (or LibreOffice)."""
    out_dir = out_dir or common.squint_dir("pdf")
    base = os.path.splitext(os.path.basename(src))[0]
    out = common.unique(os.path.join(out_dir, base + ".pdf"))
    ext = os.path.splitext(src)[1].lower()
    if common.IS_WINDOWS:
        q = lambda p: "'" + p.replace("'", "''") + "'"   # noqa: E731
        if ext in (".doc", ".docx", ".rtf", ".odt"):
            script = ("$a=New-Object -ComObject Word.Application;"
                      "$a.Visible=$false;$d=$a.Documents.Open(%s,$false,$true);"
                      "$d.ExportAsFixedFormat(%s,17);$d.Close(0);$a.Quit()"
                      % (q(src), q(out)))
        elif ext in (".ppt", ".pptx", ".odp"):
            script = ("$a=New-Object -ComObject PowerPoint.Application;"
                      "$p=$a.Presentations.Open(%s,$true,$false,$false);"
                      "$p.SaveAs(%s,32);$p.Close();$a.Quit()" % (q(src), q(out)))
        else:
            script = ("$a=New-Object -ComObject Excel.Application;"
                      "$a.DisplayAlerts=$false;$w=$a.Workbooks.Open(%s,0,$true);"
                      "$w.ExportAsFixedFormat(0,%s);$w.Close($false);$a.Quit()"
                      % (q(src), q(out)))
        done = common.run(["powershell", "-NoProfile", "-NonInteractive",
                           "-Command", script], timeout=180)
        if os.path.isfile(out):
            return out
        reason = done.stderr.decode("utf-8", "replace").strip()
    elif common.IS_MAC:
        reason = _iwork_to_pdf(src, out)
        if reason is None:
            return out
    else:
        reason = ""
    office = shutil.which("soffice") or shutil.which("libreoffice")
    if office:
        tmp = tempfile.mkdtemp()
        common.run([office, "--headless", "--convert-to", "pdf", "--outdir",
                    tmp, src], timeout=180)
        made = os.path.join(tmp, base + ".pdf")
        if os.path.isfile(made):
            shutil.move(made, out)
            return out
    if common.IS_MAC:
        need = {"pages": "Pages", "keynote": "Keynote",
                "numbers": "Numbers"}[_IWORK.get(ext, "pages")]
        raise RuntimeError("needs %s (free from the App Store) to convert %s"
                           "%s" % (need, os.path.basename(src),
                                   (": " + reason[:160]) if reason else ""))
    raise RuntimeError("needs Microsoft Office (or LibreOffice) to convert "
                       "%s%s" % (os.path.basename(src),
                                 (": " + reason[:160]) if reason else ""))


_IWORK = {".doc": "pages", ".docx": "pages", ".rtf": "pages",
          ".odt": "pages", ".pages": "pages",
          ".ppt": "keynote", ".pptx": "keynote", ".odp": "keynote",
          ".key": "keynote",
          ".xls": "numbers", ".xlsx": "numbers", ".ods": "numbers",
          ".numbers": "numbers"}


def _iwork_to_pdf(src, out):
    """A Mac has Pages, Keynote and Numbers, which open Word, PowerPoint
    and Excel files and export PDF. None when it worked, else why not."""
    app = {"pages": "Pages", "keynote": "Keynote", "numbers": "Numbers"}[
        _IWORK.get(os.path.splitext(src)[1].lower(), "pages")]
    if not os.path.isdir("/Applications/%s.app" % app):
        return "%s is not installed" % app

    def s(path):
        return path.replace("\\", "\\\\").replace('"', '\\"')

    script = ('set inF to (POSIX file "%s") as alias\n'
              'set outF to POSIX file "%s"\n'
              'tell application "%s"\n'
              '  set d to open inF\n'
              '  export d to outF as PDF\n'
              '  close d saving no\n'
              'end tell' % (s(src), s(out), app))
    done = common.run(["osascript", "-e", script], timeout=300)
    if os.path.isfile(out):
        return None
    return done.stderr.decode("utf-8", "replace").strip() or \
        "%s could not export it" % app


def files_to_pdf(files, out, password="", progress=None):
    tick = progress or (lambda *_a: None)
    fitz = _fitz()
    doc = fitz.open()
    made = []
    try:
        for n, path in enumerate(files):
            tick(n / float(len(files)), os.path.basename(path))
            ext = os.path.splitext(path)[1].lower()
            if ext == ".pdf":
                with fitz.open(path) as src:
                    doc.insert_pdf(src)
            elif ext in OFFICE_EXT:
                tmp = office_to_pdf(path, tempfile.mkdtemp())
                made.append(tmp)
                with fitz.open(tmp) as src:
                    doc.insert_pdf(src)
            else:
                from PIL import Image, ImageOps
                with Image.open(path) as im:
                    im = ImageOps.exif_transpose(im).convert("RGB")
                    buf = tempfile.NamedTemporaryFile(suffix=".jpg",
                                                      delete=False)
                    buf.close()
                    im.save(buf.name, quality=92)
                    made.append(buf.name)
                    w, h = im.size
                # A4 width at 150 dpi-ish: the picture fills the page.
                page = doc.new_page(width=w * 72 / 150.0, height=h * 72 / 150.0)
                page.insert_image(page.rect, filename=buf.name)
        if doc.page_count == 0:
            raise RuntimeError("nothing in those files could go into a PDF")
        tick(None, "Saving")
        return save_pdf(doc, out, password)
    finally:
        doc.close()
        for tmp in made:
            try:
                os.remove(tmp)
            except OSError:
                pass


def merge_pdfs(files, out, password="", progress=None):
    tick = progress or (lambda *_a: None)
    fitz = _fitz()
    doc = fitz.open()
    for n, path in enumerate(files):
        tick(n / float(len(files)), os.path.basename(path))
        with fitz.open(path) as src:
            if src.needs_pass:
                raise RuntimeError("%s is password-protected"
                                   % os.path.basename(path))
            doc.insert_pdf(src)
    tick(None, "Saving")
    try:
        return save_pdf(doc, out, password)
    finally:
        doc.close()


def split_pdf(path, password="", progress=None):
    """Every page as its own PDF, in a folder in Downloads/Squint/PDF."""
    fitz = _fitz()
    base = os.path.splitext(os.path.basename(path))[0]
    folder = common.unique(os.path.join(common.squint_dir("pdf"),
                                        base + " - pages"))
    os.makedirs(folder)
    with fitz.open(path) as src:
        width = len(str(src.page_count))
        for i in range(src.page_count):
            if progress:
                progress(i / float(src.page_count), "Page %d of %d"
                         % (i + 1, src.page_count))
            one = fitz.open()
            one.insert_pdf(src, from_page=i, to_page=i)
            save_pdf(one, os.path.join(folder, "%s - page %0*d.pdf"
                                       % (base, width, i + 1)), password)
            one.close()
    return folder


def compress_pdf(path, out, password=""):
    fitz = _fitz()
    with fitz.open(path) as doc:
        if hasattr(doc, "rewrite_images"):
            try:
                doc.rewrite_images(dpi_threshold=160, dpi_target=150,
                                   quality=75)
            except Exception as exc:      # noqa: BLE001 - still compressible
                common.log("rewrite_images: %r" % exc)
        kw = {"garbage": 4, "deflate": True, "clean": True}
        if password:
            kw.update(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=password,
                      user_pw=password)
        doc.save(out, **kw)
    return out


def lock_pdf(path, out, password):
    fitz = _fitz()
    with fitz.open(path) as doc:
        if doc.needs_pass:
            raise RuntimeError("it already has a password")
        return save_pdf(doc, out, password)


# -- zip ---------------------------------------------------------------

def _walk(paths):
    """(full path, name inside the archive) for files and whole folders."""
    for path in paths:
        path = os.path.abspath(path)
        if os.path.isdir(path):
            top = os.path.dirname(path)
            for folder, _dirs, names in os.walk(path):
                for name in names:
                    full = os.path.join(folder, name)
                    yield full, os.path.relpath(full, top)
        else:
            yield path, os.path.basename(path)


def zip_plain(paths, out, progress=None):
    items = list(_walk(paths))
    total = sum(os.path.getsize(f) for f, _a in items) or 1
    done = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zf:
        for full, arc in items:
            if progress:
                progress(done / float(total), os.path.basename(full))
            zf.write(full, arc)
            done += os.path.getsize(full)
    return out


def zip_password(seven, paths, out, password, compatible=False):
    method = "ZipCrypto" if compatible else "AES256"
    args = [seven, "a", "-tzip", "-mem=" + method, "-p" + password, "-y",
            out] + [os.path.abspath(p) for p in paths]
    done = common.run(args, timeout=3600)
    if done.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(done.stderr.decode("utf-8", "replace")[-300:])
    return out


def _needs_password(path):
    if not zipfile.is_zipfile(path):
        return None                          # not a zip: 7-Zip decides
    with zipfile.ZipFile(path) as zf:
        return any(info.flag_bits & 0x1 for info in zf.infolist())


def extract_plain(path, folder, progress=None):
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        for info in infos:
            target = os.path.realpath(os.path.join(folder, info.filename))
            if not target.startswith(os.path.realpath(folder) + os.sep) \
                    and target != os.path.realpath(folder):
                raise RuntimeError("the archive points outside its folder")
        for n, info in enumerate(infos):
            if progress:
                progress(n / float(len(infos)),
                         os.path.basename(info.filename.rstrip("/")))
            zf.extract(info, folder)
    return folder


def extract_7zip(seven, path, folder, password=""):
    args = [seven, "x", "-y", "-o" + folder, "-p" + (password or ""), path]
    done = common.run(args, timeout=3600)
    if done.returncode != 0:
        err = done.stderr.decode("utf-8", "replace")
        if "Wrong password" in err or "password" in err.lower():
            raise RuntimeError("wrong password")
        raise RuntimeError(err.strip()[-300:])
    return folder


# -- video --------------------------------------------------------

def video_to_mp4(ffmpeg, src):
    base = os.path.splitext(os.path.basename(src))[0]
    out = common.into("rec", base + ".mp4")
    args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", src,
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart", out]
    done = common.run(args, timeout=6 * 3600)
    if done.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(done.stderr.decode("utf-8", "replace")[-300:])
    return out


# -- pulling media out of documents ------------------------------------

_MEDIA_DIRS = {".pptx": "ppt/media/", ".docx": "word/media/",
               ".xlsx": "xl/media/", ".potx": "ppt/media/",
               ".ppsx": "ppt/media/", ".dotx": "word/media/"}


def extract_media(path, out_dir=None, progress=None):
    """Every picture, video and sound inside a PowerPoint, Word or PDF,
    saved into its own folder in Downloads/Squint/Extracted media.
    `progress(done, total)` is called as files are written.
    Returns (folder, count)."""
    base, ext = os.path.splitext(os.path.basename(path))
    ext = ext.lower()
    folder = common.unique(os.path.join(out_dir or common.squint_dir("ext"),
                                        base + " - media"))
    os.makedirs(folder)
    count = 0
    tick = progress or (lambda _d, _t: None)
    if ext in _MEDIA_DIRS:
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist()
                     if n.startswith(_MEDIA_DIRS[ext]) and not n.endswith("/")]
            tick(0, len(names))
            for name in names:
                target = common.unique(os.path.join(
                    folder, os.path.basename(name)))
                with zf.open(name) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                count += 1
                tick(count, len(names))
    elif ext == ".pdf":
        fitz = _fitz()
        seen = set()
        with fitz.open(path) as doc:
            pages = doc.page_count
            tick(0, pages)
            for pno in range(pages):
                for info in doc.get_page_images(pno, full=True):
                    xref = info[0]
                    if xref in seen:
                        continue
                    seen.add(xref)
                    try:
                        img = doc.extract_image(xref)
                    except Exception:
                        continue
                    if not img or not img.get("image"):
                        continue
                    target = os.path.join(folder, "page %d - image %d.%s"
                                          % (pno + 1, len(seen),
                                             img.get("ext", "png")))
                    with open(target, "wb") as out:
                        out.write(img["image"])
                    count += 1
                tick(pno + 1, pages)
    else:
        os.rmdir(folder)
        raise RuntimeError("%s files are not supported (only PowerPoint, Word "
                           "and PDF in their current formats)" % ext)
    if count == 0:
        os.rmdir(folder)
    return folder, count




# -- what the menu calls: each action in one card ------------------------
#
# Files come from Explorer's selection or a file dialog first; then one
# card next to the ring takes it from settings to progress to "Open folder".

from .card import Card, ensure_tool                       # noqa: E402


def _n(files, word="file"):
    return "%d %s%s" % (len(files), word, "" if len(files) == 1 else "s")


def _subtitle(files):
    names = ", ".join(os.path.basename(f) for f in files[:2])
    return names + (" and %d more" % (len(files) - 2) if len(files) > 2
                    else "")


PASSWORD = {"kind": "password", "key": "password", "optional": True,
            "label": "Lock with a password (AES-256)"}

_PDF = {
    "to_pdf": ("Convert to PDF", "Convert"),
    "merge": ("Merge PDFs", "Merge"),
    "split": ("Split PDF", "Split"),
    "compress": ("Compress PDF", "Compress"),
    "lock": ("Password-lock PDF", "Lock"),
}


def pdf_cmd(ctrl, action, selection=None, anchor=None, menu=None, **_):
    if action == "to_pdf":
        files = common.pick_files(ctrl, "Files to turn into PDF",
                                  TO_PDF_TYPES, selection=selection)
    elif action in ("split", "compress", "lock"):
        files = common.pick_files(ctrl, "Choose a PDF", PDF_TYPES, many=False,
                                  selection=selection)
    else:
        files = common.pick_files(ctrl, "PDFs to merge, in order", PDF_TYPES,
                                  selection=selection)
    if not files:
        return
    title, verb = _PDF[action]
    card = Card(ctrl, title, anchor, _subtitle(files), host=menu)
    first = files[0]
    base = os.path.splitext(os.path.basename(first))[0]
    pw = dict(PASSWORD)
    if action == "lock":
        pw.update(optional=False)

    def start(values):
        password = values.get("password", "")
        if action == "to_pdf" and values.get("how") == "each":
            def work(p):
                made = []
                for n, f in enumerate(files):
                    name = os.path.splitext(os.path.basename(f))[0]
                    one = common.into("pdf", name + ".pdf")

                    def step(frac, text=None, n=n, f=f):
                        p((n + (frac or 0)) / float(len(files)),
                          text or os.path.basename(f))

                    made.append(files_to_pdf([f], one, password, step))
                return made
        elif action == "to_pdf":
            name = base + ".pdf" if len(files) == 1 else \
                "Combined %s.pdf" % common.stamp()
            out = common.into("pdf", name)
            work = lambda p: files_to_pdf(files, out, password, p)  # noqa
        elif action == "merge":
            out = common.into("pdf", "Merged %s.pdf" % common.stamp())
            work = lambda p: merge_pdfs(files, out, password, p)    # noqa
        elif action == "split":
            work = lambda p: split_pdf(first, password, p)          # noqa
        elif action == "compress":
            out = common.into("pdf", base + " (smaller).pdf")

            def work(p):
                p(None, "Making it smaller")
                return compress_pdf(first, out, password)
        else:
            out = common.into("pdf", base + " (locked).pdf")

            def work(p):
                p(None, "Locking")
                return lock_pdf(first, out, password)

        def finish(result):
            if isinstance(result, list):
                return ("Made %d PDFs" % len(result)
                        + (" with a password" if password else ""),
                        common.squint_dir("pdf"))
            if action == "compress":
                return ("%.1f MB → %.1f MB" % (os.path.getsize(first) / 1e6,
                                               os.path.getsize(result) / 1e6),
                        result)
            if action == "split":
                return "Every page saved as its own PDF", result
            return "PDF saved" + (" with a password" if password else ""), \
                result

        card.run(work, finish, "%s…" % verb.replace("Convert", "Converting"))

    fields = [pw]
    if action == "to_pdf" and len(files) > 1:
        fields.insert(0, {"kind": "choice", "key": "how", "label": "Make",
                          "options": (("one", "One PDF"),
                                      ("each", "A PDF for each")),
                          "default": "one"})
    card.form(fields, verb, start)


def zip_cmd(ctrl, action, selection=None, anchor=None, menu=None, **_):
    if action == "extract":
        files = common.pick_files(ctrl, "Archive to extract",
                                  [("Archives", "*.zip *.7z *.tar *.gz *.tgz "
                                    "*.bz2 *.xz"), ("All files", "*.*")],
                                  many=False, selection=selection)
        if not files:
            return
        path = files[0]
        name = os.path.basename(path)
        for ext in (".tar.gz", ".tar.bz2", ".tar.xz", ".zip", ".7z", ".tgz",
                    ".tar"):
            if name.lower().endswith(ext):
                name = name[:-len(ext)]
                break
        folder = common.unique(os.path.join(common.squint_dir("zip"), name))
        locked = _needs_password(path)
        card = Card(ctrl, "Extract", anchor, os.path.basename(path), host=menu)

        def finish(result):
            return "Extracted", result

        def go(password):
            if locked is False:
                card.run(lambda p: extract_plain(path, folder, p), finish,
                         "Extracting…")
                return

            def work(p):
                seven = ensure_tool(p, "7zip")
                p(None, "Extracting")
                return extract_7zip(seven, path, folder, password)

            card.run(work, finish, "Extracting…")

        if locked:
            card.form([{"kind": "password", "key": "password",
                        "optional": False}], "Extract",
                      lambda v: go(v["password"]))
        else:
            go("")
        return

    files = common.pick_files(ctrl, "Files to zip", ANY_TYPES,
                              selection=selection)
    if not files:
        return
    name = (os.path.splitext(os.path.basename(files[0]))[0] if len(files) == 1
            else "Archive %s" % common.stamp()) + ".zip"
    out = common.into("zip", name)
    if action == "plain":
        card = Card(ctrl, "Zip", anchor, _subtitle(files), host=menu)
        card.run(lambda p: zip_plain(files, out, p),
                 lambda r: ("Zipped " + _n(files), r), "Zipping…")
        return
    card = Card(ctrl, "Zip with password", anchor, _subtitle(files), host=menu)

    def start(values):
        def work(p):
            seven = ensure_tool(p, "7zip")
            p(None, "Zipping")
            return zip_password(seven, files, out, values["password"],
                                values["compatible"])

        card.run(work, lambda r: ("Zipped with a password", r), "Zipping…")

    card.form([{"kind": "password", "key": "password", "optional": False},
               {"kind": "check", "key": "compatible", "default": False,
                "label": "Compatible mode: opens without 7-Zip, but the "
                         "protection is weak"}],
              "Zip", start)


def video_to_mp4_mac(src):
    """macOS's own converter (avconvert), so nothing has to be fetched."""
    if not shutil.which("avconvert"):
        raise RuntimeError("this Mac has no video converter (avconvert); "
                           "install FFmpeg to convert videos")
    base = os.path.splitext(os.path.basename(src))[0]
    out = common.into("rec", base + ".mp4")
    done = common.run(["avconvert", "--source", src, "--output", out,
                       "--preset", "PresetHighestQuality", "--replace"],
                      timeout=6 * 3600)
    if done.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError((done.stderr or done.stdout).decode(
            "utf-8", "replace")[-300:])
    return out


def video_cmd(ctrl, selection=None, anchor=None, menu=None, **_):
    """Any common video as MP4, saved beside the recordings."""
    files = common.pick_files(
        ctrl, "Video to convert",
        [("Videos", " ".join("*" + e for e in VIDEO_EXT)),
         ("All files", "*.*")],
        many=False, selection=selection)
    if not files:
        return
    card = Card(ctrl, "Video to MP4", anchor, _subtitle(files), host=menu)

    def work(p):
        try:
            ffmpeg = ensure_tool(p, "ffmpeg")
        except Exception:
            if not common.IS_MAC:
                raise
            # No download: the Mac's own converter still does MOV and M4V.
            p(None, "Converting the video")
            return video_to_mp4_mac(files[0])
        p(None, "Converting the video")
        return video_to_mp4(ffmpeg, files[0])

    card.run(work, lambda out: ("Converted to MP4", out), "Converting…")


def extract_cmd(ctrl, action, selection=None, anchor=None, menu=None, **_):
    types = {"ppt": [("PowerPoint", "*.pptx *.ppsx *.potx")],
             "word": [("Word", "*.docx *.dotx")],
             "pdf": PDF_TYPES}[action]
    files = common.pick_files(ctrl, "Get the media out of", types,
                              selection=selection)
    if not files:
        return
    card = Card(ctrl, "Extract media", anchor, _subtitle(files), host=menu)

    def work(p):
        results = []
        for i, path in enumerate(files):
            name = os.path.basename(path)

            def tick(done, total, i=i, name=name):
                part = (done / float(total)) if total else 1.0
                p((i + part) / len(files), "%s  %d of %d" % (name, done, total))

            results.append(extract_media(path, progress=tick))
        return results

    def finish(results):
        total = sum(n for _f, n in results)
        if not total:
            raise RuntimeError("No pictures, videos or sounds in %s."
                               % ("that file" if len(files) == 1
                                  else "those files"))
        folders = [f for f, n in results if n]
        target = folders[0] if len(folders) == 1 else common.squint_dir("ext")
        return "Saved %d file%s" % (total, "" if total == 1 else "s"), target

    card.run(work, finish, "Extracting media…")
