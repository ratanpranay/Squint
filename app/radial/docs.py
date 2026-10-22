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
VIDEO_EXT = (".mov", ".mkv", ".avi", ".wmv", ".webm", ".flv", ".m4v",
             ".mpg", ".mpeg", ".3gp", ".mp4")

PDF_TYPES = [("PDF", "*.pdf")]
ANY_TYPES = [("All files", "*.*")]
TO_PDF_TYPES = [("Pictures, PDFs and Office files",
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
    out_dir = out_dir or os.path.dirname(os.path.abspath(src))
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
    raise RuntimeError("needs Microsoft Office (or LibreOffice) to convert "
                       "%s%s" % (os.path.basename(src),
                                 (": " + reason[:160]) if reason else ""))


def files_to_pdf(files, out, password=""):
    fitz = _fitz()
    doc = fitz.open()
    made = []
    try:
        for path in files:
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
        return save_pdf(doc, out, password)
    finally:
        doc.close()
        for tmp in made:
            try:
                os.remove(tmp)
            except OSError:
                pass


def merge_pdfs(files, out, password=""):
    fitz = _fitz()
    doc = fitz.open()
    for path in files:
        with fitz.open(path) as src:
            if src.needs_pass:
                raise RuntimeError("%s is password-protected"
                                   % os.path.basename(path))
            doc.insert_pdf(src)
    try:
        return save_pdf(doc, out, password)
    finally:
        doc.close()


def split_pdf(path, password=""):
    """Every page as its own PDF, in a folder next to the original."""
    fitz = _fitz()
    base = os.path.splitext(os.path.basename(path))[0]
    folder = common.unique(os.path.join(os.path.dirname(path),
                                        base + " - pages"))
    os.makedirs(folder)
    with fitz.open(path) as src:
        width = len(str(src.page_count))
        for i in range(src.page_count):
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


def _pdf_password(ctrl):
    return common.ask_password(
        ctrl.root, "Password", "Lock the PDF with a password? Anyone opening "
        "it will need to type it.", optional=True)


def pdf_cmd(ctrl, action, selection=None, **_):
    if action == "to_pdf":
        files = common.pick_files(ctrl, "Files to put in one PDF",
                                  TO_PDF_TYPES, selection=selection)
    elif action in ("split", "compress", "lock"):
        files = common.pick_files(ctrl, "Choose a PDF", PDF_TYPES, many=False,
                                  selection=selection)
    else:
        files = common.pick_files(ctrl, "PDFs to merge, in order", PDF_TYPES,
                                  selection=selection)
    if not files:
        return
    if action == "lock":
        password = common.ask_password(ctrl.root, "Lock PDF",
                                       "Password for %s"
                                       % os.path.basename(files[0]),
                                       optional=False)
    else:
        password = _pdf_password(ctrl)
    if password is None:
        return
    first = files[0]
    base = os.path.splitext(os.path.basename(first))[0]
    if action == "to_pdf":
        name = base + ".pdf" if len(files) == 1 else "Combined %s.pdf" % common.stamp()
        out = common.beside(first, name)
        work = lambda: files_to_pdf(files, out, password)   # noqa: E731
        what = "Making the PDF"
    elif action == "merge":
        out = common.beside(first, "Merged %s.pdf" % common.stamp())
        work = lambda: merge_pdfs(files, out, password)     # noqa: E731
        what = "Merging"
    elif action == "split":
        work = lambda: split_pdf(first, password)           # noqa: E731
        what = "Splitting"
    elif action == "compress":
        out = common.beside(first, base + " (smaller).pdf")
        work = lambda: compress_pdf(first, out, password)   # noqa: E731
        what = "Compressing"
    else:
        out = common.beside(first, base + " (locked).pdf")
        work = lambda: lock_pdf(first, out, password)       # noqa: E731
        what = "Locking"

    def done(result):
        if action == "compress":
            before, after = os.path.getsize(first), os.path.getsize(result)
            msg = "Smaller PDF saved: %.1f MB → %.1f MB." % (before / 1e6,
                                                             after / 1e6)
        elif action == "split":
            msg = "Pages saved in a folder."
        else:
            msg = "PDF saved%s." % (" with a password" if password else "")
        common.tell(ctrl, msg, result)

    common.in_background(ctrl, work, done, what)


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


def zip_plain(paths, out):
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zf:
        for full, arc in _walk(paths):
            zf.write(full, arc)
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


def extract_plain(path, folder):
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            target = os.path.realpath(os.path.join(folder, info.filename))
            if not target.startswith(os.path.realpath(folder) + os.sep) \
                    and target != os.path.realpath(folder):
                raise RuntimeError("the archive points outside its folder")
        zf.extractall(folder)
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


def zip_cmd(ctrl, action, selection=None, **_):
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
        folder = common.unique(os.path.join(os.path.dirname(path), name))
        locked = _needs_password(path)
        if locked is False:
            common.in_background(
                ctrl, lambda: extract_plain(path, folder),
                lambda f: common.tell(ctrl, "Extracted.", f), "Extracting")
            return
        password = ""
        if locked:
            password = common.ask_password(ctrl.root, "Password",
                                           "%s is protected." % name,
                                           optional=False, confirm=False)
            if password is None:
                return
        common.with_tool(
            ctrl, "7zip", "Getting 7-Zip (once)",
            lambda seven: common.in_background(
                ctrl, lambda: extract_7zip(seven, path, folder, password),
                lambda f: common.tell(ctrl, "Extracted.", f), "Extracting"))
        return

    files = common.pick_files(ctrl, "Files to zip", ANY_TYPES,
                              selection=selection)
    if not files:
        return
    first = files[0]
    name = (os.path.splitext(os.path.basename(first))[0] if len(files) == 1
            else "Archive %s" % common.stamp()) + ".zip"
    out = common.beside(first, name)
    if action == "plain":
        common.in_background(ctrl, lambda: zip_plain(files, out),
                             lambda p: common.tell(ctrl, "Zipped.", p),
                             "Zipping")
        return
    got = common.ask_password(
        ctrl.root, "Zip with password", "Password for the zip (AES-256).",
        optional=False,
        extra_check=("Compatible mode: opens in Windows Explorer without "
                     "7-Zip, but the protection is weak.", False))
    if got is None:
        return
    password, compatible = got
    common.with_tool(
        ctrl, "7zip", "Getting 7-Zip (once)",
        lambda seven: common.in_background(
            ctrl, lambda: zip_password(seven, files, out, password,
                                       compatible),
            lambda p: common.tell(ctrl, "Zipped with a password.", p),
            "Zipping"))


# -- converting --------------------------------------------------------

IMAGE_FORMATS = (("png", "PNG"), ("jpg", "JPG"), ("webp", "WebP"),
                 ("pdf", "PDF (one page each)"))


def convert_images(files, fmt, max_side=None, out_dir=None):
    from PIL import Image, ImageOps
    try:
        import pillow_heif                  # noqa: F401 - optional
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    done = []
    for path in files:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            if max_side and max(im.size) > max_side:
                im.thumbnail((max_side, max_side), Image.LANCZOS)
            base = os.path.splitext(os.path.basename(path))[0]
            folder = out_dir or os.path.dirname(path)
            suffix = " (%dpx)" % max_side if max_side else ""
            out = common.unique(os.path.join(folder, "%s%s.%s"
                                             % (base, suffix, fmt)))
            if fmt in ("jpg", "pdf"):
                im = im.convert("RGB")
            elif im.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                im = im.convert("RGBA")
            kw = {"quality": 90} if fmt in ("jpg", "webp") else {}
            im.save(out, {"jpg": "JPEG", "png": "PNG", "webp": "WEBP",
                          "pdf": "PDF"}[fmt], **kw)
            done.append(out)
    return done


def video_to_mp4(ffmpeg, src):
    base = os.path.splitext(os.path.basename(src))[0]
    out = common.beside(src, base + (" (converted)" if
                                     src.lower().endswith(".mp4") else "")
                        + ".mp4")
    args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", src,
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart", out]
    done = common.run(args, timeout=6 * 3600)
    if done.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(done.stderr.decode("utf-8", "replace")[-300:])
    return out


def convert_cmd(ctrl, action, selection=None, **_):
    if action == "image":
        files = common.pick_files(
            ctrl, "Pictures to convert",
            [("Pictures", " ".join("*" + e for e in IMAGE_EXT))],
            selection=selection)
        if not files:
            return
        fmt = common.ask_choice(ctrl.root, "Convert pictures",
                                "Save %d picture%s as" % (
                                    len(files), "" if len(files) == 1 else "s"),
                                IMAGE_FORMATS)
        if not fmt:
            return
        size = common.ask_choice(ctrl.root, "Size", "Resize?",
                                 [("0", "Keep the size"),
                                  ("3840", "Longest side 3840 px (4K)"),
                                  ("1920", "Longest side 1920 px"),
                                  ("1280", "Longest side 1280 px"),
                                  ("800", "Longest side 800 px")])
        if size is None:
            return
        common.in_background(
            ctrl, lambda: convert_images(files, fmt, int(size) or None),
            lambda out: common.tell(ctrl, "Converted %d picture%s."
                                    % (len(out), "" if len(out) == 1 else "s"),
                                    out[0]),
            "Converting")
    elif action == "office":
        files = common.pick_files(
            ctrl, "Office files to turn into PDF",
            [("Office files", " ".join("*" + e for e in OFFICE_EXT))],
            selection=selection)
        if not files:
            return
        common.in_background(
            ctrl, lambda: [office_to_pdf(f) for f in files],
            lambda out: common.tell(ctrl, "Converted to PDF.", out[0]),
            "Converting")
    else:
        files = common.pick_files(
            ctrl, "Video to convert",
            [("Videos", " ".join("*" + e for e in VIDEO_EXT))],
            many=False, selection=selection)
        if not files:
            return
        common.with_tool(
            ctrl, "ffmpeg", "Getting the video tools (once)",
            lambda ffmpeg: common.in_background(
                ctrl, lambda: video_to_mp4(ffmpeg, files[0]),
                lambda out: common.tell(ctrl, "Converted to MP4.", out),
                "Converting the video"))


# -- pulling media out of documents ------------------------------------

_MEDIA_DIRS = {".pptx": "ppt/media/", ".docx": "word/media/",
               ".xlsx": "xl/media/", ".potx": "ppt/media/",
               ".ppsx": "ppt/media/", ".dotx": "word/media/"}


def extract_media(path, out_dir=None, progress=None):
    """Every picture, video and sound inside a PowerPoint, Word or PDF,
    saved into its own folder in Downloads/Squint (or `out_dir`).
    `progress(done, total)` is called as files are written.
    Returns (folder, count)."""
    base, ext = os.path.splitext(os.path.basename(path))
    ext = ext.lower()
    folder = common.unique(os.path.join(out_dir or common.received_dir(),
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


def extract_cmd(ctrl, action, selection=None, **_):
    types = {"ppt": [("PowerPoint", "*.pptx *.ppsx *.potx")],
             "word": [("Word", "*.docx *.dotx")],
             "pdf": PDF_TYPES}[action]
    files = common.pick_files(ctrl, "Get the media out of", types,
                              selection=selection)
    if not files:
        return
    bar = common.Progress(ctrl.root, "Extracting media")
    bar.pump()

    def work():
        results = []
        for i, path in enumerate(files):
            name = os.path.basename(path)

            def tick(done, total, i=i, name=name):
                part = (done / float(total)) if total else 1.0
                bar.set((i + part) / len(files),
                        "%s   %d of %d" % (name, done, total))

            results.append(extract_media(path, progress=tick))
        return results

    def done(results):
        total = sum(n for _f, n in results)
        if not total:
            common.tell(ctrl, "No pictures or media found in %s."
                        % ("that file" if len(files) == 1 else "those files"))
            return
        folders = [f for f, n in results if n]
        # Open the folder itself, so the files are in front of the user.
        target = folders[0] if len(folders) == 1 else common.received_dir()
        try:
            from .. import platform_util
            platform_util.open_path(target)
        except Exception:
            pass
        common.tell(ctrl, "Saved %d file%s to Downloads\\Squint." % (
            total, "" if total == 1 else "s"), target)

    common.in_background(ctrl, work, done, "Extracting media", progress=bar)
