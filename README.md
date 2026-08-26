# AI Document Router — Sở NN&MT (Gia Lai)

Server AI định tuyến văn bản đến. Thiết kế chi tiết: [`thiet-ke-ai-document-router.md`](thiet-ke-ai-document-router.md).

## Hướng hoạt động (v3)

- **Đầu vào:** văn bản + file đính kèm (PDF). **Không có payload JSON** — mọi thông tin
  (số hiệu, loại, cơ quan ban hành, trích yếu, hạn thực hiện…) được trích tự động từ nội dung file.
- **Đầu ra:** 4 trường để chuyển văn bản đi:
  - `don_vi_xu_ly_chinh` — Đơn vị xử lý chính
  - `phoi_hop_xu_ly` — Phối hợp xử lý
  - `lanh_dao_theo_doi` — Lãnh đạo theo dõi
  - `han_thuc_hien` — Hạn thực hiện
- **Knowledge base:** rulebase riêng từng Sở (`app/rules/rules.yaml` cho SoNNMT).

## Kiến trúc

`PDF → trích text → trích metadata (regex + model) → rule engine deterministic → response 4 trường`

Harness tự hạ cấp `T2 → T1 → T0` khi model yếu/lỗi (rule engine luôn chạy độc lập).

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
# chỉ cần file đính kèm
curl -X POST http://127.0.0.1:8000/classify \
  -F "file=@van_ban.pdf"

# hoặc text thô (test/dev)
curl -X POST http://127.0.0.1:8000/classify \
  -F "text=CÔNG VĂN V/v xây dựng công trình thủy lợi"
```

## Chạy test

```bash
python -m unittest discover -s tests -v
```

## Sinh PDF (rulebase / kế hoạch)

```powershell
.venv\Scripts\python.exe tools\build_pdf.py      # sinh tools/rulebase.html
# rồi in bằng Chrome headless:
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --headless=new --no-pdf-header-footer --print-to-pdf="out.pdf" "file:///D:/GPHI/ai-document-router/tools/rulebase.html"
```

## Cấu trúc

```
app/
├── main.py                    # FastAPI entrypoint
├── api/routes.py              # POST /classify — nhận file đính kèm
├── pdf/extractor.py           # text extraction + fallback OCR
├── extract/metadata.py        # trích metadata + hạn thực hiện từ văn bản
├── rules/rules.yaml           # rulebase riêng từng Sở (SoNNMT)
├── rules/engine.py            # rule matcher deterministic
├── orchestrator/harness.py    # vòng lặp agent + fallback T2→T1→T0
├── orchestrator/skills/       # SKILL.md cho từng bước reasoning
├── models/schema.py           # Pydantic response 4 trường
└── storage/audit.py           # SQLite audit log
```
