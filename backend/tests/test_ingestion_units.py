"""Tests for PDF reading, legal chunking, citations and the admin guard.
These use no ChromaDB or embedding model, so they always run."""

import pytest

from app.dependencies import is_trusted_host
from app.services.citation_service import build_citation
from app.utils.legal_chunker import chunk_pages
from app.utils.pdf_utils import PageText, PdfError, extract_pages, text_quality_warnings, validate_pdf
from app.utils.text_utils import tokenize, topics_for
from tests.pdf_factory import SAMPLE_ACT_PAGES, make_pdf

MB = 1024 * 1024


# ---------- PDF validation and extraction ----------


def test_validate_pdf_accepts_real_pdf():
    assert validate_pdf(make_pdf(SAMPLE_ACT_PAGES), 50 * MB) == 3


@pytest.mark.parametrize(
    "data, message",
    [
        (b"", "empty"),
        (b"hello, not a pdf", "not a PDF"),
        (b"%PDF-1.4 broken", "could not be opened"),
    ],
)
def test_validate_pdf_rejects_bad_files(data, message):
    with pytest.raises(PdfError, match=message):
        validate_pdf(data, 50 * MB)


def test_validate_pdf_rejects_too_large():
    with pytest.raises(PdfError, match="larger than"):
        validate_pdf(make_pdf(SAMPLE_ACT_PAGES), 100)


def test_extract_pages_keeps_page_numbers(tmp_path):
    path = tmp_path / "act.pdf"
    path.write_bytes(make_pdf(SAMPLE_ACT_PAGES))
    pages = extract_pages(str(path))
    assert [p.page_number for p in pages] == [1, 2, 3]
    assert "CHAPTER II" in pages[2].text
    assert "ninety days" in pages[2].text


def test_quality_warnings():
    assert text_quality_warnings([PageText(1, ""), PageText(2, " ")], "en")[0].startswith("No readable text")
    garbage_tamil = [PageText(1, "ÜÁ¸ ¦ºÂø ÜÁ¸ ¦ºÂø " * 20)]
    assert any("non-Unicode Tamil" in w for w in text_quality_warnings(garbage_tamil, "ta"))
    real_tamil = [PageText(1, "கூட்டுறவு சங்கம் பதிவு செய்யப்பட வேண்டும் " * 5)]
    assert text_quality_warnings(real_tamil, "ta") == []


# ---------- structure-aware chunking ----------


def _sample_chunks(tmp_path, **kwargs):
    path = tmp_path / "act.pdf"
    path.write_bytes(make_pdf(SAMPLE_ACT_PAGES))
    return chunk_pages(extract_pages(str(path)), **kwargs)


def test_chunks_follow_sections_and_chapters(tmp_path):
    chunks = _sample_chunks(tmp_path)
    by_section = {c.section: c for c in chunks if c.section}
    assert set(by_section) == {"1", "2", "3", "4"}

    assert by_section["2"].chapter == "I"
    assert by_section["2"].section_title == "Definitions"
    assert "quorum means" in by_section["2"].text
    assert by_section["2"].page_start == 2

    assert by_section["3"].chapter == "II"
    assert by_section["3"].section_title == "Registration of societies"
    assert by_section["3"].subsection == "1"
    assert by_section["3"].page_start == 3
    assert "Section 3 — Registration of societies" in by_section["3"].embed_text


def test_table_of_contents_is_dropped(tmp_path):
    chunks = _sample_chunks(tmp_path)
    # Each section appears once, from its real page, not from the contents list on page 1.
    assert all(c.page_start > 1 for c in chunks if c.section)


def test_long_section_is_split_with_overlap():
    lines = ["CHAPTER III", "5. Audit.-(1) The accounts shall be audited every year by an auditor."]
    for n in range(2, 12):
        lines.append(f"({n}) " + f"The auditor shall examine rule number {n} carefully and report. " * 4)
    chunks = chunk_pages([PageText(7, "\n".join(lines))], max_chars=500, overlap_chars=100)
    section5 = [c for c in chunks if c.section == "5"]

    assert len(section5) > 2
    assert all(len(c.text) <= 500 + 110 for c in section5)  # max size + overlap
    assert all(c.chapter == "III" and c.page_start == 7 for c in section5)
    assert section5[1].text.startswith("…")  # starts with the tail of the previous chunk
    assert section5[1].subsection not in (None, "1")


def test_unstructured_text_falls_back_to_paragraphs():
    text = "This scheme provides interest subsidy to farmers.\n\nEligible farmers apply at the society office."
    chunks = chunk_pages([PageText(1, text)])
    assert len(chunks) == 1
    assert chunks[0].section is None
    assert chunks[0].page_start == 1


def test_tamil_sections_are_detected():
    text = "அத்தியாயம் 2\nபிரிவு 10 உறுப்பினர் சேர்க்கை\n(1) தகுதியுள்ள எந்த நபரும் சங்கத்தின் உறுப்பினராக சேர்க்கப்படலாம்."
    chunks = chunk_pages([PageText(4, text)])
    assert chunks[0].chapter == "2"
    assert chunks[0].section == "10"
    assert chunks[0].page_start == 4


# ---------- text helpers ----------


def test_tokenize_keeps_tamil_words_whole():
    assert "உறுப்பினர்" in tokenize("உறுப்பினர் சேர்க்கை")
    assert "quorum" in tokenize("What is the quorum?")
    assert "what" not in tokenize("What is the quorum?")


def test_topics():
    assert set(topics_for("The auditor shall audit the accounts")) >= {"auditing"}
    assert "elections" in topics_for("தேர்தல் நடத்துதல்")
    assert topics_for("Short title and extent") == []


# ---------- citations ----------


def test_citation_label_english_and_tamil():
    metadata = {
        "citation_name": "TN Co-operative Societies Act, 1983",
        "document_title": "Tamil Nadu Co-operative Societies Act, 1983",
        "document_id": "tn-act-1983-abcd1234",
        "doc_type": "act",
        "section": "34",
        "subsection": "2",
        "page_start": 18,
        "page_end": 18,
    }
    citation = build_citation(1, metadata, "en")
    assert citation["label"] == "[1] TN Co-operative Societies Act, 1983, Section 34(2), Page 18"
    assert citation["page"] == 18

    tamil = build_citation(2, {**metadata, "page_end": 19}, "ta")
    assert tamil["label"] == "[2] TN Co-operative Societies Act, 1983, பிரிவு 34(2), பக்கங்கள் 18–19"


def test_citation_uses_rule_for_rules_documents():
    citation = build_citation(1, {"citation_name": "TN Rules 1988", "doc_type": "rules", "section": "5", "page_start": 3})
    assert citation["label"] == "[1] TN Rules 1988, Rule 5, Page 3"


# ---------- admin guard (Decision 30) ----------


def test_trusted_hosts():
    assert is_trusted_host("127.0.0.1", allow_lan=False)
    assert is_trusted_host("::1", allow_lan=False)
    assert not is_trusted_host("192.168.1.20", allow_lan=False)
    assert is_trusted_host("192.168.1.20", allow_lan=True)
    assert not is_trusted_host("8.8.8.8", allow_lan=True)
    assert not is_trusted_host("testclient", allow_lan=True)
    assert not is_trusted_host(None, allow_lan=True)


# ---------- formats found in the real Tamil Nadu PDFs ----------


def test_real_world_section_formats():
    text = "\n".join(
        [
            "CHAPTER IV.",
            "33. Constitution of board.__ (1) The board shall consist of elected members. " + "x " * 60,
            "28[33-A. Tamil Nadu State Co-operative Societies Election Commission.—(1) The Government shall",
            "constitute an Election Commission. " + "y " * 60,
            "34. Disqualification.-- No person shall be a member of the board if he is a defaulter. " + "z " * 60,
        ]
    )
    chunks = chunk_pages([PageText(45, text)])
    sections = [(c.section, c.section_title) for c in chunks]
    assert ("33", "Constitution of board") in sections
    assert ("33-A", "Tamil Nadu State Co-operative Societies Election Commission") in sections
    assert ("34", "Disqualification") in sections
    assert [c.subsection for c in chunks if c.section == "33-A"][0] == "1"


def test_footnotes_are_skipped_until_next_chapter():
    page1 = "\n".join(
        [
            "CHAPTER I",
            "1. Short title.-(1) This Act may be called the Sample Act. " + "a " * 60,
            "2. Definitions.-In this Act, words have their usual meaning. " + "b " * 60,
            "Foot Note :",
            "1. Substituted by T.N. Act 4 of 2013, pub. in T.N.G. Gaz.",
            "2. Inserted by T.N. Act 4 of 2013.",
        ]
    )
    page2 = "CHAPTER II\n3. The Registrar.-(1) The Government may appoint a Registrar. " + "c " * 60
    chunks = chunk_pages([PageText(1, page1), PageText(2, page2)])
    assert [c.section for c in chunks if c.section] == ["1", "2", "3"]
    assert not any("Substituted by" in c.text for c in chunks)


def test_contents_page_with_page_numbers_is_skipped():
    toc = "\n".join(["ARRANGEMENT OF SECTIONS"] + [f"{n}. Title of section {n} {n + 4}" for n in range(1, 30)])
    body = "1. Short title.-(1) This Act may be called the Sample Act. " + "a " * 80
    chunks = chunk_pages([PageText(2, toc), PageText(15, body)])
    assert [(c.section, c.page_start) for c in chunks] == [("1", 15)]


def test_numbered_table_inside_a_rule_is_not_a_new_rule():
    text = "\n".join(
        [
            "145. Qualifications of Managing Directors - No person shall be eligible unless qualified. " + "q " * 40,
            "THE TABLE",
            "1. The Tamil Nadu State Co-operative Bank Limited, Chennai.",
            "2. The Tamil Nadu Co-operative Union Ltd, Chennai.",
            "146. Powers of Managing Director.- The Managing Director shall manage the society. " + "m " * 40,
        ]
    )
    chunks = chunk_pages([PageText(175, text)])
    assert [c.section for c in chunks] == ["145", "146"]
    assert "State Co-operative Bank" in chunks[0].text


def test_section_key_normalises_lettered_sections():
    from app.utils.legal_chunker import section_key

    assert section_key("33-A") == section_key("33a") == section_key("33A") == "33A"
    assert section_key(None) is None


# ---------- ranking helpers ----------


def test_light_stemming_matches_word_forms():
    assert tokenize("audits audited auditing")[0] == tokenize("audit")[0] == "audit"
    assert tokenize("committees") == tokenize("committee") == ["committee"]
    assert tokenize("members") == tokenize("member")
    assert tokenize("உறுப்பினர்கள்") == ["உறுப்பினர்கள்"]  # Tamil left unchanged


def test_jurisdiction_hint():
    from app.services.retrieval_service import _jurisdiction_hint

    assert _jurisdiction_hint("How do I register a society in Tamil Nadu?") == "tamil_nadu"
    assert _jurisdiction_hint("தமிழ்நாட்டில் சங்கம் பதிவு") == "tamil_nadu"
    assert _jurisdiction_hint("multi-state cooperative society registration") == "central"
    assert _jurisdiction_hint("How do I register a society?") is None
    assert _jurisdiction_hint("Tamil Nadu and multi-state societies") is None  # both: no preference


def test_front_matter_and_bare_chapter_headings_are_dropped():
    cover = "THE SAMPLE ACT\nPublished by the Government Press\nPrice Rs. 10"
    body = "\n".join(
        [
            "An Act to consolidate the law relating to co-operative societies.",
            "CHAPTER I",
            "PRELIMINARY",
            "1. Short title.-(1) This Act may be called the Sample Act. " + "a " * 80,
        ]
    )
    chunks = chunk_pages([PageText(1, cover), PageText(5, body)])
    assert not any("Government Press" in c.text for c in chunks)  # cover page dropped
    assert any("An Act to consolidate" in c.text for c in chunks)  # preamble kept
    assert not any(c.section is None and c.text.strip() == "PRELIMINARY" for c in chunks)
