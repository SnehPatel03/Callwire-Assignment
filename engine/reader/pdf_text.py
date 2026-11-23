"""Stage 2: PDF bytes -> clean transcript text, plus quarter / call-date detection."""
import collections
import re

import pymupdf

# A line like "Moderator:" or "Rahul Sharma:" - a speaker turn, never boilerplate.
_SPEAKER = re.compile(r"^[A-Za-z .]{2,40}:")
_BARE_PAGE_NO = re.compile(r"(page\s*)?\d+(\s*(of|/)\s*\d+)?", re.I)


def read_pdf(pdf: bytes, ocr: bool = True) -> str:
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    pages = []
    for page in doc:
        text = page.get_text("text", sort=True)  # sort=True helps multi-column reading order
        if len(text.strip()) < 30 and ocr:       # image-only page -> OCR fallback (needs Tesseract)
            try:
                text = page.get_textpage_ocr(full=True).extractText()
            except Exception:
                text = ""
        pages.append(text)
    return tidy(pages)


def tidy(pages: list[str]) -> str:
    """Drop repeated headers/footers and page numbers, re-join wrapped lines, space out speakers."""
    per_page = [[ln.strip() for ln in p.splitlines() if ln.strip()] for p in pages]
    n_pages = len(pages)

    def shape(line: str) -> str:
        return re.sub(r"\d+", "#", line)  # "Page 3" and "Page 4" look identical

    # Short non-speaker lines that recur on >=40% of pages are headers/footers.
    counts = collections.Counter(
        key
        for lines in per_page
        for key in {shape(ln) for ln in lines if len(ln) < 90 and not _SPEAKER.match(ln)}
    )
    boilerplate = {k for k, v in counts.items() if n_pages >= 4 and v >= 0.4 * n_pages}

    kept = []
    for lines in per_page:
        for ln in lines:
            is_header = len(ln) < 90 and not _SPEAKER.match(ln) and shape(ln) in boilerplate
            if is_header or _BARE_PAGE_NO.fullmatch(ln):
                continue
            kept.append(ln)

    text = "\n".join(kept)
    text = re.sub(r"(?<=[a-z,])\n(?=[a-z])", " ", text)  # re-join wrapped lines
    text = re.sub(r"\n(?=(Moderator|Management|[A-Z][a-z]+ [A-Z][a-z]+)\s*:)", "\n\n", text)  # speaker turns
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def find_quarter(text: str):
    m = re.search(r"\bQ([1-4])\s*[-']?\s*FY\s*['-]?\s*(\d{2,4})", text, re.I)
    if m:
        return f"Q{m.group(1)} FY{m.group(2)[-2:]}"
    m = re.search(r"(first|second|third|fourth) quarter.{0,40}?(?:FY|financial year)\s*(?:20)?(\d{2})", text, re.I | re.S)
    if m:
        n = ["first", "second", "third", "fourth"].index(m.group(1).lower()) + 1
        return f"Q{n} FY{m.group(2)}"
    return None


_MONTH_NAMES = "january february march april may june july august september october november december".split()


def find_call_date(text: str):
    """First 'DD Month YYYY' / 'Month DD, YYYY' in the opening of the transcript -> ISO date."""
    head = text[:4000]
    mon = "|".join(m.capitalize() for m in _MONTH_NAMES) + "|" + "|".join(m[:3].capitalize() for m in _MONTH_NAMES)
    hits = []
    for m in re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s,.\-]+({mon})[a-z]*\.?[\s,.\-]+(\d{{4}})", head):
        hits.append((m.start(), m.group(3), m.group(2), m.group(1)))
    for m in re.finditer(rf"\b({mon})[a-z]*\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", head):
        hits.append((m.start(), m.group(3), m.group(1), m.group(2)))
    for _, year, month, day in sorted(hits):
        month_no = [x[:3] for x in _MONTH_NAMES].index(month[:3].lower()) + 1
        if 1 <= int(day) <= 31:
            return f"{year}-{month_no:02d}-{int(day):02d}"
    return None
