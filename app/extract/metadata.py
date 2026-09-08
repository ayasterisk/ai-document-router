"""Metadata extraction with explicit provenance and separate urgency/deadline."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

from app.extract.sections import routing_text

DOC_TYPES = [
    "Quyết định",
    "Công văn",
    "Giấy mời",
    "Thông báo",
    "Báo cáo",
    "Tờ trình",
    "Công điện",
    "Chỉ thị",
    "Kế hoạch",
    "Phiếu chuyển",
    "Hướng dẫn",
    "Chương trình",
]
DATE_PATTERN = r"(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{4}|(?:ngày\s+)?\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})"
DEADLINE_PATTERN = (
    r"(?:trước ngày|chậm nhất(?: là)? ngày|hạn(?: là)? ngày|đến hết ngày|hạn chót)\s*[:.]?\s*("
    + DATE_PATTERN
    + r")"
)


def _parse_vn_date(text: str) -> date | None:
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b", text)
    if not m:
        m = re.search(
            r"(?:ngày\s+)?(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
            text,
            re.IGNORECASE,
        )
    if m:
        try:
            return date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            pass
    return None


@dataclass
class ExtractedMetadata:
    so_hieu: str | None = None
    loai: str | None = None
    co_quan_ban_hanh: str | None = None
    nguoi_ky: str | None = None
    ngay_van_ban: date | None = None
    trich_yeu: str | None = None
    han_thuc_hien: str | None = None
    khan: bool = False
    do_khan: str = "thuong"
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["ngay_van_ban"] = (
            self.ngay_van_ban.isoformat() if self.ngay_van_ban else None
        )
        return out


class MetadataExtractor:
    @staticmethod
    def extract_so_hieu(text: str) -> str | None:
        # Never borrow an identifier from a citation in the body.
        m = re.search(
            r"(?im)^\s*S[ốo]\s*[:.]\s*(\d{1,7}/[\wĐđ-]+(?:[/-][\wĐđ-]+)*)", text[:1500]
        )
        return m[1] if m else None

    @staticmethod
    def extract_loai(text: str) -> str | None:
        for line in text[:1500].splitlines():
            for kind in DOC_TYPES:
                if re.fullmatch(
                    re.escape(kind) + r"(?:\s*[-–:]?\s*(?:KHẨN|HỎA TỐC))?",
                    line.strip(),
                    re.IGNORECASE,
                ):
                    return kind
        return "Công văn" if re.search(r"(?im)^\s*V/v\b", text[:1500]) else None

    @staticmethod
    def extract_co_quan_ban_hanh(text: str) -> str | None:
        head = unicodedata.normalize("NFC", text[:1500])
        head = re.split(r"(?im)^\s*(?:Số\s*:|Kính gửi|V/v|Về việc|Căn cứ)", head)[0]
        candidates = []
        org = r"(?:SỞ\s+|CHI CỤC\s+|CỤC\s+|CÔNG TY\s+|KIỂM TOÁN NHÀ NƯỚC|BAN CHỈ HUY\s+|BỘ ĐỘI BIÊN PHÒNG\s+|CÔNG AN\s+|(?:ỦY|UỶ) BAN NHÂN DÂN\s+|UBND\s+|BỘ\s+|TRUNG TÂM\s+|HỢP TÁC XÃ\s+|BAN QUẢN LÝ\s+|TỈNH ỦY\s+)"
        for line in head.splitlines():
            line = re.split(
                r"CỘNG H[ÒO]A|Độc lập|,\s*ngày|\s{3,}", line, flags=re.IGNORECASE
            )[0].strip()
            if re.match(org, line, re.IGNORECASE):
                candidates.append(line)
            elif candidates and re.fullmatch(
                r"(?:TỈNH|XÃ|PHƯỜNG|HUYỆN|THÀNH PHỐ)\s+[^\d]+", line
            ):
                candidates[-1] += " " + line
        # Letterhead normally lists the parent first and issuing entity below it.
        return candidates[-1] if candidates else None

    @staticmethod
    def extract_nguoi_ky(text: str) -> str | None:
        m = re.search(
            r"(?:GIÁM ĐỐC|CHỦ TỊCH)\s*\n\s*([A-ZÀ-ỸĐ][a-zà-ỹđ]+(?:\s+[A-ZÀ-ỸĐ][a-zà-ỹđ]+){1,3})",
            text[-800:],
        )
        return m[1] if m else None

    @staticmethod
    def extract_ngay_van_ban(text: str) -> date | None:
        for line in text[:1200].splitlines():
            if re.search(r",\s*ngày\s+\d", line, re.IGNORECASE) and not re.search(
                r"trước|chậm nhất|hoàn thành|thời hạn", line, re.IGNORECASE
            ):
                return _parse_vn_date(line)
        return None

    @staticmethod
    def extract_trich_yeu(text: str) -> str | None:
        lines = text[:2200].splitlines()
        for i, line in enumerate(lines):
            m = re.match(
                r"\s*(?:Trích yếu|V/v|Về việc)\s*[:.]?\s*(.*)", line, re.IGNORECASE
            )
            is_title = any(
                line.strip().casefold() == kind.casefold() for kind in DOC_TYPES
            )
            if m or is_title:
                parts = [m[1]] if m else []
                for extra in lines[i + 1 : i + 5]:
                    if not extra.strip() or re.match(
                        r"\s*(?:Kính gửi|Căn cứ|Số\s*:|Điều \d|Nơi nhận|Đề nghị|Trả lời|ỦY BAN)",
                        extra,
                        re.IGNORECASE,
                    ):
                        break
                    if re.search(r",\s*ngày", extra, re.IGNORECASE):
                        break
                    parts.append(extra.strip())
                if parts:
                    return " ".join(parts).strip() or None
        return None

    @staticmethod
    def urgency(text: str) -> str:
        for line in text[:1200].splitlines():
            m = re.fullmatch(
                r"\s*(?:(?:Văn bản|Công điện|Độ khẩn)\s*:?\s*)?(KHẨN|HỎA TỐC|HOẢ TỐC|THƯỢNG KHẨN)\s*",
                line,
                re.IGNORECASE,
            )
            if m:
                return {"khẩn": "khan", "thượng khẩn": "thuong_khan"}.get(
                    m[1].lower(), "hoa_toc"
                )
        return "thuong"

    @classmethod
    def detect_khan(cls, text: str) -> bool:
        return cls.urgency(text) != "thuong"

    @staticmethod
    def deadline_candidates(text: str, received_on: date | None = None) -> list[dict]:
        candidates = []
        for m in re.finditer(DEADLINE_PATTERN, text, re.IGNORECASE):
            d = _parse_vn_date(m[1])
            if d:
                candidates.append({"date": d.isoformat(), "text": m[0]})
        if received_on:
            for m in re.finditer(
                r"trong (?:thời hạn\s+)?(\d{1,3}) ngày(?:\s+làm việc)?\s+kể từ (?:ngày )?nhận",
                text,
                re.IGNORECASE,
            ):
                # Business days require the department's holiday calendar.
                if "làm việc" not in m[0].lower():
                    candidates.append(
                        {
                            "date": (
                                received_on + timedelta(days=int(m[1]))
                            ).isoformat(),
                            "text": m[0],
                        }
                    )
        return candidates

    @classmethod
    def extract_han_thuc_hien(cls, text: str) -> str | None:
        candidates = cls.deadline_candidates(text)
        values = {c["date"] for c in candidates}
        return next(iter(values)) if len(values) == 1 else None

    @classmethod
    def extract(cls, text: str, received_on: date | None = None) -> ExtractedMetadata:
        text = unicodedata.normalize("NFC", text or "")
        meta = ExtractedMetadata(
            so_hieu=cls.extract_so_hieu(text),
            loai=cls.extract_loai(text),
            co_quan_ban_hanh=cls.extract_co_quan_ban_hanh(text),
            nguoi_ky=cls.extract_nguoi_ky(text),
            ngay_van_ban=cls.extract_ngay_van_ban(text),
            trich_yeu=cls.extract_trich_yeu(text),
            khan=cls.detect_khan(text),
            do_khan=cls.urgency(text),
        )
        scoped = routing_text(text)
        candidates = cls.deadline_candidates(scoped, received_on)
        values = {c["date"] for c in candidates}
        meta.han_thuc_hien = next(iter(values)) if len(values) == 1 else None
        meta.evidence["deadline_candidates"] = candidates
        meta.evidence["routing_text"] = scoped
        if len(values) > 1:
            meta.warnings.append("multiple_deadlines")
        if (
            re.search(r"(?:thời hạn|trong)\s+\d+\s+ngày", scoped, re.IGNORECASE)
            and not candidates
        ):
            meta.warnings.append("unresolved_relative_deadline")
        if (
            re.search(r"trước ngày|chậm nhất|hạn chót", scoped, re.IGNORECASE)
            and not candidates
        ):
            meta.warnings.append("unresolved_deadline")
        meta.missing = [
            k
            for k in (
                "so_hieu",
                "loai",
                "co_quan_ban_hanh",
                "ngay_van_ban",
                "trich_yeu",
            )
            if getattr(meta, k) is None
        ]
        return meta
