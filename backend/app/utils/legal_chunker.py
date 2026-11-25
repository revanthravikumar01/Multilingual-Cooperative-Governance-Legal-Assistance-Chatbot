"""Structure-aware chunking for legal documents (Decision 7).

Acts and Rules are organised as Chapter -> Section/Rule -> Sub-section (1), (2) -> clause (a), (b).
Instead of cutting text every N characters, we:

1. Walk the text line by line, noticing where each Chapter and Section starts.
2. Group the lines of one section together (a "unit").
3. Split long sections into chunks of about `max_chars`, only at sub-section, clause or
   paragraph boundaries, with a small overlap so a sentence is never cut off from its context.

Every chunk remembers its chapter, section, sub-section and page numbers, which is what
the citations are built from later. Documents with no recognisable structure (e.g. some
scheme guidelines) fall back to plain paragraph chunks with page numbers only.
"""

import re
from dataclasses import dataclass, field

from app.utils.pdf_utils import PageText

# "CHAPTER II", "Chapter 3 - Members", Tamil "அத்தியாயம் 2"
_CHAPTER = re.compile(
    r"^\s*(?:CHAPTER|Chapter|அத்தியாயம்|இயல்)\s*[-–—:]?\s*([IVXLCDM]+[A-Z]?|\d{1,3}[A-Z]?)\b[.:\-–—]?\s*(.*)$"
)
# A section number: "34", "34A", "33-A". Amended text may start with a footnote marker: "28[33-A."
_NUMBER = r"(\d{1,3}(?:-?[A-Z]{1,2})?)"
_MARKER = r"(?:\d{1,3}\s*\[\s*)?"
# "Section 34. Title", "Rule 5 - Title", Tamil "பிரிவு 34", "விதி 5"
_SECTION_WORD = re.compile(
    rf"^\s*{_MARKER}(?:SECTION|Section|RULE|Rule|பிரிவு|விதி)\s+{_NUMBER}\b[.:\-–—]?\s*(.*)$"
)
# Indian Acts/Rules style: "34. Admission of members.—(1) ..." or "28[33-A. Election Commission.—"
_SECTION_NUM = re.compile(rf"^\s*{_MARKER}{_NUMBER}\.\s+(\S.*)$")
# Sub-section at the start of a line, or right after the heading dash: "(1)", "(2A)"
_SUBSECTION = re.compile(r"^\s*\((\d{1,3}[A-Z]?)\)\s")
_SUBSECTION_INLINE = re.compile(r"(?:[—–]|-{1,2}|_{2,})\s*\((\d{1,3}[A-Z]?)\)\s")
# Clause "(a)", "(iv)": a good place to split, but not tracked for citations
_CLAUSE = re.compile(r"^\s*\(([a-z]{1,4})\)\s")
# Where a section title ends: ".—", ".--", ".__", "—", ":" or ". "
_TITLE_END = re.compile(r"\.\s*(?:[—–]|-{1,2}|_{2,})|[—–]|_{2,}|:|\.\s|\.$")
# Amendment footnotes at the end of a chapter ("Foot Note :", "Footnote:"). Not legal text.
_FOOTNOTE_HEADING = re.compile(r"^\s*foot\s*-?\s*notes?\s*[:.]?\s*$", re.IGNORECASE)
# Forms, schedules and appendices after the last rule: numbered lines there are not sections.
_APPENDIX = re.compile(r"^\s*(FORM|APPENDIX|SCHEDULE|ANNEXURE)\b[\s\-–—.:]*([A-Z0-9-]{0,8})\s*$")
# Table-of-contents pages: titles such as "ARRANGEMENT OF SECTIONS" or "Contents".
_TOC_TITLE = re.compile(r"arrangement of (sections|rules)|^\s*c\s*o?\s*n\s*tents\b|table of contents", re.IGNORECASE)
# A section can't jump forward by more than this (repealed sections leave small gaps).
_MAX_SECTION_JUMP = 25


def section_key(number: str | None) -> str | None:
    """Normalised section number for matching: "33-A", "33a" and "33A" all become "33A"."""
    return number.replace("-", "").upper() if number else None


def _section_value(number: str) -> int:
    return int(re.match(r"\d+", number).group())


def _is_toc_page(text: str) -> bool:
    """A contents page lists many section titles with little text between them."""
    lines = [l for l in text.splitlines() if l.strip()]
    headings = sum(1 for l in lines if _SECTION_NUM.match(l.strip()))
    if _TOC_TITLE.search(text) and headings >= 3:
        return True
    return headings >= 8 and len(text) / headings < 160


@dataclass
class Chunk:
    text: str  # the passage itself (shown to Gemini as evidence)
    embed_text: str  # header + passage (what gets embedded, so the section title helps search)
    chunk_index: int
    page_start: int
    page_end: int
    chapter: str | None = None
    section: str | None = None
    section_title: str | None = None
    subsection: str | None = None

    @property
    def header(self) -> str:
        parts = []
        if self.chapter:
            parts.append(f"Chapter {self.chapter}")
        if self.section:
            parts.append(f"Section {self.section}" + (f" — {self.section_title}" if self.section_title else ""))
        return " · ".join(parts)


@dataclass
class _Piece:
    """A paragraph-sized bit of text from one place in the document."""

    text: str
    page: int
    subsection: str | None


@dataclass
class _Unit:
    """All text belonging to one section (or the text before the first section)."""

    chapter: str | None
    section: str | None
    section_title: str | None
    pieces: list[_Piece] = field(default_factory=list)

    def length(self) -> int:
        return sum(len(p.text) for p in self.pieces)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _title_from(rest: str) -> str | None:
    rest = rest.strip()
    if not rest or rest.startswith("("):
        return None
    match = _TITLE_END.search(rest)
    title = rest[: match.start()] if match else rest
    title = title.strip(" .[]")
    return title[:150] or None


def _build_units(pages: list[PageText]) -> list[_Unit]:
    units: list[_Unit] = [_Unit(chapter=None, section=None, section_title=None)]
    chapter: str | None = None
    subsection: str | None = None
    last_section: str | None = None
    skipping_footnotes = False  # inside a chapter's amendment footnotes
    in_appendix = False  # inside forms/schedules after the last section
    buffer: list[str] = []
    buffer_page = 1

    def flush() -> None:
        nonlocal buffer
        text = _clean(" ".join(buffer))
        if text:
            units[-1].pieces.append(_Piece(text=text, page=buffer_page, subsection=subsection))
        buffer = []

    def plausible_next(number: str) -> bool:
        """Section numbers only move forward. This rejects numbered lists inside a section."""
        if last_section is None:
            return True
        new, old = _section_value(number), _section_value(last_section)
        return old <= new <= old + _MAX_SECTION_JUMP and section_key(number) != section_key(last_section)

    for page in pages:
        flush()  # never let a paragraph carry over a page break, so page numbers stay exact
        if _is_toc_page(page.text):
            continue
        for raw_line in page.text.splitlines():
            line = raw_line.strip()
            if not line:
                flush()
                continue

            if _FOOTNOTE_HEADING.match(line):
                flush()
                skipping_footnotes = True
                continue

            chapter_match = _CHAPTER.match(line)
            if chapter_match:
                flush()
                skipping_footnotes = in_appendix = False
                chapter = chapter_match.group(1)
                subsection = None
                units.append(_Unit(chapter=chapter, section=None, section_title=_clean(chapter_match.group(2)) or None))
                buffer_page = page.page_number
                continue

            if skipping_footnotes:
                continue

            appendix_match = _APPENDIX.match(line)
            if appendix_match:
                flush()
                in_appendix = True
                subsection = None
                units.append(_Unit(chapter=None, section=None, section_title=_clean(line).title()))
                buffer_page = page.page_number
                continue

            section_match = None if in_appendix else (_SECTION_WORD.match(line) or _SECTION_NUM.match(line))
            if section_match and plausible_next(section_match.group(1)):
                flush()
                number, rest = section_match.group(1), section_match.group(2)
                inline = _SUBSECTION_INLINE.search(rest)
                subsection = inline.group(1) if inline else None
                units.append(_Unit(chapter=chapter, section=number, section_title=_title_from(rest)))
                last_section = number
                buffer = [line]
                buffer_page = page.page_number
                continue

            sub_match = _SUBSECTION.match(line)
            if sub_match or _CLAUSE.match(line):
                flush()
                if sub_match:
                    subsection = sub_match.group(1)
                buffer_page = page.page_number

            if not buffer:
                buffer_page = page.page_number
            buffer.append(line)
    flush()

    # Front matter (cover page, leftover contents lines) is noise. Keep only the text on the
    # page where the body starts, which holds the preamble ("An Act to consolidate ...").
    if len(units) > 1 and units[1].pieces:
        body_start = units[1].pieces[0].page
        units[0].pieces = [p for p in units[0].pieces if p.page >= body_start]

    # A chapter heading on its own ("CHAPTER II / REGISTRATION") is not useful evidence.
    units = [u for u in units if u.section or u.chapter is None or u.length() >= 200]

    # Safety net for contents pages that slipped through: drop tiny units whose section
    # number appears again later with real text.
    seen_long = {section_key(u.section) for u in units if u.section and u.length() >= 150}
    units = [u for u in units if not (u.section and u.length() < 150 and section_key(u.section) in seen_long)]
    return [u for u in units if u.pieces]


def _split_long_piece(piece: _Piece, max_chars: int) -> list[_Piece]:
    """Split one very long paragraph at sentence (or word) boundaries."""
    if len(piece.text) <= max_chars:
        return [piece]
    sentences = re.split(r"(?<=[.;:])\s+", piece.text)
    out: list[_Piece] = []
    current = ""
    for sentence in sentences:
        while len(sentence) > max_chars:  # a single enormous sentence: cut at a space
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            if current:
                out.append(_Piece(current, piece.page, piece.subsection))
                current = ""
            out.append(_Piece(sentence[:cut].strip(), piece.page, piece.subsection))
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > max_chars:
            out.append(_Piece(current, piece.page, piece.subsection))
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        out.append(_Piece(current, piece.page, piece.subsection))
    return out


def chunk_pages(pages: list[PageText], max_chars: int = 1200, overlap_chars: int = 200) -> list[Chunk]:
    chunks: list[Chunk] = []
    for unit in _build_units(pages):
        pieces = [p for piece in unit.pieces for p in _split_long_piece(piece, max_chars)]
        group: list[_Piece] = []
        carry: _Piece | None = None  # overlap copied from the end of the previous chunk

        def emit() -> None:
            nonlocal group, carry
            if not group:
                return
            body_pieces = ([carry] if carry else []) + group
            text = "\n".join(p.text for p in body_pieces)
            chunk = Chunk(
                text=text,
                embed_text="",
                chunk_index=len(chunks),
                page_start=group[0].page,
                page_end=group[-1].page,
                chapter=unit.chapter,
                section=unit.section,
                section_title=unit.section_title,
                subsection=next((p.subsection for p in group if p.subsection), None),
            )
            chunk.embed_text = f"{chunk.header}\n{text}" if chunk.header else text
            chunks.append(chunk)
            # Overlap: carry the tail of the last piece into the next chunk.
            tail = group[-1].text[-overlap_chars:] if overlap_chars else ""
            if tail and len(group[-1].text) > overlap_chars:
                cut = tail.find(" ")
                tail = tail[cut + 1 :] if cut >= 0 else tail
            carry = _Piece("…" + tail, group[-1].page, group[-1].subsection) if tail else None
            group = []

        size = 0
        for piece in pieces:
            if group and size + len(piece.text) > max_chars:
                emit()
                size = len(carry.text) if carry else 0
            group.append(piece)
            size += len(piece.text) + 1
        emit()

    # Drop scraps (stray page numbers, headers) that carry no meaning.
    kept = [c for c in chunks if len(c.text) >= 30]
    for index, chunk in enumerate(kept):
        chunk.chunk_index = index
    return kept
