"""Unit tests for language detection and cross-lingual regulatory normalization."""

import unittest
from src.nlp.language_detector import detect_language
from src.nlp.cross_lingual_normalizer import normalize_query


class TestNLPModules(unittest.TestCase):

    def test_language_detection(self):
        cases = [
            # English queries (including 'in Taiwan', acronyms, loanwords)
            ("What is the fee for an Alien Resident Certificate?", "en"),
            ("How do I apply for ARC in Taiwan?", "en"),
            ("What documents do I need for ARC in Taiwan?", "en"),
            ("Where is the immigration office in Taiwan for ARC?", "en"),
            ("Can international students take a loan in Taiwan?", "en"),
            ("ARC requirements in Taiwan", "en"),
            ("How to apply ARC card in Taiwan?", "en"),
            ("ARC", "en"),
            ("NHI", "en"),
            ("Form B", "en"),

            # Chinese queries
            ("請問居留證到期前幾天需要去移民署辦理延期？", "zh"),
            ("如果選課系統額滿了，我要如何拿到授權碼並請教授加簽？", "zh"),
            ("外僑居留證如何辦理？", "zh"),
            ("居留證", "zh"),

            # Vietnamese queries
            ("Làm thế nào để đăng ký bảo hiểm y tế ở Đài Loan?", "vi"),
            ("Tôi cần làm gì để gia hạn thẻ cư trú (thẻ arc) và xin giấy tờ gì ở trường?", "vi"),
            ("thẻ cư trú", "vi"),

            # Indonesian queries
            ("Bagaimana cara perpanjang kartu izin tinggal di imigrasi?", "id"),
            ("Berapa biaya asuransi kesehatan nasional (nhi) per bulan untuk mahasiswa asing?", "id"),
            ("Syarat perpanjang arc di taiwan apa saja?", "id"),
            # Tagalog / Filipino queries
            ("Paano mag-apply ng Alien Resident Certificate sa Taiwan?", "tl"),
            ("Saan ako kukuha ng health certificate para sa Form B?", "tl"),
            ("Paano mag-renew ng permit sa pananatili?", "tl"),

            # Thai queries
            ("ต่ออายุบัตร ARC ต้องทำอย่างไรบ้างในไต้หวัน?", "th"),
            ("ประกันสุขภาพแห่งชาติ NHI ต้องจ่ายเดือนละเท่าไหร่?", "th"),
            ("ตรวจสุขภาพ Form B ต้องส่งที่ไหน?", "th"),
        ]
        for text, expected in cases:
            detected = detect_language(text)
            self.assertEqual(detected, expected, f"Failed for text: '{text}', got '{detected}'")

    def test_vietnamese_cross_lingual_normalization(self):
        # Vietnamese query about ARC (thẻ cư trú) and OIA
        query = "Làm sao để gia hạn thẻ cư trú tại trường?"
        enriched, concepts = normalize_query(query, detected_lang="vi")
        self.assertIn("ARC", concepts)
        self.assertIn("Alien Resident Certificate", enriched)

    def test_indonesian_cross_lingual_normalization(self):
        # Indonesian query about NHI (asuransi kesehatan)
        query = "Kapan saya bisa ikut asuransi kesehatan nasional?"
        enriched, concepts = normalize_query(query, detected_lang="id")
        self.assertIn("NHI", concepts)
        self.assertIn("National Health Insurance", enriched)

    def test_tagalog_cross_lingual_normalization(self):
        # Tagalog query about ARC (permit sa pananatili)
        query = "Paano mag-renew ng permit sa pananatili sa paaralan?"
        enriched, concepts = normalize_query(query, detected_lang="tl")
        self.assertIn("ARC", concepts)
        self.assertIn("Alien Resident Certificate", enriched)

    def test_thai_cross_lingual_normalization(self):
        # Thai query about ARC (ต่ออายุบัตร ARC)
        query = "ต่ออายุบัตร ARC ต้องเตรียมเอกสารอะไรบ้าง?"
        enriched, concepts = normalize_query(query, detected_lang="th")
        self.assertIn("ARC", concepts)
        self.assertIn("Alien Resident Certificate", enriched)

    def test_chinese_regulatory_normalization(self):
        # Chinese query about course add/drop and override (加簽)
        query = "請問這學期選課加簽的截止日期是什麼時候？"
        enriched, concepts = normalize_query(query, detected_lang="zh")
        self.assertIn("COURSE_SELECTION", concepts)


if __name__ == "__main__":
    unittest.main()
