# KẾ HOẠCH THỰC HIỆN — AI Document Router

## Sở Nông nghiệp và Môi trường tỉnh Gia Lai

> Phiên bản: v1.0 — Trạng thái: Giai đoạn demo local.

---

## 1. Mục tiêu

Xây dựng server AI **định tuyến văn bản đến**: nhận văn bản + file đính kèm (PDF), tự trích
thông tin từ nội dung, áp dụng rulebase của Sở, trả về kết quả để chuyển văn bản đi gồm 4 trường:

- **Đơn vị xử lý chính**
- **Phối hợp xử lý**
- **Lãnh đạo theo dõi**
- **Hạn thực hiện**

Không dùng RAG; rulebase quản lý tường minh riêng từng Sở; model open-weight tự host (offline).

---

## 2. Phạm vi giai đoạn đầu

- Triển khai cho **Sở NN&MT** trước.
- Đầu vào: PDF text-based (bản scan/OCR xử lý sau).
- Chạy local (mock inference server) → sau nâng lên GPU on-prem.

---

## 3. Các giai đoạn

| Giai đoạn | Nội dung | Kết quả |
|---|---|---|
| **GĐ1 — Demo local** | Skeleton API, PDF extractor, metadata extractor, rule engine, harness + mock model, audit log, test | Chạy được end-to-end trên máy cá nhân |
| **GĐ2 — Triển khai GPU** | Docker, Nginx nội bộ, vLLM/TGI + model benchmark, giám sát, backup | Chạy 24/24 tại công ty, offline |
| **GĐ3 — Mở rộng đa Sở** | Tách rulebase đa Sở, admin UI, chuẩn hóa danh bạ | Dùng cho nhiều Sở |

---

## 4. Công việc chi tiết — Giai đoạn 1 (demo local)

| # | Công việc | Deliverable | Trạng thái |
|---|---|---|---|
| 1 | Viết lại bản thiết kế (bỏ payload JSON, output 4 trường) | `thiet-ke-ai-document-router.md` | ✅ Xong |
| 2 | PDF extractor (text + hook OCR) | `app/pdf/extractor.py` | ✅ Xong |
| 3 | Metadata extractor (số hiệu, loại, cơ quan, ngày, trích yếu, hạn) | `app/extract/metadata.py` | ✅ Xong |
| 4 | Rule engine deterministic + `rules.yaml` SoNNMT | `app/rules/engine.py`, `app/rules/rules.yaml` | ✅ Xong |
| 5 | Harness fallback T2→T1→T0 + mock/HTTP inference | `app/orchestrator/harness.py` | ✅ Xong |
| 6 | API `POST /classify` (chỉ file đính kèm) + schema 4 trường | `app/api/routes.py`, `app/models/schema.py` | ✅ Xong |
| 7 | Audit log SQLite | `app/storage/audit.py` | ✅ Xong |
| 8 | Unit test + smoke test API | `tests/` (30 test) | ✅ Xong |
| 9 | Thu thập 20–30 văn bản mẫu thật, đánh giá độ chính xác | bộ test + báo cáo eval | ⏳ Chờ dữ liệu |
| 10 | Benchmark model (Qwen2.5/3, Llama…) | báo cáo chọn model | ⏳ Chờ GPU |

---

## 5. Công việc — Giai đoạn 2 (triển khai GPU)

| # | Công việc |
|---|---|
| 1 | Docker + docker-compose, secret qua `.env` |
| 2 | Reverse proxy Nginx trong mạng nội bộ (không expose Internet) |
| 3 | Cài vLLM/TGI trên GPU, load model đã benchmark |
| 4 | Giám sát uptime, backup rulebase, restart tự động |

---

## 6. Công việc — Giai đoạn 3 (mở rộng đa Sở)

| # | Công việc |
|---|---|
| 1 | Tách rulebase thành "một Sở = một bộ rule + danh bạ" |
| 2 | Thêm tham số/endpoint chọn Sở |
| 3 | Admin UI quản lý rule; chuẩn hóa danh bạ nhân sự |

---

## 7. Rủi ro & biện pháp

| Rủi ro | Mức | Biện pháp |
|---|---|---|
| Open-weight model yếu ở rule chồng chéo/tiếng Việt | Cao | Benchmark trước khi mua GPU; fine-tune nhẹ; tăng tỷ lệ flag người duyệt |
| Trích metadata từ PDF kém chính xác (cơ quan ban hành, người ký) | Trung bình | Deterministic regex + model fallback; eval trên văn bản thật |
| Dữ liệu rulebase chưa sạch (địa danh, ký hiệu, nhân sự) | Trung bình | Rà soát/chuẩn hóa trước khi vận hành |
| Văn bản mật rò rỉ | Cao | Offline hoàn toàn, VPC nội bộ, không Internet |

---

## 8. Tiêu chí hoàn thành (Giai đoạn 1)

- [x] `POST /classify` nhận file PDF, không cần payload JSON.
- [x] Trả đúng 4 trường kết quả.
- [x] Rule engine khớp đúng thứ tự ưu tiên của rulebase SoNNMT.
- [x] Test chạy xanh (30 test).
- [ ] Độ chính xác routing ≥ 90% trên bộ 30 văn bản mẫu thật (chờ dữ liệu).

---

## 9. Cột mốc

| Mốc | Thời gian dự kiến |
|---|---|
| Hoàn thiện skeleton + test (đã xong) | Phiên này |
| Bộ eval 30 văn bản thật | Khi có dữ liệu |
| Benchmark model | ~1 tuần sau khi có GPU |
| Triển khai GPU 24/24 | Sau khi chọn model |
