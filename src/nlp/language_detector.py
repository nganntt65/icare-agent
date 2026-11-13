"""High-Accuracy Multilingual Language Detection using Lingua.

Identifies the student's query language among:
- English ('en')
- Traditional / Simplified Chinese ('zh')
- Vietnamese ('vi')
- Indonesian ('id')

Uses Lingua Language Detector constrained to target languages for sub-millisecond,
highly accurate short-text classification, with fallback to LangDetect and heuristic guardrails.
"""

from typing import Optional
import re

# Characteristic Vietnamese diacritics
VIETNAMESE_DIACRITICS = set("ăâđêôơưàảãáạằẳẵắặầẩẫấậèẻẽéẹềểễếệìỉĩíịòỏõóọồổỗốộờởỡớợùủũúụừửữứựỳỷỹýỵĐ")

# Chinese character regex
CHINESE_REGEX = re.compile(r"[\u4e00-\u9fff]")

# Thai script character regex
THAI_REGEX = re.compile(r"[\u0e00-\u0e7f]")

# Characteristic Tagalog / Filipino grammar particles and question markers
TAGALOG_MARKERS = {
    "mga", "ang", "ng", "sa", "ba", "po", "paano", "kailan", "nasaan",
    "bakit", "sino", "lahat", "ito", "iyon", "kami", "tayo", "sila",
    "kayo", "ko", "mo", "niya", "namin", "ninyo", "nila", "pwede", "maaari"
}

# Common single-acronym administrative campus queries that default to English
CAMPUS_ACRONYMS = {"arc", "nhi", "oia", "nia", "kitas", "form b", "form-b", "apr"}

_LINGUA_DETECTOR = None
_LANGDETECT_AVAILABLE = False


def _get_lingua_detector():
    """Lazily initializes the Lingua detector constrained to our 6 target languages."""
    global _LINGUA_DETECTOR
    if _LINGUA_DETECTOR is None:
        try:
            from lingua import Language, LanguageDetectorBuilder
            languages = [
                Language.ENGLISH,
                Language.CHINESE,
                Language.VIETNAMESE,
                Language.INDONESIAN,
                Language.TAGALOG,
                Language.THAI
            ]
            _LINGUA_DETECTOR = (
                LanguageDetectorBuilder.from_languages(*languages)
                .with_minimum_relative_distance(0.05)
                .build()
            )
        except Exception:
            _LINGUA_DETECTOR = False
    return _LINGUA_DETECTOR if _LINGUA_DETECTOR is not False else None


def detect_language(text: str) -> str:
    """Detects primary language of the text ('en', 'zh', 'vi', 'id', 'tl', 'th').
    
    Args:
        text: Inbound student message or query string.
        
    Returns:
        One of 'en', 'zh', 'vi', 'id', 'tl', 'th'. Defaults to 'en'.
    """
    if not text or not text.strip():
        return "en"

    clean_text = text.strip()
    lower_text = clean_text.lower()

    # 1. Guardrail: Isolated campus acronyms or short administrative terms default to English
    if lower_text in CAMPUS_ACRONYMS:
        return "en"

    # 2. Guardrail: Thai script check (100% deterministic via Unicode script block)
    thai_count = len(THAI_REGEX.findall(clean_text))
    if thai_count >= 2 or (thai_count >= 1 and len(clean_text) <= 5):
        return "th"

    # 3. Guardrail: Clear Chinese characters
    cjk_count = len(CHINESE_REGEX.findall(clean_text))
    if cjk_count >= 2:
        # Check if it's primarily an English sentence mentioning a Chinese term
        ascii_words = [w for w in re.findall(r"\b[a-zA-Z]{2,}\b", clean_text)]
        if len(ascii_words) >= 4 and cjk_count <= 4:
            return "en"
        return "zh"
    elif cjk_count == 1 and len(clean_text) <= 4:
        return "zh"

    # 4. Guardrail: Strong Vietnamese diacritics check
    vn_diacritic_count = sum(1 for c in clean_text if c in VIETNAMESE_DIACRITICS)
    if vn_diacritic_count >= 2:
        return "vi"

    # 5. Guardrail: Tagalog particles check
    words_in_text = set(re.findall(r"\b[a-zA-Z]+\b", lower_text))
    if len(words_in_text.intersection(TAGALOG_MARKERS)) >= 2:
        return "tl"

    # 6. Primary: High-Accuracy Lingua Detector (Rust-powered N-Gram & Rule Model)
    detector = _get_lingua_detector()
    if detector:
        try:
            from lingua import Language
            detected = detector.detect_language_of(clean_text)
            if detected == Language.ENGLISH:
                return "en"
            elif detected == Language.CHINESE:
                return "zh"
            elif detected == Language.VIETNAMESE:
                return "vi"
            elif detected == Language.INDONESIAN:
                return "id"
            elif detected == Language.TAGALOG:
                return "tl"
            elif detected == Language.THAI:
                return "th"
        except Exception:
            pass

    # 7. Fallback: LangDetect library
    try:
        from langdetect import detect
        code = detect(clean_text)
        if code.startswith("zh"):
            return "zh"
        elif code in ("vi", "id", "en", "th", "tl"):
            return code
        elif code == "fil":
            return "tl"
    except Exception:
        pass

    # 8. Default to English
    return "en"


