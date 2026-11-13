"""Multilingual Regulatory Normalization Engine.

Bridges language barriers by mapping colloquial native terms from Vietnamese and Indonesian
into standardized Taiwan campus administrative and regulatory terms (e.g. ARC, NHI, Health Exam).
"""

from typing import Dict, List, Tuple, Any
import re

# Regulatory concept dictionary with cross-lingual variants
REGULATORY_CONCEPTS: Dict[str, Dict[str, Any]] = {
    "ARC": {
        "canonical": "Alien Resident Certificate (ARC / 外僑居留證)",
        "keywords": ["ARC", "Alien Resident Certificate", "residence permit", "外僑居留證", "居留證"],
        "mappings": [
            # Vietnamese
            "thẻ cư trú", "the cu tru", "giấy phép cư trú", "giay phep cu tru", "thẻ arc", "gia hạn cư trú",
            # Indonesian
            "kartu izin tinggal", "izin tinggal", "kitas", "arc taiwan", "perpanjang izin tinggal",
            # Tagalog
            "permit sa pananatili", "arc kard", "residence permit", "pag-renew ng arc", "visa extension", "alien certificate",
            # Thai
            "บัตรประจำตัวคนต่างด้าว", "บัตรเออาร์ซี", "บัตร arc", "ต่ออายุบัตร", "ต่ออายุ arc", "ใบอนุญาตถิ่นที่อยู่",
            # Chinese
            "外僑居留證", "居留證", "居留證延期", "居留證過期"
        ]
    },
    "NHI": {
        "canonical": "National Health Insurance (NHI / 全民健康保險)",
        "keywords": ["NHI", "National Health Insurance", "health insurance", "全民健康保險", "健保", "健保卡"],
        "mappings": [
            # Vietnamese
            "bảo hiểm y tế", "bao hiem y te", "bảo hiểm sức khỏe", "thẻ bảo hiểm", "bhyt",
            # Indonesian
            "asuransi kesehatan", "asuransi nasional", "kartu asuransi", "bpjs taiwan",
            # Tagalog
            "seguro sa kalusugan", "health insurance", "philhealth taiwan", "nhi card", "pambansang seguro",
            # Thai
            "ประกันสุขภาพแห่งชาติ", "ประกันสุขภาพ", "บัตรประกันสุขภาพ", "บัตรทองไต้หวัน", "สปสช ไต้หวัน",
            # Chinese
            "全民健保", "健保", "健保卡", "學生保險", "醫療保險"
        ]
    },
    "HEALTH_EXAM": {
        "canonical": "Mandatory Health Examination Form B (健康檢查 / 乙表)",
        "keywords": ["Health Examination", "Form B", "medical checkup", "健康檢查", "體檢", "乙表"],
        "mappings": [
            # Vietnamese
            "khám sức khỏe", "kham suc khoe", "giấy khám sức khỏe", "xét nghiệm lao", "tiêm sởi", "form b",
            # Indonesian
            "cek kesehatan", "pemeriksaan kesehatan", "tes kesehatan", "rontgen paru", "vaksin campak", "form b",
            # Tagalog
            "medikal na eksaminasyon", "pagsusuri sa kalusugan", "health checkup", "x-ray sa baga", "bakuna sa tigdas", "form b",
            # Thai
            "ตรวจสุขภาพ", "ใบตรวจสุขภาพ", "ตรวจร่างกาย", "แบบ บี", "ฟอร์มบี", "ฉีดวัคซีนหัด", "เอกซเรย์ปอด",
            # Chinese
            "健康檢查", "體檢", "居留體檢", "乙表", "麻疹疫苗"
        ]
    },
    "DORMITORY": {
        "canonical": "On-Campus Dormitory Housing (宿舍 / 學生宿舍)",
        "keywords": ["dormitory", "housing", "dorm", "宿舍", "退宿", "宿舍門禁", "押金"],
        "mappings": [
            # Vietnamese
            "ký túc xá", "ky tuc xa", "phòng trọ", "ở ký túc", "tiền cọc phòng", "giờ giới nghiêm",
            # Indonesian
            "asrama", "kamar asrama", "tempat tinggal", "sewa kamar", "jam malam asrama", "deposit asrama",
            # Tagalog
            "dormitoryo", "dorm", "tirahan sa campus", "silid sa dorm", "curfew sa dorm", "deposito sa dorm",
            # Thai
            "หอพัก", "หอพักนักศึกษา", "หอใน", "กฎระเบียบหอพัก", "เวลาปิดหอ", "เงินประกันหอพัก",
            # Chinese
            "學生宿舍", "宿舍", "宿舍門禁", "退宿保證金", "校外租屋"
        ]
    },
    "COURSE_SELECTION": {
        "canonical": "Course Selection and Registration (選課 / 加簽 / 加退選)",
        "keywords": ["course selection", "registration", "add drop", "instructor override", "加簽", "選課", "學分"],
        "mappings": [
            # Vietnamese
            "đăng ký môn học", "dang ky mon hoc", "chọn môn", "thêm bớt môn", "xin chữ ký giáo viên", "tín chỉ",
            # Indonesian
            "pilih mata kuliah", "krs", "tambah kurang matkul", "tanda tangan dosen", "sks", "bimbingan akademik",
            # Tagalog
            "pagpili ng kurso", "pag-enroll", "pagdagdag ng klase", "bawas ng klase", "override ng propesor", "pirma ng guro",
            # Thai
            "ลงทะเบียนเรียน", "เลือกวิชาเรียน", "เพิ่มถอนรายวิชา", "ขอโควต้าอาจารย์", "ขอลายเซ็นอาจารย์", "หน่วยกิต",
            # Chinese
            "選課", "加退選", "加簽", "授權碼", "學分上限", "最低學分"
        ]
    },
    "OIA": {
        "canonical": "Office of International Affairs (OIA / 國際事務處)",
        "keywords": ["Office of International Affairs", "OIA", "國際事務處", "國際處"],
        "mappings": [
            # Vietnamese
            "phòng hợp tác quốc tế", "phong hop tac quoc te", "văn phòng oia", "ban quốc tế",
            # Indonesian
            "kantor urusan internasional", "kantor oia", "bagian mahasiswa internasional",
            # Tagalog
            "opisina ng mga internasyonal na gawain", "oia opisina", "opisina para sa dayuhang estudyante",
            # Thai
            "กองวิเทศสัมพันธ์", "สำนักงานวิเทศสัมพันธ์", "สำนักงานโอไอเอ", "ฝ่ายนักศึกษาต่างชาติ",
            # Chinese
            "國際事務處", "國際處", "國事處"
        ]
    },
    "NIA": {
        "canonical": "National Immigration Agency (NIA / 內政部移民署)",
        "keywords": ["National Immigration Agency", "NIA", "Immigration Office", "移民署"],
        "mappings": [
            # Vietnamese
            "cục di trú", "sở di dân", "cục xuất nhập cảnh", "văn phòng di trú",
            # Indonesian
            "kantor imigrasi", "badan imigrasi", "imigrasi taipei",
            # Tagalog
            "kawanihan ng imigrasyon", "opisina ng imigrasyon", "immigration office",
            # Thai
            "สำนักงานตรวจคนเข้าเมือง", "สตม ไต้หวัน", "ด่านตรวจคนเข้าเมือง",
            # Chinese
            "內政部移民署", "移民署", "服務站"
        ]
    }
}


def normalize_query(query: str, detected_lang: str = "en") -> Tuple[str, List[str]]:
    """Enriches and normalizes the user query by detecting colloquial native expressions
    and injecting canonical administrative keywords.
    
    Args:
        query: Raw or sanitized user query.
        detected_lang: Language detected ('en', 'zh', 'vi', 'id', 'tl', 'th').
        
    Returns:
        Tuple of (enriched_search_query, list_of_detected_concepts)
    """
    if not query:
        return query, []

    lower_query = query.lower()
    matched_concepts = []
    injected_keywords = []

    for concept_id, concept_data in REGULATORY_CONCEPTS.items():
        found = False
        
        # Check explicit keywords
        for kw in concept_data["keywords"]:
            kw_clean = kw.lower()
            # If CJK characters present, use substring match
            if re.search(r"[\u4e00-\u9fff]", kw_clean):
                if kw_clean in lower_query:
                    found = True
                    break
            else:
                pattern = r"\b" + re.escape(kw_clean) + r"\b"
                if re.search(pattern, lower_query):
                    found = True
                    break
        
        # Check language mappings
        if not found:
            for term in concept_data["mappings"]:
                term_clean = term.lower()
                # If CJK characters present or multi-word phrase
                if re.search(r"[\u4e00-\u9fff]", term_clean) or (" " in term_clean):
                    if term_clean in lower_query:
                        found = True
                        break
                else:
                    pattern = r"\b" + re.escape(term_clean) + r"\b"
                    if re.search(pattern, lower_query):
                        found = True
                        break

        if found:
            matched_concepts.append(concept_id)
            injected_keywords.extend(concept_data["keywords"][:3])

    if matched_concepts:
        # Create an enriched query that pairs original query with canonical terms
        enriched = f"{query} {' '.join(injected_keywords)}"
        return enriched, matched_concepts

    return query, []
