"""Deterministic Crisis Policy Engine for iCare Navigator.

Enforces strict non-clinical safety boundaries. Deterministically intercepts acute crisis,
self-harm, or suicidal ideation markers across English, Chinese, Vietnamese, and Indonesian,
immediately terminating non-clinical dialogue and routing to Taiwan emergency hotlines.
"""

from typing import Dict, Any, Optional, Tuple
import re

# Multilingual crisis keywords and patterns
CRISIS_PATTERNS = [
    # English
    r"\b(suicide|suicidal|kill myself|want to die|end(ing)? my life|end(ing)? it all|hurt myself|self[- ]harm|take my own life)\b",
    r"\b(can'?t go on living|no reason to live|better off dead|thoughts of (ending|taking) my life)\b",
    # Chinese (Traditional & Simplified)
    r"(想自殺|自殘|想死|不想活了|結束生命|割腕|尋死|跳樓|走投無路|活著沒意思)",
    # Vietnamese
    r"\b(tự tử|tự sát|muốn chết|kết thúc cuộc đời|không muốn sống|tự hại|tuyệt vọng không muốn sống)\b",
    # Indonesian
    r"\b(bunuh diri|ingin mati|akhiri hidup|menyakiti diri|tidak mau hidup lagi|putus asa ingin mati)\b",
    # Tagalog / Filipino
    r"\b(magpakamatay|kitlin ang buhay|gusto ko nang mamatay|ayaw ko nang mabuhay|saktan ang sarili|tapusin ang buhay|tapusin ang lahat)\b",
    # Thai
    r"(ฆ่าตัวตาย|ทำร้ายตัวเอง|อยากตาย|ไม่อยากมีชีวิตอยู่|จบชีวิต|ไม่อยากอยู่แล้ว)",
]

COMPILED_CRISIS_REGEXES = [re.compile(p, re.IGNORECASE) for p in CRISIS_PATTERNS]


def detect_crisis(text: str) -> Tuple[bool, Optional[str]]:
    """Evaluates whether the input contains acute crisis, self-harm, or suicidal markers.
    
    Args:
        text: Inbound student message text.
        
    Returns:
        Tuple of (is_crisis, matched_pattern_or_none)
    """
    if not text:
        return False, None
    
    cleaned = text.strip()
    for regex in COMPILED_CRISIS_REGEXES:
        match = regex.search(cleaned)
        if match:
            return True, match.group(0)
            
    return False, None


def get_crisis_escalation_payload(language: str = "en") -> Dict[str, Any]:
    """Generates the standardized crisis intervention card and hotline payload.
    
    Args:
        language: Detected language code ('en', 'zh', 'vi', 'id')
        
    Returns:
        Structured crisis response payload with emergency contacts.
    """
    hotlines = [
        {
            "name": "Taiwan MOHW 24-Hour Suicide Prevention Hotline (安心專線)",
            "number": "1925",
            "hours": "24/7",
            "languages": "Mandarin, English, Taiwanese",
            "description": "Government mental health crisis and suicide prevention helpline."
        },
        {
            "name": "Lifeline Crisis Hotline (生命線協談專線)",
            "number": "1995",
            "hours": "24/7",
            "languages": "Mandarin, Taiwanese",
            "description": "Nationwide crisis counseling and emotional support."
        },
        {
            "name": "Foreign Workers & Students 24h Multilingual Helpline (1955專線)",
            "number": "1955",
            "hours": "24/7 Free",
            "languages": "English, Vietnamese, Indonesian, Thai, Mandarin",
            "description": "Dedicated government counseling and rights protection line."
        },
        {
            "name": "Campus 24-Hour Emergency Security Office (校安中心)",
            "number": "(02) 2362-0000 / Ext. 5555",
            "hours": "24/7",
            "languages": "Mandarin, English",
            "description": "Direct university on-campus emergency and safety response."
        },
        {
            "name": "Student Counseling & Well-being Center (學生心理諮商中心)",
            "number": "(02) 3366-2181",
            "location": "General Building, Room 301",
            "hours": "Monday - Friday 08:30 - 17:30",
            "emergency_intake_url": "https://counseling.university.edu.tw/crisis-intake",
            "description": "Free, confidential counseling for international students."
        }
    ]
    
    messages = {
        "en": (
            "🚨 **Immediate Support & Safety Notice**\n\n"
            "We hear that you are going through a painful or overwhelming moment. "
            "Please know that **you do not have to carry this alone**, and immediate confidential help is available right now.\n\n"
            "Because iCare is an automated administrative assistant, we have paused our automated responses "
            "to connect you directly with caring, professional human support:"
        ),
        "zh": (
            "🚨 **緊急關懷與即時協助通知**\n\n"
            "我們非常關心你目前的處境，請記得**你並不是孤單一人**，有專業的團隊隨時願意陪伴你、支持你。\n\n"
            "iCare 作為校園行政引導助理，已立即暫停一般回覆，為你提供 24 小時即時求助與校園關懷專線："
        ),
        "vi": (
            "🚨 **Thông Báo Hỗ Trợ Khẩn Cấp & An Toàn**\n\n"
            "Chúng tôi rất quan tâm đến những gì bạn đang trải qua. Xin hãy nhớ rằng **bạn không hề đơn độc**, "
            "và luôn có sự hỗ trợ chuyên môn, bảo mật sẵn sàng giúp đỡ bạn ngay lúc này.\n\n"
            "Vì iCare là trợ lý điều hướng hành chính tự động, chúng tôi đã tạm dừng hội thoại tự động "
            "để kết nối bạn ngay lập tức với các đường dây hỗ trợ chuyên nghiệp 24/7 tại Đài Loan:"
        ),
        "id": (
            "🚨 **Pemberitahuan Bantuan Darurat & Keselamatan**\n\n"
            "Kami sangat peduli dengan apa yang sedang Anda alami. Ingatlah bahwa **Anda tidak sendirian**, "
            "dan ada bantuan profesional yang siap mendengarkan dan mendukung Anda saat ini.\n\n"
            "Karena iCare adalah asisten navigasi administratif, kami telah menghentikan respons otomatis "
            "untuk langsung menghubungkan Anda dengan layanan bantuan 24 jam di Taiwan:"
        ),
        "tl": (
            "🚨 **Agarang Suporta at Abiso sa Kaligtasan**\n\n"
            "Naiintindihan namin na ikaw ay dumaranas ng napakahirap na sitwasyon. "
            "Alamin na **hindi ka nag-iisa**, at mayroong propesyonal na tulong na handang makinig sa iyo ngayon din.\n\n"
            "Dahil ang iCare ay isang automated campus assistant, pansamantala naming itinigil ang aming tugon "
            "upang ikonekta ka sa mga mapagkalingang propesyonal sa Taiwan:"
        ),
        "th": (
            "🚨 **ประกาศความช่วยเหลือฉุกเฉินและความปลอดภัย**\n\n"
            "เรารับรู้ว่าคุณอาจกำลังเผชิญกับช่วงเวลาที่ยากลำบากอย่างยิ่ง "
            "โปรดทราบว่า **คุณไม่ได้อยู่ตัวคนเดียว** และมีความช่วยเหลือจากผู้เชี่ยวชาญพร้อมดูแลคุณทันทีตลอด 24 ชั่วโมง\n\n"
            "เนื่องจาก iCare เป็นระบบผู้ช่วยอัตโนมัติ เราจึงขอส่งต่อคุณให้กับเจ้าหน้าที่ผู้เชี่ยวชาญในไต้หวันโดยตรง:"
        )
    }

    intro_text = messages.get(language, messages["en"])
    
    return {
        "is_crisis": True,
        "language": language,
        "message": intro_text,
        "emergency_hotlines": hotlines,
        "next_step": "Please reach out to one of the hotlines above or visit the Student Counseling Center in Room 301. If you are in immediate physical danger, dial 110 (Police) or 119 (Ambulance)."
    }
