"""Taiwan PDPA-Compliant Data Minimization and PII Scrubber.

Strips personally identifiable information (PII) including Taiwan Alien Resident Certificate
(ARC) numbers, foreign passport numbers, and phone numbers before queries reach the retrieval
engine or logging sinks.
"""

from typing import Tuple, List, Dict
import re

# Taiwan ARC pattern: 1 letter + '8' or '9' or 'A'-'D' + 8 digits, or legacy format
ARC_REGEX = re.compile(r"\b[A-Z][89A-D\d]\d{8}\b", re.IGNORECASE)

# Standard international passport pattern (1-2 uppercase letters + 6-9 digits)
PASSPORT_REGEX = re.compile(r"\b(?:passport\s*(?:no\.?|number|id)?\s*[:#]?\s*)?([A-Z]{1,2}\d{6,9})\b", re.IGNORECASE)

# Taiwan phone numbers: mobile (09XXXXXXXX or +886 9XXXXXXXX) or landline (02-XXXXXXXX)
PHONE_REGEX = re.compile(r"(\+886[- ]?|0)(9\d{2}[- ]?\d{3}[- ]?\d{3}|[2-8][- ]?\d{3,4}[- ]?\d{4})\b")

# Email address pattern
EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")


def scrub_pii(text: str) -> Tuple[str, List[Dict[str, str]]]:
    """Sanitizes text by replacing sensitive personal identifiers with generic tokens.
    
    Args:
        text: Raw user query or document text.
        
    Returns:
        Tuple of (sanitized_text, list_of_redacted_items)
    """
    if not text:
        return text, []

    redactions: List[Dict[str, str]] = []
    sanitized = text

    # Scrub ARC Numbers
    for match in ARC_REGEX.finditer(sanitized):
        val = match.group(0)
        redactions.append({"type": "ARC_NUMBER", "original_masked": val[:2] + "******" + val[-2:]})
    sanitized = ARC_REGEX.sub("[REDACTED_ARC_NUMBER]", sanitized)

    # Scrub Passport Numbers (where explicitly labeled or matching strict passport pattern)
    def passport_repl(m):
        val = m.group(1) if m.lastindex else m.group(0)
        redactions.append({"type": "PASSPORT_ID", "original_masked": val[:2] + "****" + val[-2:] if len(val) > 4 else "****"})
        return "[REDACTED_PASSPORT_ID]"
    
    # We replace pure passport matches if labeled or standalone
    sanitized = PASSPORT_REGEX.sub(passport_repl, sanitized)

    # Scrub Phone Numbers
    for match in PHONE_REGEX.finditer(sanitized):
        val = match.group(0)
        redactions.append({"type": "PHONE_NUMBER", "original_masked": val[:3] + "****" + val[-2:]})
    sanitized = PHONE_REGEX.sub("[REDACTED_PHONE_NUMBER]", sanitized)

    # Scrub Emails
    for match in EMAIL_REGEX.finditer(sanitized):
        val = match.group(0)
        redactions.append({"type": "EMAIL_ADDRESS", "original_masked": val[:2] + "****@" + val.split("@")[-1]})
    sanitized = EMAIL_REGEX.sub("[REDACTED_EMAIL]", sanitized)

    return sanitized, redactions
