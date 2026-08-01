from __future__ import annotations

import re

_SENSITIVE_PATTERNS = [
    re.compile(r"password|credit.?card|ssn|social.?security", re.IGNORECASE),
]

_TOPIC_BOUNDARY = re.compile(
    r"(how\s+to\s+(hack|exploit|crack|bypass)|"
    r"generate\s+(fake|fraudulent|illegal)|"
    r"instructions\s+for\s+(theft|fraud|illegal))",
    re.IGNORECASE,
)


def validate_input(text: str) -> str | None:
    for pat in _SENSITIVE_PATTERNS:
        if pat.search(text):
            return "Request contains sensitive information that cannot be processed."
    if _TOPIC_BOUNDARY.search(text):
        return "Request is outside the scope of spend intelligence."
    return None


def sanitize_output(text: str) -> str:
    text = re.sub(r"(?i)(password:\s*)\S+", r"\1[REDACTED]", text)
    text = re.sub(r"\b\d{16}\b", "[REDACTED-CARD]", text)
    return text
