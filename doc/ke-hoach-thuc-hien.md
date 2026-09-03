# KẾ HOẠCH THỰC HIỆN — AI Document Router

## Sở Nông nghiệp và Môi trường tỉnh Gia Lai

> Phiên bản: v1.1 — Trạng thái: Giai đoạn demo local.

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
- Đầu vào: PDF — cần xác minh SỚM tỷ lệ scan vs text gốc (bước 0) để chốt OCR có bắt buộc ở đầu hay không.
- Chạy local (mock inference server) → sau nâng lên GPU on-prem.

---

## 2a. Hạ tầng phần cứng & mô hình OCR (quyết định triển khai)

### Phần cứng
- **GPU:** NVIDIA GeForce **RTX 4090 — 24 GB GDDR6X VRAM**, băng thông ~1 008 GB/s. Đủ chạy mô hình VLM 7B ở FP16 (weights ~14 GB) hoặc bản lượng tử AWQ/GPTQ 4-bit (~5 GB weights).
- Card consumer: không ECC, không NVLink, single-GPU → phù hợp phục vụ **một model thường trú tại một thời điểm** (hoặc OCR VLM + model định tuyến nhỏ/lượng tử).

### Mô hình OCR
- **OCR bản scan:** **Qwen2.5-VL-7B-Instruct** (vision-language 7B, context 125K), phục vụ qua **vLLM** (API tương thích OpenAI, offline on-prem).
- Vai trò: trích toàn văn bản từ ảnh scan, chất lượng cao hơn Tesseract (đọc bảng, chữ ký, tiếng Việt tốt hơn).
- Tham khảo cộng đồng (cần benchmark lại khi triển khai): trên RTX 4090 bản tối ưu ghi nhận ~18.2 GB VRAM, độ trễ <1.8 s/ảnh.

### Ngân sách VRAM & xung đột 2 model
- Chạy đồng thời **Qwen2.5-VL-7B (OCR)** và **model định tuyến (T1/T2)** trên **cùng 1 GPU 24 GB** sẽ cạnh tranh VRAM. Khuyến nghị:
  1. Ưu tiên OCR VLM thường trú — phần lớn văn bản đi qua rule engine **T0 deterministic**, không cần model định tuyến.
  2. Model định tuyến chỉ tải khi cần (time-share) hoặc dùng bản nhỏ/lượng tử (Qwen2.5-7B-Instruct AWQ 4-bit), giới hạn batch + context.
  3. Khi lưu lượng tăng → bổ sung GPU thứ hai để tách OCR vs reasoning.

### Cấu hình vLLM gợi ý (server OCR, cổng 8001)
```bash
vllm serve Qwen/Qwen2.5-VL-7B-Instruct \
  --dtype bfloat16 \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.90 \
  --port 8001
```
Client kết nối qua `OCR_SERVER_URL=http://127.0.0.1:8001` (xem `.env.example`).

---

## 3. Các giai đoạn

| Giai đoạn | Nội dung | Kết quả |
|---|---|---|
| **GĐ1 — Demo local** | Skeleton API, PDF extractor, metadata extractor, rule engine, harness + mock model, audit log, test | Chạy được end-to-end trên máy cá nhân |
| **GĐ2 — Triển khai GPU** | Docker, Nginx nội bộ, vLLM serve **Qwen2.5-VL-7B (OCR)** + model định tuyến trên **RTX 4090**, giám sát, backup | Chạy 24/24 tại công ty, offline |
| **GĐ3 — Mở rộng đa Sở** | Tách rulebase đa Sở, admin UI, chuẩn hóa danh bạ | Dùng cho nhiều Sở |

---

## 4. Công việc chi tiết — Giai đoạn 1 (demo local)

| # | Công việc | Deliverable | Trạng thái |
|---|---|---|---|
| 0 | **Thu thập 20–30 văn bản mẫu thật + xác minh OCR** (làm TRƯỚC) | bộ mẫu + kết luận OCR (text vs scan) | ⏳ Chờ dữ liệu |
| 1 | Viết lại bản thiết kế (bỏ payload JSON, output 4 trường) | `thiet-ke-ai-document-router.md` | ✅ Xong |
| 2 | PDF extractor (text + OCR Qwen2.5-VL-7B + Tesseract fallback) | `app/pdf/extractor.py` | ✅ Xong |
| 3 | Metadata extractor (số hiệu, loại, cơ quan, ngày, trích yếu, hạn) | `app/extract/metadata.py` | ✅ Xong |
| 4 | Rule engine deterministic + `rules.yaml` SoNNMT | `app/rules/engine.py`, `app/rules/rules.yaml` | ✅ Xong |
| 5 | Harness fallback T2→T1→T0 + mock/HTTP inference | `app/orchestrator/harness.py` | ✅ Xong |
| 6 | API `POST /classify` (chỉ file đính kèm) + schema 4 trường | `app/api/routes.py`, `app/models/schema.py` | ✅ Xong |
| 7 | Audit log SQLite | `app/storage/audit.py` | ✅ Xong |
| 8 | Unit test + smoke test API | `tests/` (30 test) | ✅ Xong |
| 8a | Refactor rule sang chức danh + bảng nhân sự riêng | `rules.yaml` + bảng nhân sự | ⏳ Đề xuất |
| 8b | Validate/sanitize output model (chống prompt injection) | guard trong `harness.py` | ⏳ Đề xuất |
| 9 | Thu thập 20–30 văn bản mẫu thật, đánh giá độ chính xác | bộ test + báo cáo eval | ⏳ Chờ dữ liệu |
| 10 | Benchmark model định tuyến (Qwen2.5/3, Llama…) + **Qwen2.5-VL-7B OCR** — SONG SONG từ bước 4 | báo cáo chọn model | ⏳ Chờ GPU |

---

## 5. Công việc — Giai đoạn 2 (triển khai GPU)

| # | Công việc |
|---|---|
| 1 | Docker + docker-compose, secret qua `.env` |
| 2 | Reverse proxy Nginx trong mạng nội bộ (không expose Internet) |
| 3 | Cài vLLM trên RTX 4090: serve **Qwen2.5-VL-7B-Instruct** (OCR, cổng 8001) |
| 4 | Serve model định tuyến (bậc T1/T2) — tách tiến trình / time-share với OCR VLM |
| 5 | Giám sát uptime, backup rulebase, restart tự động |

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
| Văn bản scan phổ biến, text extract kém | Cao | Xác minh OCR sớm (bước 0); Qwen2.5-VL-7B (vLLM) + Tesseract fallback |
| Cạnh tranh VRAM giữa OCR VLM và model định tuyến trên 1× RTX 4090 | Cao | OCR VLM thường trú; model định tuyến time-share/lượng tử; thêm GPU khi tải cao |
| Rule theo tên người lỗi thời khi luân chuyển | Trung bình | Rule theo chức danh + bảng nhân sự cập nhật riêng |
| Prompt injection từ nội dung văn bản | Thấp–Trung bình | Rule engine deterministic + validate/sanitize output model |
| Trách nhiệm khi AI định tuyến sai | Cao | Quy trình sign-off do lãnh đạo chốt |

---

## 8. Tiêu chí hoàn thành (Giai đoạn 1)

- [x] `POST /classify` nhận file PDF, không cần payload JSON.
- [x] Trả đúng 4 trường kết quả.
- [x] Rule engine khớp đúng thứ tự ưu tiên của rulebase SoNNMT.
- [x] Test chạy xanh (30 test).
- [ ] Độ chính xác trích metadata ≥ 95% (bộ 30 văn bản mẫu thật).
- [ ] Độ chính xác routing ≥ 90% (bộ 30 văn bản mẫu thật).
- [ ] Tỷ lệ `needs_review` ≤ 20% (case "mờ").

---

## 9. Cột mốc

| Mốc | Thời gian dự kiến |
|---|---|
| Hoàn thiện skeleton + test (đã xong) | Phiên này |
| Xác minh OCR + bộ 30 văn bản mẫu thật | Bước 0 (làm trước) |
| Bộ eval 30 văn bản thật | Khi có dữ liệu |
| Benchmark model | ~1 tuần sau khi có GPU |
| Triển khai GPU 24/24 | Sau khi chọn model |
| Serve Qwen2.5-VL-7B OCR trên RTX 4090 | Khi có GPU |
