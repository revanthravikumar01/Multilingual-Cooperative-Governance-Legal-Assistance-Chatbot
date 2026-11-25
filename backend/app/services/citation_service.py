"""Builds citations from stored chunk metadata (Decision 10).

Citations are made only from what the PDF upload recorded, never by Gemini,
so a citation can never point to a section or page that doesn't exist.
"""

_WORDS = {
    "en": {"section": "Section", "rule": "Rule", "page": "Page", "pages": "Pages"},
    "ta": {"section": "பிரிவு", "rule": "விதி", "page": "பக்கம்", "pages": "பக்கங்கள்"},
}


def build_citation(number: int, metadata: dict, language: str = "en") -> dict:
    words = _WORDS.get(language, _WORDS["en"])
    name = metadata.get("citation_name") or metadata.get("document_title", "Unknown document")
    parts = [f"[{number}] {name}"]

    section = metadata.get("section")
    if section:
        word = words["rule"] if metadata.get("doc_type") == "rules" else words["section"]
        subsection = metadata.get("subsection")
        parts.append(f"{word} {section}" + (f"({subsection})" if subsection else ""))

    page_start, page_end = metadata.get("page_start"), metadata.get("page_end")
    if page_start:
        if page_end and page_end != page_start:
            parts.append(f"{words['pages']} {page_start}–{page_end}")
        else:
            parts.append(f"{words['page']} {page_start}")

    return {
        "number": number,
        "label": ", ".join(parts),
        "document_id": metadata.get("document_id", ""),
        "document_title": metadata.get("document_title", ""),
        "issuing_authority": metadata.get("issuing_authority"),
        "chapter": metadata.get("chapter"),
        "section": section,
        "subsection": metadata.get("subsection"),
        "page": page_start,
        "published_on": metadata.get("published_on"),
    }
