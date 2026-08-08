"""Unit test rule engine — deterministic, không cần API key."""

from app.models.schema import DocumentPayload
from app.rules.engine import RuleEngine, vn_normalize


def make_payload(**kw):
    defaults = dict(
        so_van_ban="",
        loai_van_ban="Công văn",
        co_quan_ban_hanh="",
        nguoi_ky="",
        ngay_van_ban="2026-08-08",
        trich_yeu="",
    )
    defaults.update(kw)
    return DocumentPayload(**defaults)


def test_vn_normalize_bo_dau():
    assert vn_normalize("Sở Nông nghiệp và Môi trường") == "so nong nghiep va moi truong"
    assert vn_normalize("Đồng Nai & Gia Lai") == "dong nai va gia lai"


def test_ngoai_le_khieu_nai():
    p = make_payload(
        co_quan_ban_hanh="Công dân Nguyễn Văn A",
        trich_yeu="Đơn đề nghị giải quyết khiếu nại về đất đai",
    )
    res = RuleEngine().evaluate(p)
    assert res.has_match
    assert res.matched_rules[0].rule_id == "IV.2"
    assert any("Phạm Quý Phương" in r["ten"] for r in res.recipients)
    assert res.confidence >= 0.9


def test_ngoai_le_so_tai_chinh_tham_dinh():
    p = make_payload(
        co_quan_ban_hanh="Sở Tài chính tỉnh Gia Lai",
        trich_yeu="V/v thẩm định dự án đầu tư",
    )
    res = RuleEngine().evaluate(p)
    assert res.matched_rules[0].rule_id == "IV.9"
    assert any("Phòng KH-TC" in r["ten"] for r in res.recipients)


def test_giay_moi():
    p = make_payload(
        co_quan_ban_hanh="UBND tỉnh Gia Lai",
        trich_yeu="Giấy mời tham dự cuộc họp triển khai nhiệm vụ",
    )
    res = RuleEngine().evaluate(p)
    assert res.matched_rules[0].rule_id == "II.4"
    assert any("Đặng Phi Trường" in r["ten"] for r in res.recipients)


def test_giao_chu_tri_giam_doc_but_phe():
    p = make_payload(
        co_quan_ban_hanh="UBND tỉnh Gia Lai",
        trich_yeu="V/v giao Sở Nông nghiệp và Môi trường chủ trì xử lý",
    )
    res = RuleEngine().evaluate(p)
    assert res.central_directive
    first = res.recipients[0]
    assert first["vai_tro"] == "bút phê trước"
    assert "Giám đốc" in first["ten"]


def test_linh_vuc_chan_nuoi_thu_y():
    p = make_payload(
        co_quan_ban_hanh="Cục Thú y",
        trich_yeu="V/v tăng cường kiểm tra dịch bệnh động vật, vệ sinh thú y",
    )
    res = RuleEngine().evaluate(p)
    assert res.has_match
    assert any("Đoàn Ngọc Có" in r["ten"] for r in res.recipients)


def test_dat_dai_qldd_vs_vpdk():
    # giao đất -> Chi cục QLĐĐ
    p1 = make_payload(
        co_quan_ban_hanh="UBND tỉnh Gia Lai",
        so_van_ban="8708/SNNMT-QLDD",
        trich_yeu="V/v giao đất, cho thuê đất đối với các thửa đất nhỏ hẹp",
    )
    res1 = RuleEngine().evaluate(p1)
    assert res1.has_match
    assert any("Chi cục Quản lý đất đai" in r["ten"] for r in res1.recipients)
    assert not any("Văn phòng Đăng ký" in r["ten"] for r in res1.recipients)

    # đăng ký đất đai lần đầu -> VPĐK
    p2 = make_payload(
        co_quan_ban_hanh="Sở Tài nguyên và Môi trường",
        so_van_ban="8609/SNNMT-VPDK",
        trich_yeu="V/v kê khai, đăng ký đất đai lần đầu",
    )
    res2 = RuleEngine().evaluate(p2)
    assert res2.has_match
    assert any("Văn phòng Đăng ký đất đai" in r["ten"] for r in res2.recipients)


def test_van_ban_khan_chuyen_song_song():
    p = make_payload(
        loai_van_ban="Công văn khẩn",
        co_quan_ban_hanh="UBND tỉnh Gia Lai",
        trich_yeu="V/v ứng phó mưa lũ, phòng chống lụt bão",
    )
    res = RuleEngine().evaluate(p)
    assert res.urgent
    assert any("song song" in r["vai_tro"] for r in res.recipients)
    assert any("Vũ Ngọc An" in r["ten"] for r in res.recipients)


def test_no_match_tra_confidence_thap():
    p = make_payload(
        co_quan_ban_hanh="Công ty TNHH ABC",
        trich_yeu="V/v đề nghị hỗ trợ xúc tiến thương mại sản phẩm",
    )
    res = RuleEngine().evaluate(p)
    assert not res.has_match
    assert res.confidence == 0.0
