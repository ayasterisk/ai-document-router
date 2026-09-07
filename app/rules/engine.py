"""Rule engine deterministic cho Sở NN&MT.

Nhận một Document (được dựng từ metadata trích từ nội dung văn bản), áp dụng rule
theo đúng thứ tự ưu tiên ("Nguyên tắc áp dụng"), dừng ở rule đầu tiên khớp, trả về
4 trường kết quả: Đơn vị xử lý chính / Phối hợp xử lý / Lãnh đạo theo dõi / Hạn thực hiện.

Thứ tự ưu tiên (khớp rulebaseSoNNMT.md):
  P1 (1): ký hiệu văn bản (Mục IV)
  P2 (2): ngoại lệ đặc biệt (Mục V) — V.9/V.10 bị bỏ qua khi khẩn
  P3 (3): văn bản khẩn còn 1-2 ngày (Mục VI)
  P4 (4): giấy mời (Mục II.4)
  P5 (5): quy tắc chung theo nguồn gửi + lĩnh vực phụ trách (Mục II.1-II.3)
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# --------------------------------------------------------------------------- #
# Chuẩn hóa text
# --------------------------------------------------------------------------- #
def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt + gập 'đ'->'d' để so khớp khoan dung hơn."""
    normalized = unicodedata.normalize("NFD", text)
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    return normalized.replace("đ", "d").replace("Đ", "d").lower()


def norm(text: str) -> str:
    return strip_accents(text).lower()


_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _contains(hay_norm: str, keyword: str) -> bool:
    """Khớp keyword trong haystack đã chuẩn hóa.

    - Từ đơn (không chứa khoảng trắng) -> khớp token chính xác (tránh 'hồ'->'ho'
      khớp nhầm 'không'/'họp').
    - Cụm từ -> khớp substring (để bắt 'công trình thủy lợi'...).
    """
    kw = norm(keyword)
    if " " in kw:
        return kw in hay_norm
    return kw in set(_TOKEN_SPLIT.split(hay_norm))


# --------------------------------------------------------------------------- #
# Model dữ liệu
# --------------------------------------------------------------------------- #
@dataclass
class Document:
    so_hieu: str = ""
    loai: str = ""
    co_quan_ban_hanh: str = ""
    nguoi_ky: str = ""
    ngay_van_ban: Optional[date] = None
    trich_yeu: str = ""
    noi_dung: str = ""              # toàn bộ text đã trích
    han_thuc_hien: Optional[str] = None  # "YYYY-MM-DD" hoặc "hỏa tốc"
    khan: bool = False              # dấu hiệu khẩn (khẩn/hỏa tốc, hoặc hạn <= 2 ngày)

    def haystack(self) -> str:
        return " ".join([self.loai, self.trich_yeu, self.noi_dung])


@dataclass
class EngineResult:
    don_vi_xu_ly_chinh: List[str] = field(default_factory=list)
    phoi_hop_xu_ly: List[str] = field(default_factory=list)
    lanh_dao_theo_doi: List[str] = field(default_factory=list)
    han_thuc_hien: Optional[str] = None
    confidence: float = 0.0
    reason: str = ""
    matched_rules: List[str] = field(default_factory=list)
    needs_review: bool = False
    extracted: Dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
class RuleEngine:
    def __init__(self, rules_path: Path | str):
        self.rules_path = Path(rules_path)
        with open(self.rules_path, "r", encoding="utf-8") as fh:
            self.data: Dict[str, Any] = yaml.safe_load(fh)
        self.rules: List[Dict[str, Any]] = self.data["rules"]
        self.lookup: Dict[str, Any] = self.data.get("lookup", {})
        self.personnel: Dict[str, str] = self.data.get("personnel", {})
        # đảm bảo duyệt đúng thứ tự ưu tiên, giữ thứ tự khai báo khi cùng priority
        ordered = sorted(
            enumerate(self.rules),
            key=lambda t: (t[1].get("priority", 999), t[0]),
        )
        self.rules = [rule for _, rule in ordered]

    # ------------------------------------------------------------------ #
    # Nhận diện đặc điểm
    # ------------------------------------------------------------------ #
    def detect_source(self, doc: Document) -> Optional[str]:
        """Phân loại nguồn gửi: cap_tren | so_nganh | khac | None (không rõ)."""
        text = norm(doc.co_quan_ban_hanh)
        ng = self.lookup["nguon_gui"]

        for pat in ng.get("specific_so_nganh", []):
            if norm(pat) in text:
                return "so_nganh"
        for pat in ng.get("cap_tren", []):
            if norm(pat) in text:
                return "cap_tren"
        for pat in ng.get("so_nganh", []):
            if norm(pat) in text:
                return "so_nganh"
        for pat in ng.get("khac", []):
            if norm(pat) in text:
                return "khac"
        return None

    def detect_ky_hieu(self, doc: Document) -> Optional[str]:
        """Tìm ký hiệu phòng/đơn vị (khớp key dài nhất trước).

        Ưu tiên số hiệu văn bản đến; nếu là văn bản trả lời/phúc đáp thì dò thêm
        ký hiệu của văn bản được trả lời trong nội dung (Mục IV).
        """
        keys = sorted(self.lookup["ky_hieu"].keys(), key=len, reverse=True)
        hay = norm(doc.so_hieu)
        for key in keys:
            if norm(key) in hay:
                return key
        if self._is_reply(doc):
            body = norm(doc.trich_yeu + " " + doc.noi_dung)
            for key in keys:
                if norm(key) in body:
                    return key
        return None

    def _is_reply(self, doc: Document) -> bool:
        t = norm(doc.trich_yeu + " " + doc.noi_dung)
        return any(k in t for k in ("tra loi", "phuc dap", "phan hoi"))

    def detect_khan(self, doc: Document, today: Optional[date] = None) -> bool:
        if doc.khan:
            return True
        if doc.han_thuc_hien and doc.han_thuc_hien != "hỏa tốc":
            try:
                d = date.fromisoformat(doc.han_thuc_hien)
                today = today or date.today()
                return (d - today).days <= 2
            except ValueError:
                pass
        return False

    def detect_linh_vuc(self, doc: Document) -> Optional[Dict[str, Any]]:
        """Nhận diện lĩnh vực theo từ khóa; trả entry có nhiều keyword khớp nhất."""
        hay = norm(doc.haystack())
        best: Optional[Dict[str, Any]] = None
        best_score = 0
        for entry in self.lookup["linh_vuc_phu_trach"]:
            score = sum(1 for kw in entry.get("keywords", []) if _contains(hay, kw))
            if score > best_score:
                best_score = score
                best = entry
        return best if best_score > 0 else None

    def count_linh_vuc(self, doc: Document, min_score: int = 2) -> int:
        """Đếm số lĩnh vực có >= min_score keyword khớp (dùng phát hiện 'tổng hợp nhiều lĩnh vực')."""
        hay = norm(doc.haystack())
        return sum(
            1
            for entry in self.lookup["linh_vuc_phu_trach"]
            if sum(1 for kw in entry.get("keywords", []) if _contains(hay, kw)) >= min_score
        )

    def is_giay_moi(self, doc: Document) -> bool:
        hay = norm(doc.haystack())
        return any(_contains(hay, kw) for kw in ["giấy mời", "kính mời", "mời dự", "mời họp"])

    # ------------------------------------------------------------------ #
    # Đánh giá rule
    # ------------------------------------------------------------------ #
    def _match_condition(self, rule: Dict[str, Any], doc: Document, features: Dict[str, Any]) -> bool:
        cond = rule.get("condition", {})
        ctype = cond.get("type")

        if ctype == "ky_hieu":
            return features["ky_hieu"] is not None

        if ctype == "giay_moi":
            return features["giay_moi"]

        if ctype == "khan":
            if not features["khan"]:
                return False
            return self._any_keyword(doc, cond.get("any_of", []))

        if ctype == "keywords":
            if cond.get("unless_khan") and features["khan"]:
                return False
            if cond.get("source") and not any(norm(s) in norm(doc.co_quan_ban_hanh) for s in cond["source"]):
                return False
            if cond.get("source_category") and features["source"] not in cond["source_category"]:
                return False
            if cond.get("all_of") and not self._all_keyword(doc, cond["all_of"]):
                return False
            return self._any_keyword(doc, cond.get("any_of", []))

        if ctype == "source":
            if features["source"] != cond.get("source"):
                return False
            lv = features.get("linh_vuc")
            if cond.get("linh_vuc"):
                if lv is None or lv["linh_vuc"] != cond["linh_vuc"]:
                    return False
                if cond.get("any_of") and not self._any_keyword(doc, cond["any_of"]):
                    return False
                return True
            if cond.get("linh_vuc_leader"):
                # tổng hợp nhiều lĩnh vực -> coi như GĐ phụ trách/tổng hợp
                if cond["linh_vuc_leader"] == "gd" and features.get("tong_hop"):
                    return True
                if lv is None:
                    return False
                leader_is_gd = str(lv.get("lanh_dao", "")).startswith("Giám đốc")
                if cond["linh_vuc_leader"] == "gd" and not leader_is_gd:
                    return False
                if cond["linh_vuc_leader"] == "pgd" and leader_is_gd:
                    return False
                return True
            return True

        return False

    def _any_keyword(self, doc: Document, keywords: List[str]) -> bool:
        if not keywords:
            return False
        hay = norm(doc.haystack())
        return any(_contains(hay, kw) for kw in keywords)

    def _all_keyword(self, doc: Document, keywords: List[str]) -> bool:
        if not keywords:
            return True
        hay = norm(doc.haystack())
        return all(_contains(hay, kw) for kw in keywords)

    # ------------------------------------------------------------------ #
    # Chạy engine
    # ------------------------------------------------------------------ #
    def run(self, doc: Document, today: Optional[date] = None) -> EngineResult:
        features = {
            "source": self.detect_source(doc),
            "ky_hieu": self.detect_ky_hieu(doc),
            "khan": self.detect_khan(doc, today),
            "linh_vuc": self.detect_linh_vuc(doc),
            "giay_moi": self.is_giay_moi(doc),
            "tong_hop": self.count_linh_vuc(doc) >= 2,
        }

        result = EngineResult(extracted=dict(features), han_thuc_hien=doc.han_thuc_hien)
        result.extracted["linh_vuc"] = (
            features["linh_vuc"]["linh_vuc"] if features["linh_vuc"] else None
        )

        matched_rule: Optional[Dict[str, Any]] = None
        for rule in self.rules:
            if self._match_condition(rule, doc, features):
                matched_rule = rule
                break

        if matched_rule is None:
            result.needs_review = True
            result.confidence = 0.0
            result.reason = (
                "Không có rule cứng nào khớp rõ ràng — cần model suy luận ngữ nghĩa "
                "hoặc người duyệt xác nhận."
            )
            return result

        result.matched_rules.append(matched_rule["id"])
        self._resolve_action(matched_rule, features, result)
        result.reason = f"Khớp rule {matched_rule['id']} — {matched_rule.get('name', '')}"

        if matched_rule.get("priority") in (1, 2):
            result.confidence = 0.95
        else:
            result.confidence = 0.85

        note = matched_rule.get("note")
        if note and "KIỂM CHỨNG" in note.upper():
            result.needs_review = True
        return result

    def _resolve_action(self, rule: Dict[str, Any], features: Dict[str, Any], result: EngineResult) -> None:
        action = rule.get("action", {})
        lv = features.get("linh_vuc") or {}
        ky_hieu = features.get("ky_hieu")
        ky_info = self.lookup["ky_hieu"].get(ky_hieu, {}) if ky_hieu else {}

        repl = {
            "{lanh_dao}": lv.get("lanh_dao", ""),
            "{don_vi}": (lv.get("don_vi") or [""])[0],
            "{ky_hieu.don_vi}": ky_info.get("don_vi", ""),
        }

        def resolve(tokens: List[str]) -> List[str]:
            out: List[str] = []
            for tok in tokens:
                out.append(repl.get(tok, tok))
            return [t for t in out if t]

        primary = resolve(action.get("primary", []))
        coordinator = resolve(action.get("coordinator", []))
        monitor = resolve(action.get("monitor", []))

        # ký hiệu có lãnh đạo kèm theo (Mục IV.3)
        if ky_hieu and ky_info.get("kem_lanh_dao"):
            primary = [ky_info["kem_lanh_dao"], *primary]

        result.don_vi_xu_ly_chinh = [self.normalize_person(t) for t in primary]
        result.phoi_hop_xu_ly = [self.normalize_person(t) for t in coordinator]
        result.lanh_dao_theo_doi = [self.normalize_person(t) for t in monitor]

    def normalize_person(self, name: str) -> str:
        """Chuẩn hóa tên viết tắt -> tên đầy đủ (nếu có trong danh bạ)."""
        return self.personnel.get(name, name)
