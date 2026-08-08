# Server AI local — AI Document Router (deepseek-reasoner)

Server định tuyến văn bản đến cho **Sở Nông nghiệp và Môi trường tỉnh Gia Lai**,
triển khai theo thiết kế `doc/thiet-ke-ai-document-router.md` (giai đoạn demo local).

- **Core model:** `deepseek-reasoner` (DeepSeek API, OpenAI-compatible) — chỉ dùng
  cho phần rule không match rõ.
- **Rule engine:** code thuần, deterministic — nạp từ `app/rules/rules.yaml`
  (bản máy đọc của `doc/rulebase.md`), chạy nhanh/rẻ/dễ audit.
- **Không dùng RAG:** rulebase + từ điển lĩnh vực được nạp thẳng vào context LLM.
- **Audit:** mọi request/response được ghi vào SQLite (`app/storage/audit.db`).

> ⚠️ Không sửa `doc/`, `source/`, `README.md` — server chỉ **đọc** các tài liệu đó.
> Nếu muốn chạy hoàn toàn local/offline, trỏ `DEEPSEEK_BASE_URL` sang endpoint
> OpenAI-compatible của bạn (vd LM Studio/vLLM serve `deepseek-r1`) — xem `.env.example`.

## Cài đặt & chạy

```bat
cd d:\GPHI\ai-document-router

:: 1) Môi trường ảo + dependencies (chỉ lần đầu)
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

:: 2) Cấu hình key DeepSeek (bắt buộc nếu muốn dùng LLM)
copy .env.example .env
::   sửa .env: DEEPSEEK_API_KEY=sk-...

:: 3) Chạy server
.venv\Scripts\python -m app.main
::   hoặc: .venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Swagger UI: http://127.0.0.1:8000/docs

## Endpoint

| Method | Path             | Mô tả                                                            |
| ------ | ---------------- | ---------------------------------------------------------------- |
| GET    | `/health`        | Trạng thái server, model, LLM available                          |
| GET    | `/rules`         | Danh sách rule đang nạp (đối chiếu với rulebase.md)              |
| POST   | `/classify`      | **multipart**: 6 trường JSON + file PDF đính kèm                 |
| POST   | `/classify/json` | JSON thuần (không PDF) — tiện test nhanh                         |
| GET    | `/audit?limit=20`| Log SQLite gần nhất                                               |

### Ví dụ gọi /classify

```bat
curl -X POST http://127.0.0.1:8000/classify ^
  -F "so_van_ban=8682/SNNMT-CNTY" ^
  -F "loai_van_ban=Công văn" ^
  -F "co_quan_ban_hanh=Chi cục Chăn nuôi và Thú y" ^
  -F "nguoi_ky=Nguyễn Văn A" ^
  -F "ngay_van_ban=2026-08-05" ^
  -F "trich_yeu=V/v tăng cường kiểm tra, giám sát dịch bệnh động vật, vệ sinh thú y" ^
  -F "pdf=@source\8682_SNNMT-CNTY_04082026-signed.pdf"
```

## Demo nhanh không cần API key

```bat
.venv\Scripts\python scripts\demo.py            :: dùng PDF mẫu đầu tiên trong source/
.venv\Scripts\python scripts\demo.py --list     :: liệt kê PDF mẫu
.venv\Scripts\python scripts\demo.py "source\8680_SNNMT-CNTY_04082026-signed.pdf"
.venv\Scripts\python scripts\demo.py --no-llm   :: chỉ chạy rule engine
```

## Kiểm thử

```bat
.venv\Scripts\python -m pytest tests -v
```

## Cách hoạt động (pipeline)

```
POST /classify (6 trường + PDF)
  └─ PDF extractor (pypdf → fallback pdfplumber → OCR hook)
  └─ Harness:
       1. verify_metadata       đối chiếu payload với nội dung PDF
       2. rule_engine.evaluate  áp dụng rulebase theo thứ tự ưu tiên:
                                 Khẩn(V) → Ngoại lệ(IV) → Giấy mời(II.4)
                                 → Giao chủ trì(I) → Lĩnh vực(III)+Nguồn(II)
       3. Quyết định:
            confidence >= 0.80  → chốt rule engine, không gọi LLM
            confidence <  0.80  → gọi deepseek-reasoner suy luận (nếu có API key)
            không match         → gọi deepseek-reasoner từ đầu
       4. explain + audit log (SQLite)
```

## Điều chỉnh rule

Sửa `app/rules/rules.yaml` (admin), không cần đụng code. Keyword viết **thường,
không dấu** (engine tự bỏ dấu). Các phần: `exceptions` (Mục IV), `urgent` (Mục V),
`invitation` (II.4), `central_directive` (I/II.1), `field_routes` (Mục III).

## Ghi chú về model

- API DeepSeek hiện tại (2026) có model mới `deepseek-v4-flash`/`deepseek-v4-pro`
  với thinking mode (`thinking={"type":"enabled"}`); `deepseek-reasoner` là tên
  model reasoning truyền thống. Cả hai đều được hỗ trợ qua `DEEPSEEK_MODEL` +
  cơ chế thinking mode trong `app/llm/client.py`.
- deepseek-reasoner không dùng tool-call/agent loop — harness là pipeline
  tuần tự: rule engine trước, reasoning model chỉ cho phần mờ (đúng tinh thần
  "rule engine thuần + LLM cho phần không match rõ" trong thiết kế).
