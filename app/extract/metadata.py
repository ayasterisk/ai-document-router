"""Trích metadata + hạn thực hiện từ nội dung văn bản (deterministic, regex).

Vì đầu vào không còn payload JSON, toàn bộ thông tin nghiệp vụ (số hiệu, loại,
cơ quan ban hành, người ký, ngày, trích yếu, hạn thực hiện) được trích từ text
của file đính kèm. Phần không bắt được bằng regex sẽ do model (harness) bổ sung.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Optional

MONTH_WORDS = {
    "một": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4, "năm": 5,
    "sáu": 6, "bảy": 7, "tám": 8, "chín": 9, "mười": 10,
    "mười một": 11, "mười hai": 12, "chạp": 12,
}

DOC_TYPES = [
    "quyết định", "công văn", "giấy mời", "thông báo", "báo cáo",
    "tờ trình", "công điện", "chỉ thị", "kế hoạch", "phiếu chuyển",
    "đề nghị", "quy định", "hướng dẫn", "chương trình",
]


def _parse_vn_date(text: str) -> Optional[date]:
    """Parse ngày: DD/MM/YYYY, DD-MM-YYYY, 'ngày DD tháng M năm YYYY'."""
    if not text:
        return None
    s = text.strip()

    # DD/MM/YYYY hoặc DD-MM-YYYY
    m = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            try:
                return date(y, mo, d)
            except ValueError:
                return None

    # 'ngày 15 tháng 8 năm 2026' / '15 tháng 8 năm 2026'
    m = re.search(
        r"(?:ngày\s+)?(\d{1,2})\s+tháng\s+([^\s,.;]+)\s*(?:năm\s+(\d{4}))?",
        s,
        re.IGNORECASE,
    )
    if m:
        d = int(m.group(1))
        mo_word = m.group(2).lower()
        mo = MONTH_WORDS.get(mo_word) or (int(mo_word) if mo_word.isdigit() else None)
        y = int(m.group(3)) if m.group(3) else date.today().year
        if mo and 1 <= d <= 31:
            try:
                return date(y, mo, d)
            except ValueError:
                return None
    return None


@dataclass
class ExtractedMetadata:
    so_hieu: Optional[str] = None
    loai: Optional[str] = None
    co_quan_ban_hanh: Optional[str] = None
    nguoi_ky: Optional[str] = None
    ngay_van_ban: Optional[date] = None
    trich_yeu: Optional[str] = None
    han_thuc_hien: Optional[str] = None  # "YYYY-MM-DD" hoặc "hỏa tốc"
    khan: bool = False
    missing: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "so_hieu": self.so_hieu,
            "loai": self.loai,
            "co_quan_ban_hanh": self.co_quan_ban_hanh,
            "nguoi_ky": self.nguoi_ky,
            "ngay_van_ban": self.ngay_van_ban.isoformat() if self.ngay_van_ban else None,
            "trich_yeu": self.trich_yeu,
            "han_thuc_hien": self.han_thuc_hien,
            "khan": self.khan,
        }


class MetadataExtractor:
    """Tập các hàm regex trích metadata từ văn bản tiếng Việt."""

    # ------------------------------------------------------------------ #
    @staticmethod
    def extract_so_hieu(text: str) -> Optional[str]:
        m = re.search(r"[Ss][oố][\s]*[:.]\s*([^\n]{1,40})", text)
        if m:
            return m.group(1).strip()
        # fallback: dạng 123/SNNMT-XXX
        m = re.search(r"\b(\d{1,5}/[A-ZĐÀ-Ỹ][A-ZĐÀ-Ỹ0-9/-]{2,24})", text)
        if m:
            return m.group(1).strip()
        return None

    @staticmethod
    def extract_loai(text: str) -> Optional[str]:
        head = text[:800]
        for dt in DOC_TYPES:
            if re.search(rf"\b{dt}\b", head, re.IGNORECASE):
                return dt.capitalize()
        return None

    @staticmethod
    def extract_co_quan_ban_hanh(text: str) -> Optional[str]:
        head = text[:600]
        patterns = [
            r"ỦY BAN NHÂN DÂN\s+(?:TỈNH|THÀNH PHỐ|HUYỆN|THỊ XÃ)\s+[A-ZÀ-ỸĐ\s]+",
            r"UBND\s+(?:TỈNH|THÀNH PHỐ|HUYỆN|THỊ XÃ)\s+[A-ZÀ-ỸĐ\s]+",
            r"SỞ\s+[A-ZÀ-ỸĐ\s]+",
            r"BỘ\s+[A-ZÀ-ỸĐ\s]+",
            r"CỤC\s+THUẾ\s+[A-ZÀ-ỸĐ\s]+",
            r"CHI CỤC\s+THUẾ\s+[A-ZÀ-ỸĐ\s]+",
            r"TỈNH ỦY\s+[A-ZÀ-ỸĐ\s]+",
        ]
        for p in patterns:
            m = re.search(p, head)
            if m:
                return re.sub(r"\s+", " ", m.group(0)).strip()
        return None

    @staticmethod
    def extract_nguoi_ky(text: str) -> Optional[str]:
        # thường nằm gần cuối văn bản, kèm chức danh ký
        tail = text[-600:]
        m = re.search(
            r"(?:KT\.?\s*)?(?:GIÁM ĐỐC|PHÓ GIÁM ĐỐC|CHỦ TỊCH|PHÓ CHỦ TỊCH|TM\.?\s+)\s*\n"
            r"([A-ZÀ-ỸĐ][a-zà-ỹđ]+\s+[A-ZÀ-ỸĐ][a-zà-ỹđ]+(?:\s+[A-ZÀ-ỸĐ][a-zà-ỹđ]+)?)",
            tail,
        )
        if m:
            return m.group(1).strip()
        return None

    @staticmethod
    def extract_ngay_van_ban(text: str) -> Optional[date]:
        # ưu tiên dòng '..., ngày ... tháng ... năm ...'
        m = re.search(r"ngày\s+(\d{1,2})\s+tháng\s+([^\s,.;]+)\s*(?:năm\s+(\d{4}))?", text, re.IGNORECASE)
        if m:
            return _parse_vn_date(m.group(0))
        return _parse_vn_date(text)

    @staticmethod
    def extract_trich_yeu(text: str) -> Optional[str]:
        m = re.search(r"(?:Trích yếu|V/v|Về việc)\s*[:.]\s*([^\n]+(?:\n[^\n]{1,120})?)", text, re.IGNORECASE)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
        return None

    @staticmethod
    def extract_han_thuc_hien(text: str) -> Optional[str]:
        # 1) ngày cụ thể
        for pat in [r"trước ngày", r"chậm nhất(?: là)? ngày", r"hạn(?: là)? ngày", r"đến hết ngày", r"hạn chót"]:
            m = re.search(pat + r"\s*[:.]?\s*([^\n,.;]{0,30})", text, re.IGNORECASE)
            if m:
                d = _parse_vn_date(m.group(1))
                if d:
                    return d.isoformat()
        # 'trong thời hạn N ngày' -> không có ngày tuyệt đối, bỏ qua (trả None)
        # 2) dấu hiệu khẩn / hỏa tốc
        if MetadataExtractor.detect_khan(text):
            return "hỏa tốc"
        return None

    @staticmethod
    def detect_khan(text: str) -> bool:
        return bool(re.search(r"\b(khẩn|hỏa tốc|thượng khẩn|khẩn cấp|hoả tốc)\b", text, re.IGNORECASE))

    # ------------------------------------------------------------------ #
    @classmethod
    def extract(cls, text: str) -> ExtractedMetadata:
        text = text or ""
        meta = ExtractedMetadata(
            so_hieu=cls.extract_so_hieu(text),
            loai=cls.extract_loai(text),
            co_quan_ban_hanh=cls.extract_co_quan_ban_hanh(text),
            nguoi_ky=cls.extract_nguoi_ky(text),
            ngay_van_ban=cls.extract_ngay_van_ban(text),
            trich_yeu=cls.extract_trich_yeu(text),
            han_thuc_hien=cls.extract_han_thuc_hien(text),
            khan=cls.detect_khan(text),
        )
        meta.missing = [k for k, v in meta.to_dict().items() if v is None]
        return meta
