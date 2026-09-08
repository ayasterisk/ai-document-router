# AI Document Router — SoNNMT

Backend FastAPI đề xuất phân luồng văn bản đến cho Sở Nông nghiệp và Môi trường. Client Tampermonkey do nhóm khác phụ trách; repository cung cấp API và hợp đồng tích hợp, không thao tác giao diện hoặc gửi văn bản thay người dùng.

Luồng: **PDF/text → kiểm tra từng trang → metadata/ngữ cảnh → rule SoNNMT → đề xuất có bằng chứng → người dùng duyệt/chỉnh → ghi nhận feedback**. Không có model thì chạy rule và yêu cầu duyệt phần chưa rõ. Model không được tự bỏ qua duyệt.

## Chạy

Python 3.12 được dùng để kiểm thử. Tạo môi trường mới nếu `.venv` cũ trỏ tới Python đã bị di chuyển.

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
# Sinh token ngẫu nhiên, điền vào ROUTER_API_KEYS trong .env:
.venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

`.env` được nạp tự động, biến môi trường có ưu tiên cao hơn. Không chạy nhiều ASGI workers trên cùng SQLite: khóa tiến trình sẽ từ chối instance thứ hai. `ROUTER_MAX_WORKERS` là số tác vụ xử lý đồng thời trong backend, độc lập với `uvicorn --workers`.

Môi trường đã tạo trong lượt hoàn thiện ở máy hiện tại: `.venv-review`. Có thể dùng `.venv-review/Scripts/python.exe` để chạy các lệnh trên thay vì `.venv/Scripts/python.exe`.

Mặc định `.env.example` tắt OCR và model. Để đọc scan, cấu hình OCR nội bộ, dùng `OCR_PROVIDER=qwen-vl` hoặc `auto`. Raster PDF dùng PDFium, không cần Poppler. Fallback Tesseract cần cài thêm `pytesseract`, binary Tesseract và dữ liệu tiếng Việt `vie`. Bản scan thiếu nội dung được đánh dấu cần duyệt hoặc thất bại; không xem chuỗi rác là thành công.

## API dành cho nhóm tích hợp

Tất cả endpoint nghiệp vụ dùng header `X-API-Key`; mỗi tài khoản tích hợp có token riêng. `/health` công khai chỉ xác nhận tiến trình đang trả lời.

| Endpoint | Chức năng |
|---|---|
| `GET /ready` | Kiểm tra DB/cấu hình đang hoạt động |
| `GET /v1/directory` | Danh bạ ID ổn định và phiên bản |
| `POST /v1/jobs` | Upload PDF hoặc text, nhận 202 và job_id |
| `GET /v1/jobs/{job_id}` | Lấy trạng thái và kết quả |
| `POST /v1/jobs/{job_id}/feedback` | Ghi nhận chấp nhận/chỉnh sửa/từ chối |
| `POST /classify` | Endpoint đồng bộ tương thích, cùng xác thực và giới hạn |

Swagger: `/docs`. Hợp đồng chi tiết, ví dụ và ánh xạ màn hình: **[doc/api-integration.md](doc/api-integration.md)**. Snapshot OpenAPI: [doc/openapi.json](doc/openapi.json).

```powershell
curl.exe -X POST http://127.0.0.1:8000/v1/jobs `
  -H "X-API-Key: YOUR_TOKEN" -H "Idempotency-Key: DOC-9634-r1" `
  -F "document_id=9634" -F "received_on=2026-09-08" -F "file=@vanban.pdf"
```

`document_id` là ID bản ghi đang mở trên hệ thống Sở, khác số hiệu văn bản. Client giữ ID này để tránh điền kết quả của văn bản cũ vào văn bản mới.

## Định tuyến và kiểm chứng

- Rule cụ thể được ưu tiên trong cùng nhóm; sửa V.8b, VI.4, tổng hợp, KH-TC/TCCB cấp trên và BĐKH.
- Keyword có ranh giới từ; phân vùng nhiệm vụ giao Sở và loại nơi nhận/căn cứ khỏi nhận diện lĩnh vực.
- IV cần bằng chứng quan hệ trả lời/tổng hợp với số văn bản viện dẫn; không tự dùng ký hiệu văn bản đến.
- Hạn là ISO date hoặc null; độ khẩn là trường riêng. Nhiều hạn hoặc hạn tương đối chưa giải quyết được phải duyệt.
- VPĐK chưa xác nhận: không đưa ra người nhận tự động. Pháp chế, đơn vị tham mưu chưa rõ hoặc dữ liệu thiếu cũng gắn cờ duyệt.
- ID danh bạ được lưu cố định trong `app/rules/directory.json`. Khi đổi tên, giữ ID cũ; không sinh lại ID theo tên mới.
- `confidence` là điểm heuristic chưa hiệu chuẩn; không dùng như xác suất đúng. `requires_confirmation=true` áp dụng cho mọi kết quả trong giai đoạn này.

[Chi tiết thay đổi nghiệp vụ và điểm cần Sở xác nhận](doc/SoNNMT/implementation-notes.md).

## Test và đánh giá

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe tools/evaluate.py --output output/evaluation-approved.json
.venv/Scripts/python.exe tools/evaluate.py --include-proposed --output output/evaluation-proposed.json
```

Bộ test bao gồm hồi quy nghiệp vụ, metadata, fallback model, PDF pha trộn text/scan, API qua subprocess, hàng đợi, timeout và audit. `tests/gold/sonnmt.json` là bộ nhãn **đề xuất**, chưa được văn thư nghiệm thu; các trường hợp thiếu căn cứ để đáp án null. Mặc định evaluator chỉ tính nhãn `business_approved`; chưa có nhãn được duyệt thì accuracy=null. `--mode pdf` đánh giá đầu-cuối PDF theo cấu hình OCR hiện tại; mặc định `excerpt` chỉ đánh giá engine trên metadata/trích đoạn.

`tools/test_vb.py` là công cụ chẩn đoán độ khớp, không đo accuracy. Không dùng số lượng rule khớp để kết luận định tuyến đúng.

## Triển khai

Máy chủ nội bộ: reverse proxy HTTPS → FastAPI một ASGI worker → hàng đợi giới hạn → subprocess riêng cho từng job → OCR/inference nội bộ. Bind FastAPI vào loopback khi reverse proxy cùng máy. Giới hạn mặc định: 20 MiB tổng file, 5 file, 50 trang, 200.000 ký tự, 2 job chạy, tối đa 8 job chờ/chạy, 300 giây/job.

SQLite lưu job, metadata/kết quả, toàn văn đã trích và feedback. Khi khởi động lại, job dang dở được đánh failed với `server_restarted`, không giả vờ hoàn tất. Dữ liệu hết hạn 30 ngày được dọn khi khởi động; chạy lịch bảo trì trong [doc/api-integration.md](doc/api-integration.md) nếu dịch vụ chạy liên tục. Chỉ cấp quyền đọc thư mục DB cho tài khoản dịch vụ/quản trị; backup theo quy định của Sở. PDF gốc không được lưu lâu dài trong backend.

Bản này chưa được đo tải trên máy chủ đích, chưa kiểm chứng OCR/model thật và chưa tích hợp với script của nhóm khác. Việc nghiệm thu danh bạ, quy tắc và bộ gold là bước triển khai nghiệp vụ tiếp theo.
