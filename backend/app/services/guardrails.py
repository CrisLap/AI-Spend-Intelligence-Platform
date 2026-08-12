from __future__ import annotations

import re

from app.services.i18n_strings import translate

# Real users of this platform write in Italian, so English-only patterns
# leave these guardrails almost entirely inactive against real traffic -
# every pattern below matches both languages.
_SENSITIVE_PATTERNS = [
    re.compile(
        r"password|credit.?card|ssn|social.?security|"
        r"carta\s+di\s+credito|codice\s+fiscale|numero\s+di\s+carta",
        re.IGNORECASE,
    ),
]

_TOPIC_BOUNDARY = re.compile(
    r"(how\s+to\s+(hack|exploit|crack|bypass)|"
    r"generate\s+(fake|fraudulent|illegal)|"
    r"instructions\s+for\s+(theft|fraud|illegal)|"
    r"come\s+(?:\w+\s+){0,3}(hackerare|violare|aggirare|bypassare)|"
    r"genera(?:re)?\s+(dati\s+)?(falsi|fraudolenti|illegali)|"
    r"istruzioni\s+per\s+(?:il\s+|la\s+|un\s+|una\s+)?(furto|frode|truffa|attivit[àa]\s+illegal[ei]))",
    re.IGNORECASE,
)

# A real card/SSN-like number pasted into the message should be blocked even
# if the user never types the word "credit card" - validate_input previously
# only checked for the topic words, not for an actual sensitive-looking
# number, so a pasted real card number sailed through untouched.
_CARD_NUMBER_RE = re.compile(r"\b(?:\d[ -]?){13,16}\d\b")


_STRINGS = {
    "en": {
        "sensitive": "Request contains sensitive information that cannot be processed.",
        "out_of_scope": "Request is outside the scope of spend intelligence.",
    },
    "it": {
        "sensitive": "La richiesta contiene informazioni sensibili che non possono essere elaborate.",
        "out_of_scope": "La richiesta esula dall'ambito della spend intelligence.",
    },
}


def validate_input(text: str, lang: str = "en") -> str | None:
    for pat in _SENSITIVE_PATTERNS:
        if pat.search(text):
            return translate(_STRINGS, lang, "sensitive")
    if _CARD_NUMBER_RE.search(text):
        return translate(_STRINGS, lang, "sensitive")
    if _TOPIC_BOUNDARY.search(text):
        return translate(_STRINGS, lang, "out_of_scope")
    return None


def sanitize_output(text: str) -> str:
    # Redact the whole value after "password:" (or the Italian phrasing),
    # not just the first word - a value containing spaces used to leak
    # everything after the first space.
    text = re.sub(
        r"(?i)((?:password|pwd)\s*[:=]\s*|la\s+password\s+[eè]\s*)\S.*",
        r"\1[REDACTED]",
        text,
    )
    # Card numbers as typed/displayed: with or without spaces/dashes, and
    # covering 13-16 digit lengths (Amex is 15, most others are 16).
    text = _CARD_NUMBER_RE.sub("[REDACTED-CARD]", text)
    return text

