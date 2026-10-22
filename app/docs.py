"""File ingestion: JPEG/PNG/other images and PDFs -> extracted text -> export."""
import os

from PIL import Image

from . import ocr

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff",
             ".webp", ".jfif"}
PDF_EXT = {".pdf"}
SUPPORTED_EXT = IMAGE_EXT | PDF_EXT

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None


class Page:
    __slots__ = ("number", "source_text", "translated", "via_ocr")

    def __init__(self, number, source_text, via_ocr=False):
        self.number = number
        self.source_text = source_text
        self.translated = ""
        self.via_ocr = via_ocr


def is_supported(path):
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXT


def extract(path, progress=None):
    """Returns a list of Page. progress(done, total, label) is optional."""
    ext = os.path.splitext(path)[1].lower()
    if ext in PDF_EXT:
        return _extract_pdf(path, progress)
    if ext in IMAGE_EXT:
        if progress:
            progress(0, 1, "Reading image")
        with Image.open(path) as img:
            img.load()
            text, _lang = ocr.image_to_text(img.convert("RGB"), psm=3)
        if progress:
            progress(1, 1, "Read image")
        return [Page(1, text, via_ocr=True)]
    raise ValueError("Unsupported file type: %s" % ext)


def _extract_pdf(path, progress=None):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. Re-run build.bat.")
    pages = []
    with fitz.open(path) as doc:
        total = doc.page_count
        for index in range(total):
            page = doc.load_page(index)
            text = (page.get_text("text") or "").strip()
            via_ocr = False
            # A scanned page has an empty (or near-empty) text layer.
            if len(text) < 20:
                via_ocr = True
                pix = page.get_pixmap(dpi=300, colorspace=fitz.csRGB)
                img = Image.frombytes("RGB", (pix.width, pix.height),
                                      pix.samples)
                try:
                    text, _lang = ocr.image_to_text(img, psm=3)
                except Exception as exc:
                    text = ""
                    if progress:
                        progress(index + 1, total, "OCR failed on page %d: %s"
                                 % (index + 1, exc))
            else:
                text = ocr.clean(text)
            pages.append(Page(index + 1, text, via_ocr=via_ocr))
            if progress:
                progress(index + 1, total,
                         "Read page %d/%d%s" % (index + 1, total,
                                                " (OCR)" if via_ocr else ""))
    return pages


# -- export ------------------------------------------------------------
def export_txt(pages, dest, include_original=True):
    with open(dest, "w", encoding="utf-8") as fh:
        for page in pages:
            if len(pages) > 1:
                fh.write("=== Page %d ===\n\n" % page.number)
            if include_original and page.source_text:
                fh.write("--- Original ---\n%s\n\n" % page.source_text)
                fh.write("--- Translation ---\n")
            fh.write((page.translated or "") + "\n\n")
    return dest


def export_docx(pages, dest, include_original=True, target_label=""):
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Segoe UI"
    style.font.size = Pt(11)

    heading = doc.add_heading("Translation", level=1)
    if target_label:
        doc.add_paragraph("Target language: %s" % target_label)
    del heading

    for page in pages:
        if len(pages) > 1:
            doc.add_heading("Page %d" % page.number, level=2)
        if include_original and page.source_text:
            doc.add_heading("Original", level=3)
            for para in page.source_text.split("\n\n"):
                if para.strip():
                    doc.add_paragraph(para.strip())
            doc.add_heading("Translation", level=3)
        for para in (page.translated or "").split("\n\n"):
            if para.strip():
                doc.add_paragraph(para.strip())
    doc.save(dest)
    return dest


def export_pdf(pages, dest, include_original=True, target_label=""):
    """Simple text PDF via reportlab; falls back to .txt if unavailable."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.units import mm
    from xml.sax.saxutils import escape

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(dest, pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    flow = [Paragraph("Translation", styles["Title"])]
    if target_label:
        flow.append(Paragraph("Target language: %s" % escape(target_label),
                              styles["Normal"]))
    flow.append(Spacer(1, 8))
    for page in pages:
        if len(pages) > 1:
            flow.append(Paragraph("Page %d" % page.number, styles["Heading2"]))
        if include_original and page.source_text:
            flow.append(Paragraph("Original", styles["Heading3"]))
            for para in page.source_text.split("\n\n"):
                if para.strip():
                    flow.append(Paragraph(escape(para.strip()),
                                          styles["Normal"]))
                    flow.append(Spacer(1, 4))
            flow.append(Paragraph("Translation", styles["Heading3"]))
        for para in (page.translated or "").split("\n\n"):
            if para.strip():
                flow.append(Paragraph(escape(para.strip()), styles["Normal"]))
                flow.append(Spacer(1, 4))
    doc.build(flow)
    return dest
