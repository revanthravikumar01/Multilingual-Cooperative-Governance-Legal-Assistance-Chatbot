"""Text helpers shared by ingestion and retrieval: tokens, topics, slugs."""

import re

# Letters/digits plus the whole Tamil block (Tamil vowel signs are not "word" characters in Python).
_TOKEN = re.compile(r"[\w஀-௿]+")

_STOPWORDS = {
    "the", "and", "for", "are", "what", "which", "who", "how", "can", "does", "with", "that",
    "this", "from", "into", "under", "about", "any", "all", "its", "has", "have", "was", "were",
    "will", "shall", "may", "been", "being", "their", "there", "where", "when", "why", "not",
    "per", "such", "other", "than", "then", "also", "should", "would", "could", "tell",
    "explain", "please", "society", "societies", "cooperative", "co", "operative",
}

# Keywords for metadata filters (Decision 8). A chunk is tagged with a topic if any keyword appears.
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "registration": ["registration", "register a society", "registered", "bye-law", "byelaw", "பதிவு"],
    "membership": ["member", "membership", "admission", "expulsion", "shareholder", "உறுப்பினர்"],
    "elections": ["election", "elected", "vote", "voting", "ballot", "polling", "தேர்தல்", "வாக்கு"],
    "governance": [
        "board", "general body", "general meeting", "quorum", "committee", "director",
        "president", "management", "பொதுக்குழு", "கூட்டம்", "இயக்குநர்", "நிர்வாக",
    ],
    "auditing": ["audit", "auditor", "accounts", "balance sheet", "தணிக்கை", "கணக்கு"],
    "schemes": ["scheme", "subsidy", "assistance", "loan", "grant", "திட்டம்", "மானியம்", "கடன்"],
}


def _stem(token: str) -> str:
    """Very light English word-ending removal, so "audits", "audited" and "audit" match.
    Tamil words are left unchanged."""
    if not token.isascii() or len(token) <= 4:
        return token
    for suffix, replacement in (("ies", "y"), ("ing", ""), ("ed", ""), ("s", "")):
        if token.endswith(suffix) and not token.endswith("ss") and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)] + replacement
    return token


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if len(t) > 2 and t not in _STOPWORDS]


def topics_for(text: str) -> list[str]:
    lowered = text.lower()
    return [topic for topic, words in TOPIC_KEYWORDS.items() if any(w in lowered for w in words)]


def slugify(text: str, max_length: int = 50) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_length].strip("-") or "document"


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
