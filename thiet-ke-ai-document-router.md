# Thiết kế Server AI Phân loại & Định tuyến Văn bản Đến

> Trạng thái: Ý tưởng cá nhân — đang ở giai đoạn demo local, sẽ triển khai lên VM chạy 24/24 sau khi hoàn chỉnh.

---

## 1. Bài toán

Xây dựng một server AI cho văn phòng, nhận request gồm:
- **Payload JSON** chứa 6 trường quan trọng của văn bản:
  1. Số hiệu văn bản
  2. Loại văn bản
  3. Cơ quan ban hành
  4. Người ký
  5. Ngày văn bản
  6. Trích yếu văn bản
- **File PDF** đính kèm (nội dung đầy đủ của văn bản)

**Đầu ra:** Danh sách các cơ quan chịu trách nhiệm tiếp nhận văn bản đó để thực hiện.

Kết quả được suy ra từ: đọc payload + đọc nội dung PDF + áp dụng **Rule** do admin cấu hình.

**Ràng buộc kỹ thuật:**
- Sử dụng Claude Orchestration, Harness, Agent Skills
- **Không sử dụng RAG** — rule quản lý dạng rule engine tường minh, không phải retrieval ngữ nghĩa

---

## 2. Vì sao không dùng RAG

RAG phù hợp khi cần tìm kiếm trong kho tài liệu lớn, không biết trước phần nào liên quan. Ở đây rule do admin set là tập hữu hạn, có cấu trúc rõ ràng (điều kiện → cơ quan nhận). Nên xử lý bằng:
- **Rule engine dạng code thuần** (deterministic) cho các điều kiện rõ ràng — nhanh, rẻ, dễ audit, dự đoán được.
- **Claude reasoning** chỉ can thiệp cho phần "mờ" — khi rule cứng không match rõ ràng và cần hiểu ngữ nghĩa nội dung văn bản (ví dụ trích yếu nói về nội dung không có từ khóa khớp chính xác với rule).
- Toàn bộ rule set (nếu không quá lớn) được **load thẳng vào context** của Claude khi cần reasoning, không qua bước retrieval/embedding.

---

## 3. Kiến trúc tổng thể

```
Client (payload 6 field + PDF)
        │
        ▼
[API Layer] — nhận request, validate, lưu file tạm, tạo job_id
        │
        ▼
[Harness / Agent Loop] — điều phối vòng lặp gọi tool của Claude
        │
        ├──> Tool: extract_pdf_content (trích text/OCR từ PDF)
        │
        ├──> Skill: verify_metadata (đối chiếu 6 field với nội dung PDF, phát hiện sai lệch)
        │
        ├──> Skill: classify_document (xác định đặc điểm văn bản: loại, mức độ, nội dung chính)
        │
        ├──> Tool: rule_engine.apply(fields, extracted_content)
        │         → chạy rule cứng (deterministic) trước
        │         → phần nào rule không match rõ ràng → đưa cho Claude reasoning
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

| Thành phần | Vai trò |
|---|---|
| **Harness** | Vòng lặp điều phối: gọi tool, xử lý lỗi/retry, giới hạn số bước, timeout khi PDF lớn/OCR chậm |
| **Orchestration** | Điều phối nhiều skill theo trình tự có điều kiện (nếu verify_metadata phát hiện sai lệch → dừng, yêu cầu xác nhận thay vì tự động routing) |
| **Agent Skills** | Đóng gói từng nghiệp vụ độc lập, dễ bảo trì/version riêng: `extract-pdf-metadata`, `apply-routing-rules`, `explain-decision`, `flag-ambiguous-cases` |
| **Rule Engine (code, không phải Claude)** | Xử lý phần rule tường minh, tách khỏi model để: nhanh, admin sửa rule không cần đụng prompt, audit dễ, dự đoán được |

---

## 4. Explainability & Human review

Vì đây là hệ thống ra quyết định hành chính (định tuyến sai có thể gây hậu quả):
- Mỗi kết quả có **độ tin cậy** (rule match rõ ràng vs Claude suy luận)
- Trường hợp confidence thấp hoặc nhiều rule mâu thuẫn → **flag để người dùng xác nhận** thay vì tự động gửi
- Log đầy đủ lý do (rule nào match, hoặc Claude giải thích gì) để admin audit và tinh chỉnh rule theo thời gian

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
│   │   ├── harness.py          # vòng lặp agent: gọi Claude + tool use
│   │   └── skills/              # SKILL.md cho từng bước reasoning
│   │       ├── verify_metadata.md
│   │       ├── classify_document.md
│   │       ├── apply_rules.md
│   │       └── explain_decision.md
│   ├── models/
│   │   └── schema.py           # Pydantic: request/response schema
│   └── storage/
│       └── audit.db            # SQLite log kết quả + lý do
├── tests/
├── requirements.txt
└── .env                        # ANTHROPIC_API_KEY
```

---

## 6. Tech stack đề xuất

- **API**: FastAPI (Python)
- **PDF extraction**: `pdfplumber` / `pypdf` cho PDF text-based; Tesseract hoặc Claude vision cho bản scan (fallback khi text extract ra rỗng/quá ít)
- **Rule storage**: file YAML/JSON ban đầu, sau này có thể chuyển sang SQLite/Postgres + admin UI
- **Orchestration**: Claude Agent SDK hoặc Messages API tự viết harness với tool use
- **Audit/log**: SQLite (demo) → Postgres (production)

---

## 7. Lộ trình xây dựng

### Giai đoạn 1 — Demo trên máy cá nhân

1. **Skeleton API** — FastAPI với endpoint `POST /classify` nhận JSON (6 field) + file PDF (multipart), validate bằng Pydantic.
2. **PDF extractor** — bắt đầu với `pdfplumber`/`pypdf` cho PDF text-based; để sẵn hook OCR phòng trường hợp scan.
3. **Rule engine thuần code** — viết `rules.yaml` với vài rule mẫu, viết matcher Python test độc lập, không phụ thuộc Claude.
4. **Harness gọi Claude** — đưa 6 field + nội dung PDF liên quan + rule active vào context, cho Claude dùng tool `apply_rules`, xử lý phần rule không match rõ bằng reasoning.
5. **Viết Agent Skills** — mỗi skill là 1 file hướng dẫn riêng, dễ chỉnh sửa từng phần mà không đụng cả prompt.
6. **Test end-to-end** với vài văn bản mẫu thật.
7. **Audit log** — lưu input, rule matched, output, lý do vào SQLite.

### Giai đoạn 2 — Triển khai VM chạy 24/24

8. Đóng gói Docker + docker-compose, quản lý secret qua `.env`.
9. Reverse proxy (Nginx) nếu cần expose HTTPS.
10. Giám sát uptime, backup cấu hình rule, xử lý restart tự động (systemd/docker restart policy).

> Lưu ý: Server luôn cần kết nối Internet để gọi Claude API (không có bản chạy offline hoàn toàn). Việc chuyển từ máy cá nhân sang VM chỉ thay đổi hạ tầng, không cần sửa logic nghiệp vụ nếu giai đoạn 1 được thiết kế tốt.

---

## 8. Các điểm còn cần xác nhận / làm rõ thêm

Những thông tin sau sẽ giúp tinh chỉnh kiến trúc chính xác hơn (rule engine đơn giản hay cần Claude reasoning nhiều, có cần OCR hay không):

- [ ] **Loại PDF đầu vào**: chủ yếu là PDF gốc (text-based), bản scan/ảnh (cần OCR), hay cả hai xen kẽ?
- [ ] **Độ phức tạp của rule**: đơn giản dạng bảng quyết định (điều kiện rõ ràng → cơ quan cụ thể), hay phức tạp/chồng chéo cần suy luận ngữ nghĩa nội dung văn bản?
- [ ] **Khối lượng xử lý dự kiến**: bao nhiêu văn bản/ngày, yêu cầu độ trễ (real-time từng văn bản hay có thể xử lý theo batch)?
- [ ] **Output chi tiết**: chỉ cần tên cơ quan, hay cần thêm mức ưu tiên, người xử lý cụ thể, thời hạn xử lý?
- [ ] **Cơ chế xác nhận thủ công**: có cần người dùng duyệt lại kết quả trước khi coi là chính thức không, đặc biệt với case confidence thấp?
- [ ] **Bảo mật dữ liệu**: văn bản có thuộc loại nhạy cảm/mật cần kiểm soát không rời khỏi mạng nội bộ không? (Ảnh hưởng đến việc có được gọi Claude API qua Internet hay không)

---

## 9. Bước tiếp theo đề xuất

- Scaffold code skeleton cho giai đoạn demo (FastAPI + rule engine + harness mẫu), hoặc
- Thu thập vài văn bản mẫu thật (payload + PDF) để thiết kế `rules.yaml` và prompt sát với dữ liệu thực tế.
