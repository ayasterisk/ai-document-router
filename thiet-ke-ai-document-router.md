# Thiết kế Server AI Phân loại & Định tuyến Văn bản Đến

---

## 1. Bài toán

Xây dựng một server AI cho văn phòng, nhận request gồm:

- **Payload JSON** chứa 6 trường quan trọng của văn bản, cộng 1 trường tùy chọn:
  1. Số hiệu văn bản
  2. Loại văn bản
  3. Cơ quan ban hành
  4. Người ký
  5. Ngày văn bản
  6. Trích yếu văn bản
  7. **Hạn xử lý** (nullable) — dùng cho rule "văn bản khẩn còn 1–2 ngày"; nếu null thì bỏ qua nhánh khẩn (xem Mục 3.2)
- **File PDF** đính kèm (nội dung đầy đủ của văn bản)

**Đầu ra:** Danh sách các cơ quan chịu trách nhiệm tiếp nhận văn bản đó để thực hiện.

Kết quả được suy ra từ: đọc payload + đọc nội dung PDF + áp dụng **Rule** do admin cấu hình.

**Ràng buộc kỹ thuật:**

- Kiến trúc theo mô hình **Orchestration, Harness, Agent Skills** (điều phối vòng lặp gọi tool + skill theo bước), backend model là **open-weight model tự host tại công ty** (không gọi API model bên ngoài — xem Mục 3)
- **Không sử dụng RAG** — rule quản lý dạng rule engine tường minh, không phải retrieval ngữ nghĩa

---

## 2. Vì sao không dùng RAG

RAG phù hợp khi cần tìm kiếm trong kho tài liệu lớn, không biết trước phần nào liên quan. Ở đây rule do admin set là tập hữu hạn, có cấu trúc rõ ràng (điều kiện → cơ quan nhận). Nên xử lý bằng:

- **Rule engine dạng code thuần** (deterministic) cho các điều kiện rõ ràng — nhanh, rẻ, dễ audit, dự đoán được.
- **Model reasoning** (open-weight model tự host) chỉ can thiệp cho phần "mờ" — khi rule cứng không match rõ ràng và cần hiểu ngữ nghĩa nội dung văn bản (ví dụ trích yếu nói về nội dung không có từ khóa khớp chính xác với rule).
- Toàn bộ rule set (nếu không quá lớn) được **load thẳng vào context** của model khi cần reasoning, không qua bước retrieval/embedding.
- Với khối lượng dự kiến ~600 văn bản/ngày (Mục 8), nên tận dụng **prefix caching** mà vLLM/TGI hỗ trợ sẵn cho phần rule set/system prompt cố định — rule set không đổi giữa các văn bản trong cùng phiên xử lý, cache giúp giảm đáng kể độ trễ/tải GPU so với việc xử lý lại toàn bộ rule set cho từng văn bản.

---

## 3. Kiến trúc tổng thể

```
Client (payload 6 field + PDF)
        │
        ▼
[API Layer] — nhận request, validate, lưu file tạm, tạo job_id
        │
        ▼
[Harness / Agent Loop] — điều phối vòng lặp gọi tool của model
        │
        ├──> Tool: extract_pdf_content (trích text/OCR từ PDF)
        │
        ├──> Skill: verify_metadata (đối chiếu 6 field với nội dung PDF, phát hiện sai lệch)
        │
        ├──> Skill: classify_document (xác định đặc điểm văn bản: loại, mức độ, nội dung chính)
        │
        ├──> Tool: rule_engine.apply(fields, extracted_content)
        │         → chạy rule cứng (deterministic) trước
        │         → phần nào rule không match rõ ràng → đưa cho model reasoning
        │           dựa trên toàn bộ rule set (load thẳng vào context, không retrieval)
        │
        ├──> Skill: resolve_conflicts (nếu nhiều rule cùng match / mâu thuẫn)
        │
        └──> Skill: explain_decision (sinh lý do routing để admin kiểm tra/audit)
        │
        ▼
[Response Formatter] — trả JSON: danh sách cơ quan + độ tin cậy + lý do
```

### Vai trò từng thành phần

| Thành phần                                     | Vai trò                                                                                                                                                                         |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Harness**                                | Vòng lặp điều phối: gọi tool, xử lý lỗi/retry, giới hạn số bước, timeout khi PDF lớn/OCR chậm; tự hạ cấp theo thang fallback`T2 → T1 → T0` (xem Mục 3.2) |
| **Orchestration**                          | Điều phối nhiều skill theo trình tự có điều kiện (nếu verify_metadata phát hiện sai lệch → dừng, yêu cầu xác nhận thay vì tự động routing)               |
| **Agent Skills**                           | Đóng gói từng nghiệp vụ độc lập, dễ bảo trì/version riêng: `verify_metadata`, `classify_document`, `apply_rules`, `resolve_conflicts`, `explain_decision`    |
| **Rule Engine (code, không phải model)** | Xử lý phần rule tường minh, tách khỏi model để: nhanh, admin sửa rule không cần đụng prompt, audit dễ, dự đoán được                                         |
| **Inference Server (vLLM/TGI)**            | Chạy open-weight model tại chỗ, expose API tương thích OpenAI/Anthropic-style để Harness gọi tool use nội bộ, không cần Internet                                    |

### Kết nối mạng & bảo mật dữ liệu

Văn bản đến của Sở có thể thuộc loại nhạy cảm/mật, cần **không rời khỏi mạng nội bộ dưới bất kỳ hình thức nào** (đã chốt: **Phương án B — offline hoàn toàn**, không gọi API model bên ngoài, kể cả qua private link).

- **Tự host một open-weight model** ngay tại server đặt ở công ty, phục vụ inference qua **vLLM** hoặc **TGI (Text Generation Inference)** — chạy trên GPU on-prem, không có traffic đi ra Internet cho bước reasoning.
- Toàn bộ **Harness/Agent Loop**, **Rule Engine**, và **inference server** nằm trên cùng một máy/cụm máy vật lý tại công ty, hoàn toàn cách ly khỏi Internet công cộng nếu cần (air-gapped hoặc chỉ mở cổng nội bộ).
- Đánh đổi so với Phương án A (Bedrock/Vertex): mất khả năng dùng Claude qua API, phải tự chọn/benchmark một open-weight model đủ mạnh để xử lý rule **phức tạp/chồng chéo cần suy luận ngữ nghĩa** (đã xác nhận ở Mục 8) — xem Mục 3.1 bên dưới để đánh giá rủi ro này trước khi cam kết hạ tầng.
- Đổi lại: **không cần Internet ở bước gọi model**, đáp ứng yêu cầu bảo mật ở mức cao nhất.

#### 3.1. Rủi ro độ chính xác khi chuyển sang open-weight model — cần benchmark trước

Mục 8 đã xác nhận: rule của Sở **phức tạp, chồng chéo, cần suy luận ngữ nghĩa** khi rule cứng không match rõ ràng (đây chính là lý do thiết kế ban đầu chọn Claude qua Bedrock/Vertex). Các open-weight model hiện nay nhìn chung suy luận theo rule nhiều bước/ưu tiên chồng chéo yếu hơn model closed-source hàng đầu, và hỗ trợ tiếng Việt không đồng đều giữa các model.

**Trước khi cam kết mua GPU/hạ tầng**, nên chạy một bước **benchmark nội bộ** (khoảng 1 tuần, trước Phase 1 chính thức):

1. Chọn 2-3 ứng viên model để thử — ưu tiên theo 2 tiêu chí: (a) hỗ trợ tiếng Việt tốt, (b) có bản quyền cho phép dùng thương mại/nội bộ tại doanh nghiệp/cơ quan nhà nước. Nhóm model đáng cân nhắc ở thời điểm hiện tại: dòng **Qwen2.5/Qwen3** (đa ngôn ngữ tốt, có tiếng Việt), **Llama 3.3/4**, **DeepSeek-V3/R1** (mạnh về suy luận, cần kiểm tra license), và các bản distill nhỏ hơn nếu cần chạy trên GPU hạn chế. **Cần kiểm tra lại thông tin model mới nhất tại thời điểm triển khai thực tế** — lĩnh vực này thay đổi nhanh, danh sách trên chỉ là điểm khởi đầu tham khảo, không phải khuyến nghị cuối cùng.
2. Chạy 2-3 model ứng viên với **~50 test case suy từ rulebase** — case sinh từ các quy tắc định tuyến của `rulebaseSoNNMT.md` (Mục II/IV/V/VI) theo đúng thứ tự ưu tiên "Nguyên tắc áp dụng", gồm cả case chồng chéo (ví dụ: văn bản vừa trúng ngoại lệ vừa trúng quy tắc chung); *không* coi "mỗi dòng bảng = 1 case" vì nhiều dòng là bảng tra cứu tham chiếu — cộng thêm một số văn bản mẫu thật có case "mờ" cần suy luận.
3. So sánh độ chính xác giữa các model, và so với kỳ vọng ban đầu (đã test thử bằng Claude khi xây rulebase, nếu có). Nếu độ chính xác của open-weight model thấp hơn đáng kể, cân nhắc: model lớn hơn (cần GPU mạnh hơn), fine-tune nhẹ trên rule cụ thể của Sở, hoặc chấp nhận tỷ lệ flag-để-người-duyệt cao hơn ở các case mờ.

#### 3.2. Thiết kế Harness — cơ chế fallback khi model yếu / không hỗ trợ tool-calling

**Nguyên tắc cốt lõi:** Rule Engine là code deterministic và **luôn chạy độc lập, không phụ thuộc model**. Model chỉ tham gia phần "mờ" (phân loại lĩnh vực/nguồn gửi, suy luận khi rule không match rõ, giải thích). Nhờ tách bạch này, harness có thể **hạ cấp (degrade) dần mà kết quả vẫn hợp lệ** — trường hợp xấu nhất chỉ mất phần suy luận, rule cứng vẫn trả kết quả.

Harness hoạt động theo **3 bậc (tier)** và tự hạ cấp theo thang fallback khi bậc trên thất bại:

| Bậc                         | Cách gọi model                                                                                  | Dùng khi                                                   |
| ---------------------------- | ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| **T2 — Tool-calling** | Model tự gọi tool (`apply_rules`, `extract_pdf_content`…) qua vòng lặp agent             | Model hỗ trợ function-calling tốt (mặc định khi bật) |
| **T1 — Prompt-only**  | Gộp 6 field + nội dung PDF + toàn bộ rule set vào 1 prompt; model trả 1 JSON có cấu trúc | Model không hỗ trợ / không theo được tool-calling    |
| **T0 — Không model** | Chỉ chạy Rule Engine; phần không match rõ → flag để người duyệt                        | Model lỗi/timeout/parse hỏng vượt ngưỡng              |

**Thang fallback:** `T2 → T1 → T0`. Mỗi lần hạ cấp vẫn trả về response hợp lệ, kèm cờ `degraded` để audit biết kết quả đến từ bậc nào.

**Điều kiện kích hoạt fallback (hạ bậc):**

- **T2 → T1:** model không có khả năng tool-calling (đã xác định ở Mục 3.1), hoặc trả `tool_call` sai định dạng/sai tên tool/sai tham số sau **N lần retry** (mặc định N=2), hoặc vòng lặp tool vượt **max_steps** (mặc định 6).
- **T1 → T0:** model trả JSON không parse được sau retry, trả sai schema, timeout inference, hoặc inference server lỗi 5xx vượt ngưỡng.

**Hàng rào giảm fallback trước khi phải hạ cấp:**

1. **Ràng buộc đầu ra** — dùng guided decoding của vLLM (`guided_json`/xgrammar) hoặc JSON mode để ép model trả đúng schema, giảm tối đa lỗi parse.
2. **Retry có giới hạn** — retry cùng bậc với lỗi parse/timeout trước khi hạ cấp; không retry vô hạn.
3. **Schema thống nhất** — cả 3 bậc trả về cùng một cấu trúc JSON (danh sách đơn vị nhận + confidence + lý do + `matched_rules` + `needs_review` + `degraded`), nên API Layer/Response Formatter không cần biết kết quả đến từ bậc nào.

**Xử lý trường hợp `hạn xử lý = null`:** rule "văn bản khẩn còn 1–2 ngày" (Mục VI của rulebase SoNNMT) chỉ áp dụng khi `hạn xử lý` có giá trị. Nếu null → bỏ qua nhánh khẩn, xử lý theo luồng thường, đồng thời đặt `needs_review = true` (cờ nhẹ) để người dùng tự kiểm tra tính khẩn — không chặn định tuyến.

**Cấu hình (qua `.env` / config):**

- `HARNESS_TOOL_MODE = auto | native | prompt | off` — `auto` (mặc định): thăm dò khả năng tool-calling của model rồi chọn T2 hay T1.
- `HARNESS_MAX_TOOL_STEPS`, `HARNESS_RETRY`, `HARNESS_MODEL_TIMEOUT` — giới hạn vòng lặp/retry/timeout.

**Audit:** mỗi kết quả ghi lại `tier`, `degraded`, số lần retry, lý do hạ cấp (nếu có) vào `audit.db` để đo tần suất fallback — chỉ số này cũng là đầu vào cho việc chọn model ở Mục 3.1 (fallback xảy ra thường xuyên → model chưa đủ mạnh, cần chọn model lớn hơn hoặc fine-tune).

---

## 4. Explainability & Human review

Vì đây là hệ thống ra quyết định hành chính (định tuyến sai có thể gây hậu quả):

- Mỗi kết quả có **độ tin cậy** (rule match rõ ràng vs model suy luận)
- Trường hợp confidence thấp hoặc nhiều rule mâu thuẫn → **flag để người dùng xác nhận** thay vì tự động gửi
- Log đầy đủ lý do (rule nào match, hoặc model giải thích gì) để admin audit và tinh chỉnh rule theo thời gian

---

## 5. Cấu trúc project (giai đoạn demo local)

```
ai-doc-router/
├── app/
│   ├── main.py                 # FastAPI entrypoint
│   ├── api/
│   │   └── routes.py           # POST /classify — nhận payload + PDF
│   ├── pdf/
│   │   └── extractor.py        # text extraction, fallback OCR nếu cần
│   ├── rules/
│   │   ├── rules.yaml          # rule admin set (điều kiện → cơ quan)
│   │   └── engine.py           # rule matcher thuần code (deterministic)
│   ├── orchestrator/
│   │   ├── harness.py          # vòng lặp agent: gọi model (local, qua vLLM/TGI) + tool use
│   │   └── skills/              # SKILL.md cho từng bước reasoning
│   │       ├── verify_metadata.md
│   │       ├── classify_document.md
│   │       ├── apply_rules.md
│   │       ├── resolve_conflicts.md
│   │       └── explain_decision.md
│   ├── models/
│   │   └── schema.py           # Pydantic: request/response schema
│   └── storage/
│       └── audit.db            # SQLite log kết quả + lý do
├── tests/
├── requirements.txt
└── .env                        # INFERENCE_SERVER_URL (endpoint local vLLM/TGI, không có API key ra ngoài)
```

---

## 6. Tech stack đề xuất

- **API**: FastAPI (Python)
- **PDF extraction**: `pdfplumber` / `pypdf` cho PDF text-based; **Tesseract OCR** (offline) cho bản scan, hoặc self-host thêm một model vision-capable open-weight (ví dụ nhóm Qwen2-VL/InternVL — cần benchmark riêng) nếu OCR thường không đủ chính xác
- **Rule storage**: file YAML/JSON ban đầu, sau này có thể chuyển sang SQLite/Postgres + admin UI
- **Orchestration**: tự viết harness gọi tool use qua API tương thích OpenAI/Anthropic-style do **vLLM/TGI** cung cấp cho model tự host (tool-calling tùy khả năng model đã chọn ở Mục 3.1)
- **Model access**: **self-host open-weight model** (ứng viên: Qwen2.5/Qwen3, Llama 3.3/4, DeepSeek — cần benchmark lại tại thời điểm triển khai, xem Mục 3.1) qua **vLLM** hoặc **TGI**, chạy trên GPU on-prem đặt tại công ty — không gọi API model bên ngoài
- **Hạ tầng GPU**: cần xác định sau bước benchmark Mục 3.1 (model càng lớn/độ chính xác yêu cầu càng cao → GPU/VRAM càng lớn); tối thiểu nên tính phương án 1-2 GPU 24-48GB VRAM cho model tầm 7B-32B (có quantization), hoặc nhiều GPU/VRAM lớn hơn nếu chọn model 70B+
- **Audit/log**: SQLite (demo) → Postgres (production)

---

## 7. Lộ trình xây dựng

### Giai đoạn 1 — Demo trên máy cá nhân

1. **Skeleton API** — FastAPI với endpoint `POST /classify` nhận JSON (6 field) + file PDF (multipart), validate bằng Pydantic.
2. **PDF extractor** — bắt đầu với `pdfplumber`/`pypdf` cho PDF text-based; để sẵn hook OCR phòng trường hợp scan.
3. **Rule engine thuần code** — viết `rules.yaml` với vài rule mẫu, viết matcher Python test độc lập, không phụ thuộc model.
4. **Harness gọi model local** — đưa 6 field + nội dung PDF liên quan + rule active vào context, cho model dùng tool `apply_rules`, xử lý phần rule không match rõ bằng reasoning (qua vLLM/TGI, xem Mục 3.1 để chọn model cụ thể).
5. **Viết Agent Skills** — mỗi skill là 1 file hướng dẫn riêng, dễ chỉnh sửa từng phần mà không đụng cả prompt.
6. **Test end-to-end** với vài văn bản mẫu thật.
7. **Audit log** — lưu input, rule matched, output, lý do vào SQLite.

> Lưu ý (máy không có GPU): Giai đoạn 1 có thể phát triển mà không cần GPU — dùng **mock inference server** (trả response giả lập theo schema ở Mục 3.2) hoặc chạy model nhỏ/quantized trên CPU; chỉ bước 4 cần có 1 endpoint inference khả dụng để test vòng lặp harness. GPU on-prem chỉ bắt buộc ở Giai đoạn 2 (bước 11).

### Giai đoạn 2 — Triển khai server GPU tại công ty, chạy 24/24

8. Đóng gói Docker + docker-compose, quản lý secret qua `.env` (không còn API key model bên ngoài, nhưng vẫn cần secret cho DB/nội bộ nếu có).
9. Reverse proxy (Nginx) nếu cần expose HTTPS **trong mạng nội bộ** — không expose endpoint ra Internet công cộng.
10. Giám sát uptime, backup cấu hình rule, xử lý restart tự động (systemd/docker restart policy).
11. Cài đặt inference server (vLLM/TGI) trên GPU tại công ty, load model đã chọn sau bước benchmark ở Mục 3.1; cấu hình mạng nội bộ để Harness gọi thẳng inference server qua localhost/LAN, không cần Internet.

---

## 8. Các điểm còn cần xác nhận / làm rõ thêm

Những thông tin sau sẽ giúp tinh chỉnh kiến trúc chính xác hơn (rule engine đơn giản hay cần model reasoning nhiều, có cần OCR hay không):

- [X] **Loại PDF đầu vào**: chủ yếu là PDF gốc (text-based).
- [X] **Độ phức tạp của rule**: phức tạp/chồng chéo, cần suy luận ngữ nghĩa nội dung văn bản.
- [X] **Khối lượng xử lý dự kiến**: khoảng 600 văn bản/ngày; có thể xử lý theo batch.
- [X] **Output chi tiết**: cần tên cơ quan + mức ưu tiên + người xử lý cụ thể.
- [X] **Cơ chế xác nhận thủ công**: trước mắt chỉ cần output độ chính xác cao, review kết quả bằng thủ công sau (chưa cần cơ chế duyệt tự động trong hệ thống).
- [X] **Bảo mật dữ liệu**: văn bản thuộc loại nhạy cảm/mật, cần kiểm soát không rời khỏi mạng nội bộ. **Quyết định (đã chốt — Phương án B):** tự host open-weight model, chạy hoàn toàn offline tại server đặt ở công ty, không gọi API model bên ngoài dưới bất kỳ hình thức nào — xem Mục 3 "Kết nối mạng & bảo mật dữ liệu" và Mục 3.1 "Rủi ro độ chính xác cần benchmark trước".

---

## 9. Bước tiếp theo đề xuất

- **Trước tiên**: chạy benchmark model theo Mục 3.1 (~1 tuần) để chọn open-weight model đủ khả năng xử lý rule chồng chéo trước khi cam kết mua GPU.
- Scaffold code skeleton cho giai đoạn demo (FastAPI + rule engine + harness mẫu, gọi tới inference server local thay vì Bedrock/Vertex), hoặc
- Thu thập vài văn bản mẫu thật (payload + PDF) để thiết kế `rules.yaml` và bộ test benchmark sát với dữ liệu thực tế.
