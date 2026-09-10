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

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from app.extract.sections import routing_text


# --------------------------------------------------------------------------- #
# Chuẩn hóa text
# --------------------------------------------------------------------------- #
def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt + gập 'đ'->'d' để so khớp khoan dung hơn."""
    normalized = unicodedata.normalize("NFD", text)
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    return normalized.replace("đ", "d").replace("Đ", "d").lower()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(text)).strip()


_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _contains(hay_norm: str, keyword: str) -> bool:
    """Khớp keyword trong haystack đã chuẩn hóa.

    - Từ đơn (không chứa khoảng trắng) -> khớp token chính xác (tránh 'hồ'->'ho'
      khớp nhầm 'không'/'họp').
    - Cụm từ -> khớp đầy đủ ranh giới từ, chuẩn hóa khoảng trắng.
    """
    kw = norm(keyword)
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", hay_norm))


def _source_matches(source_norm: str, pattern: str) -> bool:
    """Match a source hint without treating a fragment of a larger word as a hit.

    A few source hints are intentionally written as prefixes (for example
    ``"bộ "`` and ``"sở "``).  ``norm(pattern) in source_norm`` turns those
    into the fragments ``"bo"`` and ``"so"``, which can match words such as
    ``"công bố"``.  Preserve the prefix intent: these hints must start the
    issuing-organization value, and ``"bộ phận"`` is not an agency name.
    """
    raw_pattern = str(pattern)
    keyword = norm(raw_pattern)
    if not keyword:
        return False
    if raw_pattern[-1:].isspace():
        return bool(
            re.search(
                r"^"
                + re.escape(keyword)
                + r"(?!\s+phan\b)\s",
                source_norm,
            )
        )
    return _contains(source_norm, keyword)


# --------------------------------------------------------------------------- #
# Model dữ liệu
# --------------------------------------------------------------------------- #
@dataclass
class Document:
    so_hieu: str = ""
    loai: str = ""
    co_quan_ban_hanh: str = ""
    nguoi_ky: str = ""
    ngay_van_ban: date | None = None
    trich_yeu: str = ""
    noi_dung: str = ""  # toàn bộ text đã trích
    han_thuc_hien: str | None = None  # "YYYY-MM-DD" hoặc None
    khan: bool = False  # dấu hiệu khẩn (khẩn/hỏa tốc, hoặc hạn <= 2 ngày)

    def haystack(self) -> str:
        return " ".join([self.trich_yeu, routing_text(self.noi_dung)])


@dataclass
class EngineResult:
    don_vi_xu_ly_chinh: list[str] = field(default_factory=list)
    phoi_hop_xu_ly: list[str] = field(default_factory=list)
    lanh_dao_theo_doi: list[str] = field(default_factory=list)
    han_thuc_hien: str | None = None
    confidence: float = 0.0
    reason: str = ""
    matched_rules: list[str] = field(default_factory=list)
    needs_review: bool = False
    extracted: dict[str, Any] = field(default_factory=dict)
    review_reasons: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
class RuleEngine:
    def __init__(self, rules_path: Path | str):
        self.rules_path = Path(rules_path)
        with open(self.rules_path, "r", encoding="utf-8") as fh:
            self.data: dict[str, Any] = yaml.safe_load(fh)
        self.rules: list[dict[str, Any]] = self.data["rules"]
        self.lookup: dict[str, Any] = self.data.get("lookup", {})
        self.personnel: dict[str, str] = self.data.get("personnel", {})
        self.version = self.data["meta"]["version"]
        self.fingerprint = hashlib.sha256(self.rules_path.read_bytes()).hexdigest()
        ids = [r["id"] for r in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate rule IDs")
        for rule in self.rules:
            if rule.get("condition", {}).get("type") not in {
                "ky_hieu",
                "giay_moi",
                "khan",
                "keywords",
                "source",
            }:
                raise ValueError(f"Invalid rule type: {rule['id']}")
            allowed = {
                "type",
                "none_of",
                "any_of",
                "all_of",
                "document_types",
                "tong_hop",
                "source",
                "source_category",
                "source_prefixes",
                "unless_khan",
                "linh_vuc",
                "linh_vuc_leader",
            }
            unknown = set(rule["condition"]) - allowed
            if unknown:
                raise ValueError(
                    f"Unknown conditions in {rule['id']}: {sorted(unknown)}"
                )
            action = rule.get("action", {})
            if set(action) - {"primary", "coordinator", "monitor"}:
                raise ValueError(f"Unknown action in {rule['id']}")
            placeholders = {"{lanh_dao}", "{don_vi}", "{ky_hieu.don_vi}"}
            for values in action.values():
                if not isinstance(values, list) or any(
                    not isinstance(v, str) for v in values
                ):
                    raise ValueError(f"Invalid action list in {rule['id']}")
                if any("{" in v and v not in placeholders for v in values):
                    raise ValueError(f"Unknown placeholder in {rule['id']}")
        # đảm bảo duyệt đúng thứ tự ưu tiên, giữ thứ tự khai báo khi cùng priority
        ordered = sorted(
            enumerate(self.rules),
            key=lambda t: (t[1].get("priority", 999), t[1].get("order", 100), t[0]),
        )
        self.rules = [rule for _, rule in ordered]

    # ------------------------------------------------------------------ #
    # Nhận diện đặc điểm
    # ------------------------------------------------------------------ #
    def detect_source(self, doc: Document) -> str | None:
        """Phân loại nguồn gửi: cap_tren | so_nganh | khac | None (không rõ)."""
        text = norm(doc.co_quan_ban_hanh)
        ng = self.lookup["nguon_gui"]

        for pat in ng.get("specific_so_nganh", []):
            if _source_matches(text, pat):
                return "so_nganh"
        for pat in ng.get("cap_tren", []):
            if _source_matches(text, pat):
                return "cap_tren"
        for pat in ng.get("so_nganh", []):
            if _source_matches(text, pat):
                return "so_nganh"
        for pat in ng.get("khac", []):
            if _source_matches(text, pat):
                return "khac"
        return None

    def detect_ky_hieu(self, doc: Document) -> str | None:
        """Chỉ trả một ký hiệu có bằng chứng quan hệ trả lời/tổng hợp (Mục IV)."""
        references = self.reply_references(doc)
        keys = {ref["key"] for ref in references}
        return next(iter(keys)) if len(keys) == 1 else None

    def reply_references(self, doc: Document) -> list[dict[str, str]]:
        text = norm(doc.trich_yeu + "\n" + doc.noi_dung)
        refs = []
        for key in self.lookup["ky_hieu"]:
            for match in re.finditer(
                r"\b\d{1,7}/" + re.escape(norm(key)) + r"(?![a-z0-9-])", text
            ):
                before = text[max(0, match.start() - 100) : match.start()]
                after = text[match.end() : match.end() + 250]
                direct = re.search(
                    r"(?:tra loi|phuc dap|phan hoi|tong hop theo|bao cao theo)\s+(?:cong van|van ban)?\s*(?:so)?\s*$",
                    before,
                )
                exchange = (
                    "can cu cong van so" in before
                    and "trao doi ket qua" in after
                    and "tong hop" in after
                )
                if direct or exchange:
                    refs.append(
                        {
                            "key": key,
                            "reference": match.group(),
                            "evidence": before + match.group() + after,
                        }
                    )
        return refs

    def detect_khan(self, doc: Document, today: date | None = None) -> bool:
        if doc.khan:
            return True
        if doc.han_thuc_hien:
            try:
                d = date.fromisoformat(doc.han_thuc_hien)
                today = today or datetime.now(timezone(timedelta(hours=7))).date()
                return 0 <= (d - today).days <= 2
            except ValueError:
                pass
        return False

    def detect_linh_vuc(self, doc: Document) -> dict[str, Any] | None:
        """Nhận diện lĩnh vực theo từ khóa; trả entry có nhiều keyword khớp nhất."""
        hay = norm(doc.haystack())
        best: dict[str, Any] | None = None
        best_score = 0
        for entry in self.lookup["linh_vuc_phu_trach"]:
            score = sum(1 for kw in entry.get("keywords", []) if _contains(hay, kw))
            if score > best_score:
                best_score = score
                best = entry
        return best if best_score > 0 else None

    def domain_evidence(self, doc: Document) -> list[dict[str, Any]]:
        hay = norm(doc.haystack())
        return [
            {"linh_vuc": entry["linh_vuc"], "keywords": hits, "score": len(hits)}
            for entry in self.lookup["linh_vuc_phu_trach"]
            if (hits := [kw for kw in entry.get("keywords", []) if _contains(hay, kw)])
        ]

    def count_linh_vuc(self, doc: Document, min_score: int = 2) -> int:
        """Đếm số lĩnh vực có >= min_score keyword khớp (dùng phát hiện 'tổng hợp nhiều lĩnh vực')."""
        hay = norm(doc.haystack())
        return sum(
            1
            for entry in self.lookup["linh_vuc_phu_trach"]
            if sum(1 for kw in entry.get("keywords", []) if _contains(hay, kw))
            >= min_score
        )

    def is_giay_moi(self, doc: Document) -> bool:
        if norm(doc.loai) == "giay moi":
            return True
        hay = norm(doc.trich_yeu or routing_text(doc.noi_dung)[:350])
        return any(_contains(hay, kw) for kw in ["kính mời", "mời dự", "mời họp"])

    # ------------------------------------------------------------------ #
    # Đánh giá rule
    # ------------------------------------------------------------------ #
    def _match_condition(
        self, rule: dict[str, Any], doc: Document, features: dict[str, Any]
    ) -> bool:
        cond = rule.get("condition", {})
        ctype = cond.get("type")
        if cond.get("source_prefixes") and not any(
            norm(doc.co_quan_ban_hanh).startswith(norm(p) + " ")
            for p in cond["source_prefixes"]
        ):
            return False
        if cond.get("none_of") and self._any_keyword(doc, cond["none_of"]):
            return False
        if cond.get("document_types") and norm(doc.loai) not in [
            norm(t) for t in cond["document_types"]
        ]:
            return False
        if (
            cond.get("tong_hop") is not None
            and features["tong_hop"] != cond["tong_hop"]
        ):
            return False

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
            if cond.get("source") and not any(
                _contains(norm(doc.co_quan_ban_hanh), s) for s in cond["source"]
            ):
                return False
            if (
                cond.get("source_category")
                and features["source"] not in cond["source_category"]
            ):
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
                return not (
                    cond.get("any_of") and not self._any_keyword(doc, cond["any_of"])
                )
            if cond.get("linh_vuc_leader"):
                # tổng hợp nhiều lĩnh vực -> coi như GĐ phụ trách/tổng hợp
                if features.get("tong_hop"):
                    return cond["linh_vuc_leader"] == "gd"
                if lv is None:
                    return False
                leader_is_gd = str(lv.get("lanh_dao", "")).startswith("Giám đốc")
                if cond["linh_vuc_leader"] == "gd" and not leader_is_gd:
                    return False
                return not (cond["linh_vuc_leader"] == "pgd" and leader_is_gd)
            return True

        return False

    def _any_keyword(self, doc: Document, keywords: list[str]) -> bool:
        if not keywords:
            return False
        hay = norm(doc.haystack())
        return any(_contains(hay, kw) for kw in keywords)

    def _all_keyword(self, doc: Document, keywords: list[str]) -> bool:
        if not keywords:
            return True
        hay = norm(doc.haystack())
        return all(_contains(hay, kw) for kw in keywords)

    # ------------------------------------------------------------------ #
    # Chạy engine
    # ------------------------------------------------------------------ #
    def run(self, doc: Document, today: date | None = None) -> EngineResult:
        features = {
            "source": self.detect_source(doc),
            "ky_hieu": self.detect_ky_hieu(doc),
            "khan": self.detect_khan(doc, today),
            "linh_vuc": self.detect_linh_vuc(doc),
            "giay_moi": self.is_giay_moi(doc),
            "tong_hop": self.count_linh_vuc(doc) >= 2,
            "domain_evidence": self.domain_evidence(doc),
            "reply_references": self.reply_references(doc),
        }

        result = EngineResult(extracted=dict(features), han_thuc_hien=doc.han_thuc_hien)
        if len({r["key"] for r in features["reply_references"]}) > 1:
            result.review_reasons.append("ambiguous_reply_reference")
        if doc.han_thuc_hien:
            try:
                if date.fromisoformat(doc.han_thuc_hien) < (
                    today or datetime.now(timezone(timedelta(hours=7))).date()
                ):
                    result.review_reasons.append("overdue_deadline")
            except ValueError:
                result.review_reasons.append("invalid_deadline")
        result.extracted["linh_vuc"] = (
            features["linh_vuc"]["linh_vuc"] if features["linh_vuc"] else None
        )

        matched_rule: dict[str, Any] | None = None
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
        result.reason = (
            f"Khớp rule {matched_rule['id']} — {matched_rule.get('name', '')}"
        )

        if matched_rule.get("priority") in (1, 2):
            result.confidence = 0.95
        else:
            result.confidence = 0.85

        ky_info = self.lookup["ky_hieu"].get(features["ky_hieu"], {})
        lv = features["linh_vuc"] or {}
        if matched_rule.get("requires_review") or ky_info.get("requires_review"):
            result.review_reasons.append("unverified_rule_mapping")
        if matched_rule["condition"]["type"] == "source" and lv.get("requires_review"):
            result.review_reasons.append("unverified_domain_mapping")
        evidence = features["domain_evidence"]
        if (
            matched_rule["priority"] == 5
            and len(evidence) > 1
            and not features["tong_hop"]
        ):
            scores = sorted((e["score"] for e in evidence), reverse=True)
            if scores[0] == scores[1]:
                result.review_reasons.append("ambiguous_domain")
        if not result.don_vi_xu_ly_chinh:
            result.review_reasons.append("missing_primary_recipient")
        result.needs_review = bool(result.review_reasons)
        if result.needs_review:
            result.confidence = min(result.confidence, 0.5)
        return result

    def _resolve_action(
        self, rule: dict[str, Any], features: dict[str, Any], result: EngineResult
    ) -> None:
        action = rule.get("action", {})
        lv = features.get("linh_vuc") or {}
        ky_hieu = features.get("ky_hieu")
        ky_info = self.lookup["ky_hieu"].get(ky_hieu, {}) if ky_hieu else {}

        repl = {
            "{lanh_dao}": lv.get("lanh_dao", ""),
            "{ky_hieu.don_vi}": ky_info.get("don_vi", ""),
        }

        units = lv.get("don_vi", [])
        hits = {
            norm(kw)
            for entry in features["domain_evidence"]
            for kw in entry["keywords"]
        }
        selections = [
            entry["units"]
            for entry in lv.get("unit_rules", [])
            if any(norm(kw) in hits for kw in entry["keywords"])
        ]
        if selections:
            units = list(
                dict.fromkeys(unit for selection in selections for unit in selection)
            )
        elif len(units) > 1 and lv.get("unit_mode") != "all":
            units = []
            if "{don_vi}" in action.get("primary", []):
                result.review_reasons.append("ambiguous_advisory_unit")

        def resolve(tokens: list[str]) -> list[str]:
            out: list[str] = []
            for tok in tokens:
                if tok == "{don_vi}":
                    out.extend(units)
                else:
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

    def recipient_names(self) -> list[str]:
        names = set(self.personnel.values())
        for rule in self.rules:
            for values in rule.get("action", {}).values():
                names.update(self.normalize_person(v) for v in values if "{" not in v)
        for entry in self.lookup["linh_vuc_phu_trach"]:
            names.add(self.normalize_person(entry["lanh_dao"]))
            names.update(entry["don_vi"])
        for entry in self.lookup["ky_hieu"].values():
            if entry.get("don_vi"):
                names.add(self.normalize_person(entry["don_vi"]))
        return sorted(names)
