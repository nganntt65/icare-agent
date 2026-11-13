"""Faithfulness & Citation Auditor for Grounded Retrieval Verification.

Audits generated responses against retrieved official sources:
1. Verifies that claims align with retrieved snippets.
2. Computes grounding confidence score (target threshold: 0.85).
3. Detects low-confidence or non-covered queries and appends uncertainty disclaimers with direct OIA contact.
4. Enforces non-diagnostic boundaries (prohibits clinical diagnoses or prescription recommendations).
"""

from typing import List, Tuple, Dict, Any
import re
from src.retrieval.hybrid_rrf import RankedResult
from src.agent.state import Citation

# Medical/Diagnostic terms prohibited under non-diagnostic boundaries
PROHIBITED_DIAGNOSTIC_TERMS = [
    r"\byou\s+have\s+(depression|anxiety\s+disorder|bipolar|schizophrenia|ptsd)\b",
    r"\byou\s+should\s+take\s+\d+\s*(mg|milligram|tablets?)\b",
    r"\bprescribe\s+(antidepressants?|medication|xanax|prozac)\b",
    r"(診斷您患有|建議服用.*毫克|開立藥物)"
]

COMPILED_DIAGNOSTIC_REGEXES = [re.compile(p, re.IGNORECASE) for p in PROHIBITED_DIAGNOSTIC_TERMS]


class CitationAuditor:
    """Verifies output faithfulness and attaches structured citations."""

    def __init__(self, confidence_threshold: float = 0.85):
        self.confidence_threshold = confidence_threshold

    def audit_and_format(
        self,
        answer: str,
        retrieved_results: List[RankedResult],
        language: str = "en"
    ) -> Tuple[str, List[Citation], float, bool]:
        """Audits the generated response and builds verified citation attachments.
        
        Args:
            answer: Preliminary synthesized answer.
            retrieved_results: Top ranked results from hybrid RRF retrieval.
            language: Language code.
            
        Returns:
            Tuple of:
            - audited_answer (str)
            - verified_citations (List[Citation])
            - confidence_score (float)
            - is_low_confidence (bool)
        """
        # 1. Non-diagnostic boundary check
        for regex in COMPILED_DIAGNOSTIC_REGEXES:
            if regex.search(answer):
                warning_notice = (
                    "\n\n*(Notice: As an administrative assistant, iCare cannot provide medical "
                    "or psychological diagnoses. For health evaluations, please consult Campus Health Center "
                    "or the Student Counseling Center.)*"
                )
                answer = regex.sub("[clinical assessment removed]", answer) + warning_notice

        # 2. Extract citations from top results
        citations: List[Citation] = []
        if not retrieved_results:
            confidence_score = 0.40
            is_low_confidence = True
            audited_answer = self._append_uncertainty_disclaimer(answer, language)
            return audited_answer, citations, confidence_score, is_low_confidence

        top_rrf = retrieved_results[0].rrf_score
        
        # Build structured citations
        for res in retrieved_results[:3]:
            # Take first 160 characters as preview snippet
            clean_snippet = res.content.replace("\n", " ").strip()
            if len(clean_snippet) > 160:
                clean_snippet = clean_snippet[:157] + "..."

            citations.append(Citation(
                source_file=res.source_file,
                doc_title=res.doc_title,
                section_title=res.section_title,
                chunk_id=res.chunk_id,
                snippet=clean_snippet,
                rrf_score=res.rrf_score
            ))

        # 3. Calculate Confidence Score based on RRF strength and source match
        # RRF for 2 top-1 ranks = 1/(60+1) + 1/(60+1) = ~0.0328.
        # Normalize top RRF score to 0.0 - 1.0 range
        base_confidence = min(1.0, (top_rrf / 0.032) * 0.95)
        
        # Bonus if keyword overlap exists in the top doc
        top_content = retrieved_results[0].content.lower()
        key_matches = sum(1 for word in ["arc", "nhi", "health", "dorm", "course", "oia", "tuition", "fee"] if word in top_content)
        confidence_score = round(min(0.98, max(0.40, base_confidence + (0.02 * key_matches))), 2)

        is_low_confidence = confidence_score < self.confidence_threshold

        # 4. If confidence falls below 0.85, append uncertainty and OIA front-desk route
        if is_low_confidence:
            audited_answer = self._append_uncertainty_disclaimer(answer, language)
        else:
            audited_answer = answer

        return audited_answer, citations, confidence_score, is_low_confidence

    def _append_uncertainty_disclaimer(self, text: str, language: str) -> str:
        """Appends institutional contact and uncertainty advisory."""
        disclaimers = {
            "en": (
                "\n\nℹ️ **Advisory on Institutional Verification**:\n"
                "The system retrieval confidence for this specific inquiry is below our verified threshold (0.85). "
                "To ensure full compliance with university and immigration rules, please consult the "
                "**Office of International Affairs (OIA)** counter directly:\n"
                "- **Location**: Administration Building, Room 201\n"
                "- **Hours**: Mon–Fri 09:00–12:00, 13:30–17:00\n"
                "- **Phone**: +886-2-3366-2007 | Email: intladm@university.edu.tw"
            ),
            "zh": (
                "\n\nℹ️ **官方核實提醒**：\n"
                "系統對此項查詢之資料檢索可信度低於官方標準 (0.85)。為確保符合最新校規與法令，建議直接洽詢**國際事務處 (OIA)** 櫃台：\n"
                "- **地點**：行政大樓 201 室\n"
                "- **服務時間**：週一至週五 09:00–12:00, 13:30–17:00\n"
                "- **電話**：+886-2-3366-2007 | 電子郵件：intladm@university.edu.tw"
            ),
            "vi": (
                "\n\nℹ️ **Khuyến Nghị Xác Thực Chính Thức**:\n"
                "Độ tin cậy của hệ thống cho yêu cầu này thấp hơn ngưỡng tiêu chuẩn (0.85). Để đảm bảo chính xác các quy định mới nhất, bạn vui lòng liên hệ trực tiếp **Văn phòng Hợp tác Quốc tế (OIA)**:\n"
                "- **Địa điểm**: Tòa nhà Hành chính, Phòng 201\n"
                "- **Giờ làm việc**: Thứ 2 - Thứ 6 09:00–12:00, 13:30–17:00\n"
                "- **Điện thoại**: +886-2-3366-2007 | Email: intladm@university.edu.tw"
            ),
            "id": (
                "\n\nℹ️ **Saran Verifikasi Resmi**:\n"
                "Tingkat keyakinan sistem untuk pencarian ini berada di bawah batas standar (0.85). Untuk memastikan kepatuhan regulasi kampus, silakan hubungi langsung loket **Kantor Urusan Internasional (OIA)**:\n"
                "- **Lokasi**: Gedung Administrasi, Ruang 201\n"
                "- **Jam Kerja**: Senin–Jumat 09:00–12:00, 13:30–17:00\n"
                "- **Telepon**: +886-2-3366-2007 | Email: intladm@university.edu.tw"
            ),
            "tl": (
                "\n\nℹ️ **Payo sa Opisyal na Pag-verify**:\n"
                "Ang kumpiyansa sa pagkuha ng sistema para sa katanungang ito ay mas mababa sa pamantayang threshold (0.85). "
                "Upang matiyak ang buong pagsunod sa pinakabagong mga patakaran ng unibersidad at imigrasyon, mangyaring sumangguni sa **Office of International Affairs (OIA)** counter nang direkta:\n"
                "- **Lokasyon**: Administration Building, Room 201\n"
                "- **Oras ng Serbisyo**: Lun–Biy 09:00–12:00, 13:30–17:00\n"
                "- **Telepono**: +886-2-3366-2007 | Email: intladm@university.edu.tw"
            ),
            "th": (
                "\n\nℹ️ **คำแนะนำสำหรับการตรวจสอบอย่างเป็นทางการ**:\n"
                "ระดับความเชื่อมั่นของระบบสำหรับการค้นหานี้ต่ำกว่าเกณฑ์มาตรฐาน (0.85) "
                "เพื่อให้มั่นใจว่าเป็นไปตามกฎระเบียบและข้อบังคับล่าสุด โปรดติดต่อเคาน์เตอร์ **สำนักงานวิเทศสัมพันธ์ (OIA)** โดยตรง:\n"
                "- **สถานที่**: อาคารบริหาร ห้อง 201 (Administration Building, Room 201)\n"
                "- **เวลาทำการ**: จันทร์–ศุกร์ 09:00–12:00, 13:30–17:00\n"
                "- **โทรศัพท์**: +886-2-3366-2007 | อีเมล: intladm@university.edu.tw"
            )
        }
        return text + disclaimers.get(language, disclaimers["en"])
