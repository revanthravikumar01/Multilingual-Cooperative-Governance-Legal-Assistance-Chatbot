"""Builds tiny text PDFs for tests, so tests don't depend on real government files."""


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[list[str]]) -> bytes:
    """Each page is a list of text lines (ASCII). Returns the bytes of a valid PDF."""
    objects: list[bytes] = []
    page_count = len(pages)
    # Object numbers: 1 catalog, 2 pages, 3 font, then (page, content) pairs.
    kids = " ".join(f"{4 + i * 2} 0 R" for i in range(page_count))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, lines in enumerate(pages):
        content_num = 5 + i * 2
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_num} 0 R >>".encode()
        )
        body = "BT /F1 10 Tf 40 760 Td 13 TL " + " ".join(f"({_escape(line)}) Tj T*" for line in lines) + " ET"
        stream = body.encode("latin-1")
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


# A small Act-like document: a table of contents, two chapters, sections with sub-sections.
SAMPLE_ACT_PAGES = [
    [
        "THE SAMPLE CO-OPERATIVE SOCIETIES ACT",
        "ARRANGEMENT OF SECTIONS",
        "1. Short title.",
        "2. Definitions.",
        "3. Registration of societies.",
        "4. Admission of members.",
    ],
    [
        "CHAPTER I",
        "PRELIMINARY",
        "1. Short title.-(1) This Act may be called the Sample Co-operative Societies Act.",
        "(2) It extends to the whole of the State.",
        "2. Definitions.-In this Act, unless the context otherwise requires,",
        "(a) quorum means the minimum number of members who must be present at a general meeting",
        "for its proceedings to be valid;",
        "(b) Registrar means the officer appointed to register co-operative societies.",
    ],
    [
        "CHAPTER II",
        "REGISTRATION",
        "3. Registration of societies.-(1) A society may be registered by applying to the Registrar",
        "with a copy of the proposed bye-laws and the signatures of at least twenty-five persons.",
        "(2) The Registrar shall dispose of the application within ninety days of its receipt.",
        "4. Admission of members.-(1) Any person eligible under the bye-laws may be admitted as a",
        "member of the society on payment of the share amount.",
        "(2) No person shall be admitted as a member of more than one credit society.",
    ],
]
