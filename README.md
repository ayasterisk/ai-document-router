# AI Document Router — Sở NN&MT (Gia Lai)

Server AI phân loại & định tuyến văn bản đến. Thiết kế chi tiết: [`thiet-ke-ai-document-router.md`](thiet-ke-ai-document-router.md).

## Kiến trúc (tóm tắt)

- **Rule engine deterministic** (`app/rules/engine.py` + `app/rules/rules.yaml`) chạy trước, xử lý rule tường minh theo thứ tự ưu tiên — nhanh, rẻ, audit được.
- **Model tự host** (vLLM/TGI) chỉ can thiệp phần "mờ" khi rule cứng không khớp rõ.
- **Harness** (`app/orchestrator/harness.py`) có thang fallback `T2 → T1 → T0`.

## Cài đặt & chạy

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt

# dev (không cần GPU): dùng mock inference server
uvicorn app.main:app --reload

# gắn model thật: đặt INFERENCE_SERVER_URL trong .env
```

### Gọi API

```bash
curl -X POST http://127.0.0.1:8000/classify \
  -F "so_hieu=123/SNNMT-TS" \
  -F "loai=Công văn" \
  -F "co_quan_ban_hanh=Cục Thuế tỉnh Gia Lai" \
  -F "nguoi_ky=Nguyễn Văn A" \
  -F "ngay_van_ban=2026-08-01" \
  -F "trich_yeu=Thông báo thu hồi đất do nợ thuế" \
  -F "file=@van_ban.pdf"
```

## Chạy test

```bash
python -m unittest discover -s tests -v
```

## Lưu ý khớp keyword

Engine khớp từ khóa dạng **substring** (sau khi bỏ dấu tiếng Việt). Các từ đơn âm ngắn
(ví dụ `hồ`, `ao`, `phá`) có thể gây false-positive (VD `hồ sơ` chứa `hồ`). Admin nên
tinh chỉnh danh sách `keywords` trong `app/rules/rules.yaml` dựa trên dữ liệu văn bản thật.

## Cấu trúc

```
app/
├── main.py                 # FastAPI entrypoint
├── api/routes.py           # POST /classify
├── pdf/extractor.py        # text extraction + hook OCR
├── rules/rules.yaml        # rule admin set (điều kiện → cơ quan)
├── rules/engine.py         # rule matcher deterministic
├── orchestrator/harness.py # vòng lặp agent + fallback T2→T1→T0
├── orchestrator/skills/    # SKILL.md cho từng bước reasoning
├── models/schema.py        # Pydantic request/response
└── storage/audit.py        # SQLite audit log
```
