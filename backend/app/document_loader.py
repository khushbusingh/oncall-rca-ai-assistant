"""Load and chunk documents: PDF, DOCX, DOC, HTML, plain text, CSV, and best-effort for other text files."""
import re
from pathlib import Path
from typing import List, Tuple

from pypdf import PdfReader
from docx import Document as DocxDocument

# Extensions we can extract text from (ingest and upload use this).
SUPPORTED_EXTENSIONS = (
    ".pdf", ".docx", ".doc",
    ".txt", ".md", ".rst", ".log", ".json", ".xml", ".yaml", ".yml",
    ".html", ".htm",
    ".csv",
)


def extract_text_from_html(html_content: str) -> str:
    """Extract visible text from HTML (e.g. Confluence export saved as .doc)."""
    from html.parser import HTMLParser
    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.text = []
        def handle_data(self, data):
            t = data.strip()
            if t:
                self.text.append(t)
    parser = TextExtractor()
    try:
        parser.feed(html_content)
        return re.sub(r"\s+", " ", " ".join(parser.text)).strip()
    except Exception:
        return ""


def extract_text_from_pdf(file_path: str) -> str:
    """Extract raw text from PDF."""
    reader = PdfReader(file_path)
    parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def extract_text_from_docx(file_path: str) -> str:
    """Extract text from DOCX."""
    doc = DocxDocument(file_path)
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(parts)


def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> List[Tuple[str, int]]:
    """Split text into overlapping chunks. Returns list of (chunk, start_char_index)."""
    if not text or not text.strip():
        return []
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_words = words[start:end]
        chunk = " ".join(chunk_words)
        if chunk.strip():
            chunks.append((chunk, start))
        start += chunk_size - chunk_overlap
        if start >= len(words):
            break
    return chunks


def extract_text_plain(file_path: str) -> str:
    """Read file as UTF-8 text (for .txt, .md, .rst, .log, .json, .xml, .yaml, .csv, etc.)."""
    path = Path(file_path)
    return path.read_text(encoding="utf-8", errors="replace")


def extract_text_from_csv(file_path: str) -> str:
    """Read CSV as plain text (cells joined with spaces)."""
    path = Path(file_path)
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _try_as_plain_text(file_path: str) -> str:
    """Fallback: try reading any file as UTF-8. Returns empty if not usable text."""
    path = Path(file_path)
    raw = path.read_bytes()
    decoded = raw.decode("utf-8", errors="replace")
    # Reject if mostly non-printable (likely binary)
    printable = sum(1 for c in decoded if c.isprintable() or c in "\n\r\t")
    if len(decoded) > 0 and printable / len(decoded) < 0.7:
        return ""
    return decoded


def load_and_chunk_file(
    file_path: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> List[str]:
    """Load document and return list of text chunks. Supports PDF, DOCX, DOC, HTML, TXT, MD, CSV, etc."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    text = ""

    if suffix == ".pdf":
        text = extract_text_from_pdf(str(path))
    elif suffix == ".docx":
        text = extract_text_from_docx(str(path))
    elif suffix == ".doc":
        raw = path.read_bytes()
        decoded = raw.decode("utf-8", errors="ignore")
        if "<html" in decoded.lower() or "Content-Type: text/html" in decoded or decoded.lstrip().startswith("<!") or decoded.lstrip().startswith("Date:"):
            text = extract_text_from_html(decoded)
        else:
            try:
                text = extract_text_from_docx(str(path))
            except Exception:
                text = ""
        if not text or len(text.strip()) < 50:
            raise ValueError("Could not extract text from .doc (tried HTML and DOCX). Try exporting as .docx or .pdf.")
    elif suffix in (".html", ".htm"):
        text = extract_text_plain(str(path))
        text = extract_text_from_html(text)
    elif suffix == ".csv":
        text = extract_text_from_csv(str(path))
    elif suffix in (".txt", ".md", ".rst", ".log", ".json", ".xml", ".yaml", ".yml"):
        text = extract_text_plain(str(path))
    else:
        # Best-effort: try as plain text (e.g. .conf, .ini, .cfg, no extension)
        text = _try_as_plain_text(str(path))
        if not text or len(text.strip()) < 10:
            raise ValueError(f"Unsupported or binary file: {suffix or '(no extension)'}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}")

    if not text.strip():
        return []
    paired = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return [c[0] for c in paired]
