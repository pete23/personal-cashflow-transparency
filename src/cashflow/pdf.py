import shutil
import subprocess
from pathlib import Path

import pdfplumber


def pdf_to_text(path: Path) -> str:
    """Return the text of a PDF with fixed-width column layout preserved.

    Uses pdfplumber's layout mode, falling back to Ghostscript's txtwrite device
    if pdfplumber fails or finds no text.
    """
    try:
        text = _pdfplumber_text(path)
    except Exception:
        text = ""
    if text.strip():
        return text
    return _ghostscript_text(path)


def _pdfplumber_text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text(layout=True) for page in pdf.pages)


def _ghostscript_text(path: Path) -> str:
    gs = shutil.which("gs")
    if gs is None:
        raise RuntimeError(f"could not extract text from {path}: pdfplumber failed and Ghostscript (gs) is not installed")
    result = subprocess.run(
        [gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=txtwrite", "-sOutputFile=-", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout
