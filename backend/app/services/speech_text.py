"""Turns a written answer into text a voice can read aloud (Phase 4).

The voices garble digits and symbols ("34(2)" was read as "342" in testing), so before speaking:
  - source markers [1] / [1, 2] are removed (the sources are shown on screen),
  - list dashes, "**" and "#" are removed,
  - "Section 34(2)(a)" -> "Section thirty-four, sub-section two, clause a",
  - "Rs. 500" / "₹500" -> "five hundred rupees", "5%" -> "five per cent",
  - every other number is written as words, in English or Tamil.
"""

import re

# ---------- English numbers ----------

_EN_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
            "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def english_number(n: int) -> str:
    """Indian-style English: 150000 -> "one lakh fifty thousand"."""
    if n < 0:
        return "minus " + english_number(-n)
    if n < 20:
        return _EN_ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _EN_TENS[tens] + (f"-{_EN_ONES[ones]}" if ones else "")
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return f"{_EN_ONES[hundreds]} hundred" + (f" and {english_number(rest)}" if rest else "")
    for size, word in ((10_000_000, "crore"), (100_000, "lakh"), (1000, "thousand")):
        if n >= size:
            big, rest = divmod(n, size)
            text = f"{english_number(big)} {word}"
            if rest:
                text += (" and " if rest < 100 else " ") + english_number(rest)
            return text
    return str(n)


def english_year(n: int) -> str:
    """1983 -> "nineteen eighty-three", 2002 -> "two thousand and two"."""
    if 2000 <= n <= 2009:
        return english_number(n)
    high, low = divmod(n, 100)
    if low == 0:
        return f"{english_number(high)} hundred"
    return f"{english_number(high)} {'oh ' + _EN_ONES[low] if low < 10 else english_number(low)}"


# ---------- Tamil numbers ----------

_TA_ONES = ["பூஜ்ஜியம்", "ஒன்று", "இரண்டு", "மூன்று", "நான்கு", "ஐந்து", "ஆறு", "ஏழு", "எட்டு", "ஒன்பது"]
_TA_TEENS = ["பத்து", "பதினொன்று", "பன்னிரண்டு", "பதின்மூன்று", "பதினான்கு", "பதினைந்து", "பதினாறு",
             "பதினேழு", "பதினெட்டு", "பத்தொன்பது"]
_TA_TENS = ["", "பத்து", "இருபது", "முப்பது", "நாற்பது", "ஐம்பது", "அறுபது", "எழுபது", "எண்பது", "தொண்ணூறு"]
_TA_TENS_JOIN = ["", "", "இருபத்து", "முப்பத்து", "நாற்பத்து", "ஐம்பத்து", "அறுபத்து", "எழுபத்து", "எண்பத்து",
                 "தொண்ணூற்று"]
_TA_HUNDREDS = ["", "நூறு", "இருநூறு", "முந்நூறு", "நானூறு", "ஐந்நூறு", "அறுநூறு", "எழுநூறு", "எண்ணூறு",
                "தொள்ளாயிரம்"]
_TA_HUNDREDS_JOIN = ["", "நூற்று", "இருநூற்று", "முந்நூற்று", "நானூற்று", "ஐந்நூற்று", "அறுநூற்று", "எழுநூற்று",
                     "எண்ணூற்று", "தொள்ளாயிரத்து"]
_TA_THOUSANDS = ["", "ஆயிரம்", "இரண்டாயிரம்", "மூன்றாயிரம்", "நான்காயிரம்", "ஐந்தாயிரம்", "ஆறாயிரம்",
                 "ஏழாயிரம்", "எட்டாயிரம்", "ஒன்பதாயிரம்", "பத்தாயிரம்"]
_TA_THOUSANDS_JOIN = ["", "ஆயிரத்து", "இரண்டாயிரத்து", "மூன்றாயிரத்து", "நான்காயிரத்து", "ஐந்தாயிரத்து",
                      "ஆறாயிரத்து", "ஏழாயிரத்து", "எட்டாயிரத்து", "ஒன்பதாயிரத்து", "பத்தாயிரத்து"]


def tamil_number(n: int) -> str:
    """34 -> "முப்பத்து நான்கு", 1983 -> "ஆயிரத்து தொள்ளாயிரத்து எண்பத்து மூன்று"."""
    if n < 0:
        return "கழித்தல் " + tamil_number(-n)
    if n < 10:
        return _TA_ONES[n]
    if n < 20:
        return _TA_TEENS[n - 10]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TA_TENS[tens] if not ones else f"{_TA_TENS_JOIN[tens]} {_TA_ONES[ones]}"
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return _TA_HUNDREDS[hundreds] if not rest else f"{_TA_HUNDREDS_JOIN[hundreds]} {tamil_number(rest)}"
    if n < 100_000:
        thousands, rest = divmod(n, 1000)
        if thousands <= 10:
            return _TA_THOUSANDS[thousands] if not rest else f"{_TA_THOUSANDS_JOIN[thousands]} {tamil_number(rest)}"
        head = f"{tamil_number(thousands)} ஆயிரம்"
        return head if not rest else f"{tamil_number(thousands)} ஆயிரத்து {tamil_number(rest)}"
    for size, word, join in ((10_000_000, "கோடி", "கோடியே"), (100_000, "லட்சம்", "லட்சத்து")):
        if n >= size:
            big, rest = divmod(n, size)
            head = "ஒரு" if big == 1 else tamil_number(big)  # "ஒரு லட்சம்", not "ஒன்று லட்சம்"
            return f"{head} {word}" if not rest else f"{head} {join} {tamil_number(rest)}"
    return str(n)


# ---------- text cleanup ----------

_WORDS = {
    "en": {"sub": "sub-section", "clause": "clause", "rupees": "rupees", "percent": "per cent", "point": "point",
           "and": "and", "eg": "for example", "ie": "that is"},
    "ta": {"sub": "உட்பிரிவு", "clause": "கூறு", "rupees": "ரூபாய்", "percent": "சதவீதம்", "point": "புள்ளி",
           "and": "மற்றும்", "eg": "எடுத்துக்காட்டாக", "ie": "அதாவது"},
}

_MARKER = re.compile(r"\s?\[\d{1,2}(?:\s*,\s*\d{1,2})*\]")
# 34, 33-A, 136-D, 20(2), 34(2)(a)  — a section-like reference (number, optional letter, brackets)
_SECTION_REF = re.compile(r"\b(\d{1,3})(?:-?([A-Z]{1,2}))?((?:\(\s*[0-9a-zA-Z]{1,4}\s*\))+)")
_LETTERED = re.compile(r"\b(\d{1,3})-([A-Z]{1,2})\b")
_RUPEES = re.compile(r"(?:Rs\.?|INR|₹|ரூ\.?)\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)
_PERCENT = re.compile(r"([\d,]+(?:\.\d+)?)\s*%")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def prepare_for_speech(text: str, language: str) -> str:
    words = _WORDS.get(language, _WORDS["en"])
    number = tamil_number if language == "ta" else english_number

    def say(raw: str, year_ok: bool = False) -> str:
        raw = raw.replace(",", "")
        if "." in raw:
            whole, frac = raw.split(".", 1)
            return f"{say(whole)} {words['point']} " + " ".join(number(int(d)) for d in frac)
        value = int(raw)
        if year_ok and language != "ta" and 1100 <= value <= 2099 and len(raw) == 4:
            return english_year(value)
        return number(value)

    text = _MARKER.sub("", text)
    text = re.sub(r"\*\*|__|`|^#+\s*", "", text, flags=re.MULTILINE)
    # Each list item / line becomes its own sentence.
    lines = [re.sub(r"^\s*(?:[-•*]|\d{1,2}[.)])\s+", "", line).strip() for line in text.splitlines()]
    text = " ".join(line if re.search(r"[.!?।:;]$", line) else line + "." for line in lines if line)

    text = re.sub(r"\be\.g\.", words["eg"], text, flags=re.IGNORECASE)
    text = re.sub(r"\bi\.e\.", words["ie"], text, flags=re.IGNORECASE)
    text = text.replace("&", f" {words['and']} ")

    def section(match: re.Match) -> str:
        parts = [say(match.group(1))]
        if match.group(2):
            parts[0] += " " + " ".join(match.group(2))
        for inner in re.findall(r"\(\s*([0-9a-zA-Z]{1,4})\s*\)", match.group(3)):
            if inner.isdigit():
                parts.append(f"{words['sub']} {say(inner)}")
            else:
                parts.append(f"{words['clause']} {inner}")
        return ", ".join(parts)

    text = _SECTION_REF.sub(section, text)
    text = _LETTERED.sub(lambda m: f"{say(m.group(1))} {' '.join(m.group(2))}", text)
    text = _RUPEES.sub(lambda m: f"{say(m.group(1))} {words['rupees']}", text)
    text = _PERCENT.sub(lambda m: f"{say(m.group(1))} {words['percent']}", text)
    text = _NUMBER.sub(lambda m: say(m.group(0), year_ok=True), text)

    text = re.sub(r"[()\[\]{}\"“”*_#|<>]", " ", text)
    text = re.sub(r"\s+([,.!?।])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()
