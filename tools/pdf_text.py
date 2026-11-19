"""Step 1 of the pipeline: PDF -> plain text (works for PDFs that contain real text, not scans)."""
import pdfplumber


def pdf_to_text(source) -> str:
    """`source` can be a file path or a file-like object."""
    with pdfplumber.open(source) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages).strip()
