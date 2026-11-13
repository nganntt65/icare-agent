"""Deterministic Prompt Injection and Jailbreak Interception Engine.

Protects against adversarial jailbreak patterns, system prompt extraction,
and unauthorized behavior override attempts without invoking the LLM.
"""

from typing import Tuple, Optional
import re

INJECTION_PATTERNS = [
    # System instruction bypasses
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"forget\s+(all\s+)?(previous|prior|above)\s+instructions",
    # Roleplay / Jailbreak personas
    r"\bDAN\s+mode\b",
    r"\bjailbreak\b",
    r"you\s+are\s+now\s+(an?\s+)?unrestricted\b",
    r"pretend\s+you\s+have\s+no\s+(rules|limits|safety)",
    r"developer\s+mode\s+enabled",
    # Secret extraction
    r"(reveal|show|print|leak|output)\s+(your\s+)?(system\s+prompt|hidden\s+prompt|master\s+instructions)",
    r"(reveal|show|print|leak|output)\s+(your\s+)?(api[_\s]?key|secret[_\s]?key|credentials)",
    r"what\s+is\s+your\s+(exact\s+)?system\s+prompt",
]

COMPILED_INJECTION_REGEXES = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def detect_prompt_injection(text: str) -> Tuple[bool, Optional[str]]:
    """Checks whether the inbound message matches prompt injection or jailbreak patterns.
    
    Args:
        text: Inbound student query.
        
    Returns:
        Tuple of (is_injection, matched_pattern_or_none)
    """
    if not text:
        return False, None
        
    cleaned = text.strip()
    for regex in COMPILED_INJECTION_REGEXES:
        match = regex.search(cleaned)
        if match:
            return True, match.group(0)
            
    return False, None


def get_injection_blocked_response(language: str = "en") -> str:
    """Returns a polite, secure denial response when injection is detected."""
    messages = {
        "en": (
            "⚠️ **Security Notice**: Your request contains patterns that conflict with our "
            "institutional security and safety policy. iCare is dedicated to assisting "
            "international students with campus procedures. How may I help you with your university journey?"
        ),
        "zh": (
            "⚠️ **安全防護提醒**：您的輸入包含違反校園系統安全政策之指令。iCare 專門協助國際學生處理在台行政與校園流程，請問有任何校園事務需要協助嗎？"
        ),
        "vi": (
            "⚠️ **Thông Báo Bảo Mật**: Yêu cầu của bạn chứa các mẫu lệnh xung đột với chính sách an toàn của hệ thống. iCare chuyên hỗ trợ các thủ tục trường học cho sinh viên quốc tế. Bạn cần hỗ trợ gì về hành chính campus?"
        ),
        "id": (
            "⚠️ **Pemberitahuan Keamanan**: Permintaan Anda berisi perintah yang melanggar kebijakan keamanan sistem. iCare berdedikasi untuk membantu mahasiswa internasional dalam prosedur kampus. Ada hal administrasi kampus yang bisa dibantu?"
        ),
        "tl": (
            "⚠️ **Paunawa sa Seguridad**: Ang iyong mensahe ay naglalaman ng mga pattern na sumasalungat sa aming patakaran sa seguridad ng institusyon. Ang iCare ay nakatuon sa pagtulong sa mga internasyonal na mag-aaral sa mga pamamaraan sa campus. Paano kita matutulungan sa iyong buhay-estudyante?"
        ),
        "th": (
            "⚠️ **ประกาศความปลอดภัย**: คำขอของคุณมีรูปแบบคำสั่งที่ขัดต่อความปลอดภัยของระบบ iCare มีหน้าที่ให้ความช่วยเหลือนักศึกษาต่างชาติในด้านระเบียบการและขั้นตอนต่างๆ ในมหาวิทยาลัย มีเรื่องเอกสารหรือระเบียบการใดที่ต้องการให้ช่วยเหลือหรือไม่?"
        )
    }
    return messages.get(language, messages["en"])
