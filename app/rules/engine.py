"""Rule engine — matcher thuần code, deterministic (không phụ thuộc LLM).

Triển khai "Nguyên tắc áp dụng" của doc/rulebase.md:
  1. Ngoại lệ đặc biệt (Mục IV)      4. Giao chủ trì / TB kết luận (Mục I, II.1)
  2. Văn bản khẩn (Mục V)            5. Quy tắc chung theo nguồn (Mục II.1-II.3)
  3. Giấy mời (Mục II.4)            + lĩnh vực phụ trách (Mục III)

Mọi văn bản (tiếng Việt) được chuẩn hóa: bỏ dấu, lowercase, nén khoảng trắng,
"&" -> " va " trước khi so khớp keyword (keyword trong rules.yaml cùng quy ước).
"""

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from app.models.schema import DocumentPayload

RULES_PATH = Path(__file__).parent / "rules.yaml"

# --------------------------------------------------------------------------
# Chuẩn hóa tiếng Việt
# --------------------------------------------------------------------------
VN_DIACRITIC_MAP = {
    "à": "a", "á": "a", "ả": "a", "ã": "a", "ạ": "a",
    "ă": "a", "ằ": "a", "ắ": "a", "ẳ": "a", "ẵ": "a", "ặ": "a",
    "â": "a", "ầ": "a", "ấ": "a", "ẩ": "a", "ẫ": "a", "ậ": "a",
    "è": "e", "é": "e", "ẻ": "e", "ẽ": "e", "ẹ": "e",
    "ê": "e", "ề": "e", "ế": "e", "ể": "e", "ễ": "e", "ệ": "e",
    "ì": "i", "í": "i", "ỉ": "i", "ĩ": "i", "ị": "i",
    "ò": "o", "ó": "o", "ỏ": "o", "õ": "o", "ọ": "o",
    "ô": "o", "ồ": "o", "ố": "o", "ổ": "o", "ỗ": "o", "ộ": "o",
    "ơ": "o", "ờ": "o", "ớ": "o", "ở": "o", "ỡ": "o", "ợ": "o",
    "ù": "u", "ú": "u", "ủ": "u", "ũ": "u", "ụ": "u",
    "ư": "u", "ừ": "u", "ứ": "u", "ử": "u", "ữ": "u", "ự": "u",
    "ỳ": "y", "ý": "y", "ỷ": "y", "ỹ": "y", "ỵ": "y",
    "đ": "d",
}

_EXTRA_REPLACE = str.maketrans({"&": " va ", "–": " ", "—": " ", "\u00a0": " "})


def vn_normalize(text: str) -> str:
    """Chuẩn hóa tiếng Việt để so khớp: bỏ dấu, lowercase, nén khoảng trắng."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", str(text))
    text = text.lower().translate(_EXTRA_REPLACE)
    out = []
    for ch in text:
        out.append(VN_DIACRITIC_MAP.get(ch, ch))
    text = "".join(out)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _matches_any(keywords: List[str], haystack: str) -> List[str]:
    """Trả danh sách keyword khớp (substring) trong haystack đã chuẩn hóa."""
    return [kw for kw in keywords if kw in haystack]


# --------------------------------------------------------------------------
# Dữ liệu trả về
# --------------------------------------------------------------------------
@dataclass
class RuleMatch:
    rule_id: str
    name: str
    reason: str
    confidence: float


@dataclass
class EngineResult:
    recipients: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    matched_rules: List[RuleMatch] = field(default_factory=list)
    method: str = "rule_engine"
    notes: List[str] = field(default_factory=list)
    source_category: Optional[str] = None  # II.1 | II.2 | II.3
    field_leader: Optional[str] = None
    central_directive: bool = False
    urgent: bool = False

    @property
    def has_match(self) -> bool:
        return self.confidence > 0.0 and bool(self.recipients)


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------
class RuleEngine:
    def __init__(self, rules_path: Path = RULES_PATH):
        self.path = rules_path
        with open(rules_path, "r", encoding="utf-8") as f:
            self.rules = yaml.safe_load(f) or {}
        self.trace: List[Dict[str, Any]] = []  # trace các bước ưu tiên khi evaluate

    def _trace(self, event: str, **details: Any) -> None:
        entry: Dict[str, Any] = {"event": event}
        entry.update(details)
        self.trace.append(entry)

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _recips(raw: List[Dict[str, Any]], rule_id: str) -> List[Dict[str, Any]]:
        out = []
        for r in raw:
            out.append(
                {
                    "ten": r["ten"],
                    "vai_tro": r.get("vai_tro", "xử lý chính"),
                    "muc_uu_tien": r.get("muc_uu_tien", 1),
                    "nguon": rule_id,
                }
            )
        return out

    @staticmethod
    def _match_ma_ky_hieu(so_van_ban_norm: str) -> Optional[Dict[str, str]]:
        """Trích mã ký hiệu đơn vị từ số văn bản, vd: 8682/SNNMT-CNTY -> CNTY."""
        table = {
            "kl": {"don_vi": "Chi cục Kiểm lâm", "lanh_dao": "PGĐ Nguyễn Văn Hoan", "linh_vuc": "Lâm nghiệp, Kiểm lâm"},
            "qldd": {"don_vi": "Chi cục Quản lý đất đai", "lanh_dao": "Giám đốc Cao Thanh Thương", "linh_vuc": "Quản lý đất đai"},
            "cnty": {"don_vi": "Chi cục Chăn nuôi và Thú y", "lanh_dao": "PGĐ Đoàn Ngọc Có", "linh_vuc": "Chăn nuôi và Thú y"},
            "tnn": {"don_vi": "Phòng Tài nguyên nước và KTTV", "lanh_dao": "PGĐ Vũ Ngọc An", "linh_vuc": "Tài nguyên nước, KTTV"},
            "vpdk": {"don_vi": "Văn phòng Đăng ký đất đai", "lanh_dao": "Giám đốc Cao Thanh Thương", "linh_vuc": "Đăng ký đất đai"},
        }
        for code, info in table.items():
            if code in so_van_ban_norm:
                return info
        return None

    # -- các bước ưu tiên -------------------------------------------------
    def _step_exceptions(self, combined: str, sender_norm: str) -> Optional[EngineResult]:
        for exc in self.rules.get("exceptions", []):
            sender_kws = [vn_normalize(k) for k in exc.get("sender_keywords", [])]
            if sender_kws and not any(k in sender_norm for k in sender_kws):
                continue  # rule yêu cầu đúng cơ quan gửi
            hits = _matches_any([vn_normalize(k) for k in exc.get("keywords", [])], combined)
            if hits:
                conf = float(exc.get("confidence", 0.95))
                return EngineResult(
                    recipients=self._recips(exc["recipients"], exc["id"]),
                    confidence=conf,
                    matched_rules=[
                        RuleMatch(exc["id"], exc["name"], f"Khớp keyword: {', '.join(hits[:3])}", conf)
                    ],
                )
        return None

    def _step_urgent(self, combined: str, loai_norm: str) -> Optional[EngineResult]:
        tokens = set(loai_norm.split()) | set(combined.split())
        detect = self.rules.get("urgent", {}).get("detect_tokens", [])
        if not any(t in tokens for t in detect):
            return None
        for route in self.rules.get("urgent", {}).get("routes", []):
            hits = _matches_any([vn_normalize(k) for k in route.get("keywords", [])], combined)
            if hits:
                conf = float(route.get("confidence", 0.95))
                return EngineResult(
                    recipients=self._recips(route["recipients"], route["id"]),
                    confidence=conf,
                    urgent=True,
                    matched_rules=[
                        RuleMatch(route["id"], "Văn bản khẩn — chuyển song song",
                                  f"Khớp keyword: {', '.join(hits[:3])}", conf)
                    ],
                )
        return None

    def _step_invitation(self, combined: str) -> Optional[EngineResult]:
        inv = self.rules.get("invitation", {})
        hits = _matches_any([vn_normalize(k) for k in inv.get("keywords", [])], combined)
        if hits:
            conf = float(inv.get("confidence", 0.95))
            return EngineResult(
                recipients=self._recips(inv["recipients"], "II.4"),
                confidence=conf,
                matched_rules=[
                    RuleMatch("II.4", "Giấy mời / nội dung như giấy mời",
                              f"Khớp keyword: {', '.join(hits[:3])}", conf)
                ],
            )
        return None

    def _classify_source(self, sender_norm: str) -> str:
        """Mục II — phân loại nguồn gửi: II.1 TW/UBND tỉnh; II.2 sở, ngành; II.3 xã/tổ chức/doanh nghiệp."""
        central = ["chinh phu", "thu tuong", "tinh uy", "ban thuong vu", "ubnd tinh",
                   "hoi dong nhan dan", "quoc hoi", "van phong chinh phu", "trung uong"]
        dept = ["so nong nghiep", "so tai chinh", "so ", "cuc ", "chi cuc", "trung tam ",
                "cong an", "vien kiem sat", "toa an", "mat tran", "ban quan ly", "kho bac"]
        if any(k in sender_norm for k in central):
            return "II.1"
        if any(k in sender_norm for k in dept):
            return "II.2"
        return "II.3"

    def _step_fields(self, combined: str, sender_norm: str, so_norm: str) -> Optional[EngineResult]:
        """Mục III — chấm điểm theo độ dài keyword (cụ thể hơn -> nặng hơn)."""
        scored: List[Tuple[float, Dict[str, Any], List[str], Optional[List[str]], str]] = []
        for fr in self.rules.get("field_routes", []):
            hits = _matches_any([vn_normalize(k) for k in fr.get("keywords", [])], combined)
            if not hits:
                continue
            score = float(max(len(k) for k in hits))
            sub_units: Optional[List[str]] = None
            sub_id = fr["id"]
            for sub in fr.get("sub_routes", []):
                shits = _matches_any([vn_normalize(k) for k in sub.get("keywords", [])], combined)
                if shits:
                    sub_units = sub["don_vi"]
                    sub_id = sub["id"]
                    # phân nhánh đất đai QLĐĐ/VPĐK: cộng thêm độ đặc tả của sub-keyword
                    score += max(len(k) for k in shits) / 100.0
                    break
            scored.append((score, fr, hits, sub_units, sub_id))

        if not scored:
            return None

        # tín hiệu mã ký hiệu: cộng 4 điểm cho leader trùng mã đơn vị
        mkh = self._match_ma_ky_hieu(so_norm)
        if mkh:
            scored = [
                (score + 4.0, fr, hits, sub, sid)
                if fr["lanh_dao"] == mkh["lanh_dao"]
                else (score, fr, hits, sub, sid)
                for (score, fr, hits, sub, sid) in scored
            ]

        scored.sort(key=lambda x: -x[0])
        top_score = scored[0][0]
        top_routes = [s for s in scored if abs(s[0] - top_score) < 0.0001]

        # tổng hợp nhiều lĩnh vực: nhiều leader khác nhau cùng đỉnh điểm
        if len(top_routes) > 1 and len({r[1]["lanh_dao"] for r in top_routes}) > 1:
            return self._result_tong_hop(sender_norm)

        best = top_routes[0]
        _, fr, hits, sub_units, sub_id = best
        don_vi = sub_units or fr.get("don_vi", [])
        source = self._classify_source(sender_norm)
        recipients = self._build_by_source(source, fr["lanh_dao"], fr["cap"], don_vi)

        conf = 0.82 + min(0.06, top_score / 100.0)
        if mkh and mkh["lanh_dao"] == fr["lanh_dao"]:
            conf = min(0.93, conf + 0.04)
        if source in ("II.1", "II.2"):
            conf = min(0.93, conf + 0.02)
        conf = round(min(0.95, conf), 3)

        mkh_note = f"; mã ký hiệu: {so_norm.split('/')[-1]}" if mkh else ""
        matched = RuleMatch(
            sub_id if sub_units else fr["id"],
            f"Lĩnh vực phụ trách ({fr['lanh_dao']})",
            f"Khớp keyword: {', '.join(hits[:4])}{mkh_note}",
            conf,
        )
        return EngineResult(
            recipients=recipients,
            confidence=conf,
            matched_rules=[matched],
            source_category=source,
            field_leader=fr["lanh_dao"],
            notes=[] if len(top_routes) == 1 else ["Nhiều lĩnh vực khớp — nên kiểm tra thủ công"],
        )

    def _build_by_source(self, source: str, leader: str, cap: str, don_vi: List[str]) -> List[Dict[str, Any]]:
        """Mục II — quy tắc chung theo nguồn gửi + lĩnh vực."""
        recips: List[Dict[str, Any]] = []
        if cap == "GĐ":
            if source == "II.1":
                recips.append({"ten": leader, "vai_tro": "xử lý chính", "muc_uu_tien": 1, "nguon": "II.1"})
                for u in don_vi:
                    recips.append({"ten": u, "vai_tro": "xử lý chính", "muc_uu_tien": 1, "nguon": "II.1"})
            elif source == "II.2":
                recips.append({"ten": "Chánh Văn phòng Sở", "vai_tro": "xử lý chính", "muc_uu_tien": 1, "nguon": "II.2"})
                for u in don_vi:
                    recips.append({"ten": u, "vai_tro": "xử lý chính", "muc_uu_tien": 1, "nguon": "II.2"})
                recips.append({"ten": leader, "vai_tro": "theo dõi", "muc_uu_tien": 2, "nguon": "II.2"})
            else:  # II.3
                for u in don_vi:
                    recips.append({"ten": u, "vai_tro": "xử lý chính", "muc_uu_tien": 1, "nguon": "II.3"})
                recips.append({"ten": "Chánh Văn phòng Sở", "vai_tro": "phối hợp", "muc_uu_tien": 2, "nguon": "II.3"})
        else:  # PGĐ
            recips.append({"ten": leader, "vai_tro": "xử lý chính", "muc_uu_tien": 1, "nguon": "II"})
            for u in don_vi:
                recips.append({"ten": u, "vai_tro": "xử lý chính", "muc_uu_tien": 1, "nguon": "II"})
            if source == "II.1":
                recips.append({"ten": "Giám đốc Sở (Cao Thanh Thương)", "vai_tro": "theo dõi", "muc_uu_tien": 2, "nguon": "II.1"})
        return recips

    # -- entry point ------------------------------------------------------
    def evaluate(self, payload: DocumentPayload, pdf_text: str = "") -> EngineResult:
        combined = vn_normalize((payload.trich_yeu or "") + " " + (pdf_text or ""))
        loai_norm = vn_normalize(payload.loai_van_ban or "")
        sender_norm = vn_normalize(payload.co_quan_ban_hanh or "")
        so_norm = vn_normalize(payload.so_van_ban or "")

        self.trace = []  # reset trace mỗi lần evaluate
        self._trace(
            "input",
            so_van_ban=payload.so_van_ban,
            loai_van_ban=payload.loai_van_ban,
            co_quan_ban_hanh=payload.co_quan_ban_hanh,
            nguoi_ky=payload.nguoi_ky,
            trich_yeu=payload.trich_yeu,
            pdf_chars=len(pdf_text or ""),
            combined_norm=combined[:200],
            sender_norm=sender_norm,
            so_norm=so_norm,
        )

        # 1. Văn bản khẩn (Mục V) — chuyển SONG SONG.
        #    Lưu ý: kiểm tra TRƯỚC ngoại lệ IV.10/IV.11 vì chúng có keyword trùng
        #    với Mục V; nếu để ngoại lệ trước thì quy tắc "khẩn -> song song"
        #    không bao giờ có hiệu lực cho thủy lợi/thủy sản. (Quyết định triển khai)
        res = self._step_urgent(combined, loai_norm)
        if res:
            self._trace("step", step="1_urgent(Muc_V)", matched=True,
                        rule=[r.rule_id for r in res.matched_rules],
                        recipients=[r["ten"] for r in res.recipients],
                        confidence=res.confidence)
            return res
        self._trace("step", step="1_urgent(Muc_V)", matched=False)

        # 2. Ngoại lệ đặc biệt (Mục IV)
        res = self._step_exceptions(combined, sender_norm)
        if res:
            self._trace("step", step="2_exception(Muc_IV)", matched=True,
                        rule=[r.rule_id for r in res.matched_rules],
                        recipients=[r["ten"] for r in res.recipients],
                        confidence=res.confidence)
            return res
        self._trace("step", step="2_exception(Muc_IV)", matched=False)

        # 3. Giấy mời (Mục II.4)
        res = self._step_invitation(combined)
        if res:
            self._trace("step", step="3_invitation(II.4)", matched=True,
                        rule=[r.rule_id for r in res.matched_rules],
                        recipients=[r["ten"] for r in res.recipients],
                        confidence=res.confidence)
            return res
        self._trace("step", step="3_invitation(II.4)", matched=False)

        # 4. Giao chủ trì / Thông báo kết luận (Mục I, II.1) -> GĐ bút phê trước
        central_hits = _matches_any(
            [vn_normalize(k) for k in self.rules.get("central_directive", {}).get("keywords", [])], combined
        )
        self._trace("step", step="4_central_directive(I/II.1)",
                    matched=bool(central_hits), keywords=central_hits[:3])

        # 5. Lĩnh vực phụ trách (Mục III)
        res = self._step_fields(combined, sender_norm, so_norm)
        if res:
            if central_hits:
                res.central_directive = True
                gd = {"ten": "Giám đốc Sở (Cao Thanh Thương)", "vai_tro": "bút phê trước", "muc_uu_tien": 0, "nguon": "II.1.chutri"}
                if not any(r["ten"] == gd["ten"] for r in res.recipients):
                    res.recipients.insert(0, gd)
                res.confidence = min(0.95, res.confidence + 0.02)
                res.matched_rules.insert(
                    0,
                    RuleMatch("II.1.chutri", "Giao chủ trì / Thông báo kết luận — Giám đốc bút phê trước",
                              f"Khớp keyword: {', '.join(central_hits[:2])}", 0.9),
                )
            self._trace("step", step="5_field(Muc_III)", matched=True,
                        rule=[r.rule_id for r in res.matched_rules],
                        source_category=res.source_category,
                        field_leader=res.field_leader,
                        recipients=[r["ten"] for r in res.recipients],
                        confidence=res.confidence,
                        notes=res.notes)
            return res
        self._trace("step", step="5_field(Muc_III)", matched=False)

        # 4b. Giao chủ trì nhưng chưa xác định lĩnh vực -> GĐ bút phê trước
        if central_hits:
            self._trace("step", step="4b_central_only", matched=True,
                        recipients=["Giám đốc Sở (bút phê trước)"], confidence=0.82)
            return EngineResult(
                recipients=[{
                    "ten": "Giám đốc Sở (Cao Thanh Thương)",
                    "vai_tro": "bút phê trước",
                    "muc_uu_tien": 0,
                    "nguon": "II.1.chutri",
                }],
                confidence=0.82,
                central_directive=True,
                matched_rules=[
                    RuleMatch("II.1.chutri", "Giao chủ trì / Thông báo kết luận — Giám đốc bút phê trước",
                              f"Khớp keyword: {', '.join(central_hits[:2])}", 0.9)
                ],
                notes=["Sau khi Giám đốc bút phê cần xác định lĩnh vực để chuyển đơn vị (có thể dùng LLM)"],
            )

        # Không rule nào match rõ -> confidence thấp -> harness quyết định gọi LLM
        self._trace("step", step="no_match", matched=False)
        return EngineResult(
            confidence=0.0,
            matched_rules=[
                RuleMatch("NO_MATCH", "Không khớp rule cứng",
                          "Cần suy luận ngữ nghĩa (deepseek-reasoner) để xác định lĩnh vực", 0.0)
            ],
            notes=["Không khớp rule cứng — chuyển sang reasoning model"],
        )


engine = RuleEngine()



