"""Translate a file and give back the same kind of file.

Pulling the words out of a PDF and showing them in a text box loses the thing
that made it a PDF: the layout, the tables, the picture the text sits beside.
For a scanned page or a photo it is worse still — you get a wall of text where
there was a document.

So the picture is kept and the words are replaced in place, the same way the
screen overlay works: OCR each page, translate, draw the translation back over
the box each line came from. A JPEG in, a JPEG out. A PDF in, a PDF out.
"""
import os

from PIL import Image

from . import ocr, overlay, translator

IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")
PDF_TYPES = (".pdf",)

# Rendering a PDF page at 2x gives OCR enough pixels to read small print
# without making the output file enormous.
PDF_RENDER_SCALE = 2.0


def is_supported(path):
    return path.lower().endswith(IMAGE_TYPES + PDF_TYPES)


def translated_name(path, suffix="-translated"):
    root, ext = os.path.splitext(path)
    return "%s%s%s" % (root, suffix, ext)


# A page's paragraphs go to the engine together, a batch at a time, the
# way a snip's lines do: one request a page instead of one a paragraph —
# and on this computer, several paragraphs side by side. A batch stays
# under the size one request can take.
BATCH_CHARS = 3500
BATCH_UNITS = 25


def translate_units(texts, target):
    """One translation per paragraph, in page order. A paragraph too long
    to share a request goes on its own; a batch that fails is translated a
    paragraph at a time, as before."""
    flat = [" ".join(str(t or "").split()) for t in texts]
    out = [""] * len(flat)
    batch, size = [], 0

    def send(indexes):
        if not indexes:
            return
        try:
            got = translator.translate_lines([flat[i] for i in indexes],
                                             target=target)
            if len(got) == len(indexes):
                for i, text in zip(indexes, got):
                    out[i] = text
                missing = [i for i in indexes
                           if flat[i] and not str(out[i] or "").strip()]
            else:
                missing = [i for i in indexes if flat[i]]
        except Exception:
            missing = [i for i in indexes if flat[i]]
        for i in missing:
            try:
                out[i] = translator.translate(flat[i], target=target)
            except Exception:
                out[i] = ""

    for index, text in enumerate(flat):
        if not text:
            continue
        if len(text) > BATCH_CHARS:
            send(batch)
            batch, size = [], 0
            try:
                out[index] = translator.translate(text, target=target)
            except Exception:
                out[index] = ""
            continue
        if batch and (size + len(text) > BATCH_CHARS
                      or len(batch) >= BATCH_UNITS):
            send(batch)
            batch, size = [], 0
        batch.append(index)
        size += len(text) + 1
    send(batch)
    return out


def translate_image(image, target, progress=None):
    """Return (translated image, lines drawn, plain text)."""
    lines, _lang = ocr.image_to_lines(image)
    if not lines:
        return image, 0, ""
    if progress:
        progress("translating %d lines…" % len(lines))
    texts = overlay.translate_grouped(lines, translator, target)
    rendered, drawn = overlay.render(image, lines, texts, target)
    plain = "\n".join(t for t in texts if t and t.strip())
    return rendered, drawn, plain


def _page_count(path):
    """How many pages, for a bar that has to know where the end is.

    Nought rather than raising: a count that cannot be had is a reason to
    show progress without an end in sight, not a reason to fail the
    translation that was going to work anyway.
    """
    try:
        import fitz
        document = fitz.open(path)
        try:
            return document.page_count
        finally:
            document.close()
    except Exception:
        return 0


def _pdf_pages(path):
    import fitz
    document = fitz.open(path)
    try:
        for index in range(document.page_count):
            page = document.load_page(index)
            matrix = fitz.Matrix(PDF_RENDER_SCALE, PDF_RENDER_SCALE)
            pixmap = page.get_pixmap(matrix=matrix)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height),
                                    pixmap.samples)
            yield index, image, page.rect.width, page.rect.height
    finally:
        document.close()


def _translate_pdf_text(path, target, dest, progress=None, steps=None):
    """Translate a PDF through its own text. None if it hasn't got any.

    Returning None rather than raising is the whole safety of this: a
    scanned page, a page of vector outlines, a file whose character map is
    broken — anything this cannot read honestly — falls through to the
    recogniser below, which is what the app did before. The worst case for
    any document is therefore the old behaviour, never something worse.
    """
    from . import pdf_text
    try:
        import pymupdf
    except Exception:
        try:
            import fitz as pymupdf          # older installs
        except Exception:
            return None

    try:
        document = pymupdf.open(path)
    except Exception:
        return None

    try:
        if not document.page_count:
            return None
        readable = sum(1 for page in document if pdf_text.has_text(page))
        # Some pages of a real document are pictures — a scanned annex, a
        # chart. One page in five carrying text is not a text PDF, and
        # translating those pages while photographing the rest would give
        # back a document in two languages.
        if readable < max(1, document.page_count * 0.6):
            return None

        total, chunks = 0, []
        count = document.page_count
        if steps:
            steps(0, count)
        for index, page in enumerate(document):
            if progress:
                progress("page %d of %d…" % (index + 1, count))
            if steps:
                steps(index, count)
            if not pdf_text.has_text(page):
                continue
            lines = pdf_text.lines_on(page)
            units = pdf_text.paragraphs(lines, overlay.group_paragraphs)
            if not units:
                continue
            texts = translate_units([unit["text"] for unit in units],
                                    target)
            pdf_text.erase(page, units)
            for unit, text in zip(units, texts):
                if not str(text or "").strip():
                    continue
                if pdf_text.place(page, unit, text, target):
                    total += 1
                    chunks.append(text)
        if not total:
            return None
        pages = document.page_count
        document.save(dest, garbage=3, deflate=True)
    except Exception:
        return None
    finally:
        try:
            document.close()
        except Exception:
            pass
    return dest, pages, total, "\n\n".join(chunks)


def translate_file(path, target, dest=None, progress=None, steps=None):
    """Translate `path` into a new file of the same type.

    Returns (destination path, pages, lines drawn, plain text).
    """
    dest = dest or translated_name(path)
    lower = path.lower()

    if lower.endswith(IMAGE_TYPES):
        if progress:
            progress("reading the image…")
        if steps:
            steps(0, 1)
        image = Image.open(path).convert("RGB")
        rendered, drawn, plain = translate_image(image, target, progress)
        # Keep the original format; JPEG cannot hold alpha, which is why the
        # image is converted to RGB above.
        rendered.save(dest)
        if steps:
            steps(1, 1)
        return dest, 1, drawn, plain

    if not lower.endswith(PDF_TYPES):
        raise ValueError("unsupported file type")

    done = _translate_pdf_text(path, target, dest, progress, steps)
    if done is not None:
        return done

    import fitz
    out = fitz.open()
    total_drawn, page_count, chunks = 0, 0, []
    try:
        pages_total = _page_count(path)
        if steps:
            steps(0, pages_total)
        for index, image, width, height in _pdf_pages(path):
            if progress:
                progress("page %d of %d…" % (index + 1, pages_total)
                         if pages_total else "page %d…" % (index + 1))
            if steps:
                steps(index, pages_total)
            rendered, drawn, plain = translate_image(image, target, progress)
            total_drawn += drawn
            page_count += 1
            if plain:
                chunks.append(plain)

            import io
            buffer = io.BytesIO()
            # JPEG, not PNG. A 2x A4 page as lossless PNG is several
            # megabytes, so a short document came out at 12 MB — big enough
            # to be useless to email. At quality 90 the same page is a few
            # hundred KB and the text is still clean.
            rendered.save(buffer, format="JPEG", quality=90, optimize=True)
            # New page at the original page size, so the output opens at the
            # same dimensions as the file that went in.
            new_page = out.new_page(width=width, height=height)
            new_page.insert_image(fitz.Rect(0, 0, width, height),
                                  stream=buffer.getvalue())
        if not page_count:
            raise ValueError("this PDF has no pages")
        out.save(dest)
    finally:
        out.close()
    return dest, page_count, total_drawn, "\n\n".join(chunks)
