# Kế hoạch xây dựng API tương thích giữa Script-Idesk và ai-document-router

Ngày lập: 2026-09-11  
Phạm vi chính: backend trong repository ai-document-router. Kế hoạch cũng liệt kê một nhóm thay đổi nhỏ bắt buộc ở Script-Idesk khi backend đơn thuần không thể bảo đảm đúng dữ liệu hoặc an toàn automation.

## 1. Kết luận kiến trúc

Không nên dựng thêm một service thứ ba và không nên port nguyên backend Gemini cũ.

Phương án ít rủi ro nhất là thêm một lớp compatibility façade ngay trong ứng dụng FastAPI hiện có của ai-document-router:

    Script-Idesk
        |
        |  Hợp đồng DocFlow hiện tại: Bearer + JSON + presign/upload
        v
    /api/v1 compatibility façade
        |-- xác thực tương thích
        |-- upload PDF tạm
        |-- cache/projection 13 trường + PATCH
        |-- chuyển đổi request/response
        v
    JobManager hiện có
        v
    worker subprocess hiện có
        v
    PDF extractor / OCR -> RuleEngine -> Harness -> AI local
        v
    SQLite audit + kết quả tương thích trả về frontend

Lớp façade chỉ dịch hợp đồng. Nó không được sao chép OCR, rule engine, harness, queue hoặc logic gọi AI.

API native hiện có như /v1/jobs, /v1/directory, /classify và feedback vẫn giữ nguyên để phục vụ client mới hoặc công cụ vận hành.

## 2. Nguồn sự thật đã đối chiếu

Kế hoạch này được lập từ code đang chạy, không dựa riêng vào tài liệu cũ:

- Script-Idesk/src/services/ai.js: hợp đồng backend frontend thực sự gọi.
- Script-Idesk/src/config.js và build.mjs: cách ghép base URL và nhúng cấu hình khi build.
- Script-Idesk/src/controllers/mainController.js: lookup, process, review, PATCH và fill.
- Script-Idesk/src/automation/formFiller.js: các field thực sự được dùng để automation.
- Script-Idesk/src/ui/dashboard.js: các field thực sự được hiển thị.
- Script-Idesk/docs/en/docflowv2.md và METADATA_SCHEMA.md: semantics của backend cũ.
- Script-Idesk/src/back_end_mockup/mock_backend.py: test double tham khảo, không phải blueprint production.
- ai-document-router/app/main.py, api/routes.py, jobs.py, worker.py, orchestrator/harness.py, models/schema.py và storage/audit.py: kiến trúc backend/harness hiện tại.
- ai-document-router/tests: hành vi native đã được kiểm thử.

Nguyên tắc ưu tiên khi có mâu thuẫn:

1. Call-site trong frontend hiện tại.
2. Schema và hành vi đã có test.
3. Tài liệu cũ chỉ dùng để bổ sung ý nghĩa nghiệp vụ.

## 3. Luồng frontend thực tế cần phục vụ

Một batch hiện chạy tuần tự như sau:

1. Frontend crawl danh sách và metadata từ iDesk.
2. Frontend lấy token qua POST /auth/token.
3. Với mỗi văn bản, frontend gọi POST /documents/lookup.
4. Nếu chưa có cache, frontend dùng session iDesk của trình duyệt để tải PDF.
5. Frontend gọi POST /files/presign.
6. Frontend PUT bytes PDF thô vào upload_url.
7. Frontend gọi đồng bộ POST /documents/process với metadata và public_url.
8. Backend trả object 13 trường để frontend hiển thị review.
9. Người dùng có thể sửa đơn vị/hạn; frontend PATCH /documents/{stt} theo kiểu best-effort.
10. Người dùng bấm Duyệt; frontend tự thao tác DOM iDesk. Bước này không gọi backend AI.

Ba nhóm request iDesk như view.cpx, download.cpx và fbyvsphere.cpx là request native của hệ thống iDesk. ai-document-router không triển khai các endpoint này.

## 4. Endpoint bắt buộc cho MVP

Compatibility router phải được mount chính xác tại prefix /api/v1 vì AUTH_BASE_URL hiện đã chứa prefix này rồi mới nối thêm path.

| Method | Path | Mục đích | Bắt buộc |
|---|---|---|---|
| POST | /api/v1/auth/token | Đổi credential tương thích thành Bearer token | Có |
| POST | /api/v1/files/presign | Cấp upload_url và reference cho PDF | Có |
| PUT | /api/v1/files/upload/{token} | Nhận bytes PDF thô | Có |
| POST | /api/v1/documents/lookup | Tra projection đã xử lý | Có |
| POST | /api/v1/documents/process | Chạy hoặc join job, chờ và trả 13 trường | Có |
| PATCH | /api/v1/documents/{stt} | Lưu chỉnh sửa tay | Có |

Không triển khai trong MVP vì frontend không gọi:

- GET /files/tmp/{token}.
- /wards, /wards/compare, /wards/{ward_code}/organizations.
- /organizations/{id}/entries.
- Các alias /api/process-doc hoặc route root của mock cũ.
- Một queue/Celery/Redis mới.
- Một service AI trung gian mới.

/health và /ready native hiện có vẫn giữ để deploy/probe, nhưng không thuộc hợp đồng frontend.

## 5. Ma trận khoảng cách hiện tại

| Chủ đề | Script-Idesk hiện cần | ai-document-router hiện có | Việc phải làm |
|---|---|---|---|
| Auth | Authorization: Bearer | X-API-Key | Thêm principal resolver tương thích Bearer |
| Input PDF | presign rồi PUT raw bytes | multipart POST /v1/jobs | Thêm temp upload store và adapter |
| Process | JSON, đồng bộ, chỉ nhận HTTP 200 | multipart, job 202 + polling | Submit JobManager nội bộ rồi chờ terminal state |
| Lookup | Theo 6 metadata field | Theo job_id | Thêm document projection/cache riêng |
| Mutable result | PATCH theo stt | Feedback append-only theo job | Thêm stt và partial PATCH riêng |
| Output | 13 field tiếng Anh/scalar | Role array + native audit fields | Thêm mapper ở biên |
| Error | error.code/message/detail + X-Request-Id | FastAPI detail | Thêm error adapter và middleware |
| CORS | PUT/PATCH/Authorization | Chỉ GET/POST và X-API-Key | Mở đúng method/header/origin |
| Lifecycle | processing nhưng frontend vẫn gọi process | queued/running/completed/failed | Request trùng phải join cùng job |

## 6. Các quyết định thiết kế đã chốt cho MVP

### 6.1 Không self-call HTTP

/documents/process không gọi ngược http://127.0.0.1/classify.

Route compatibility phải gọi trực tiếp request.app.state.manager.submit(), đọc trạng thái từ request.app.state.store và chờ bằng asyncio sleep ngắn, tương tự logic /classify hiện có.

Lợi ích:

- Giữ nguyên queue/backpressure.
- Giữ hard timeout và kill process tree.
- Giữ worker isolation và audit SQLite.
- Không tạo thêm network hop hoặc cấu hình loopback.

Không gọi Harness trực tiếp trong request thread vì OCR và inference là blocking, đồng thời sẽ bỏ qua cơ chế timeout/recovery đã có.

### 6.2 Giữ core native độc lập với schema legacy

ClassifyResponse và RoutingFields hiện có vẫn là contract native.

Object 13 trường chỉ được tạo tại mapper compatibility. Không nhét stt, processing_unit hoặc notes vào schema native.

### 6.3 Process vẫn đồng bộ

Frontend chỉ coi status chính xác 200 là thành công và không poll job_id. Vì vậy compatibility process phải:

1. Submit hoặc join một job.
2. Chờ queued/running kết thúc.
3. Trả 200 với data, hoặc trả lỗi legacy.

Reverse proxy phải có read timeout lớn hơn ROUTER_JOB_TIMEOUT cộng overhead. Với default job timeout 300 giây, nên đặt proxy timeout tối thiểu 330 giây hoặc hạ đồng bộ cả hai giá trị sau khi benchmark máy thật.

### 6.4 Không fetch file_url tùy ý

Frontend hiện luôn tải PDF bằng session iDesk rồi upload lại. Vì vậy MVP chỉ nhận reference do chính backend vừa phát hành.

/documents/process tuyệt đối không tải URL bất kỳ từ Internet/intranet. Cách này loại bỏ toàn bộ bề mặt SSRF của backend cũ.

### 6.5 Cache trước khi kiểm tra reference upload

/documents/process phải tra document cache trước khi resolve file_url.

Nếu document đã completed, backend trả source=cache ngay cả khi upload token đã hết hạn hoặc file tạm đã được dọn. Đây là điều kiện để retry an toàn khi lần xử lý trước đã commit nhưng response 200 bị mất trên mạng.

### 6.6 Không thêm rate limiter ứng dụng ở MVP

JobManager đã có max_pending, max_workers và trả backpressure. Queue đầy được map sang HTTP 429 có Retry-After để frontend retry.

Rate limit theo IP/token có thể đặt ở reverse proxy khi có yêu cầu vận hành hoặc số đo tải; không thêm Redis/rate-limit package trước khi cần.

### 6.7 Dùng định danh iDesk ổn định, không dùng metadata thưa làm cache production

Sáu metadata có thể rỗng và không đủ phân biệt hai bản ghi. Cache chỉ theo các field này có thể trả kết quả hoặc bản PATCH của văn bản khác.

Frontend đã có sẵn doc.id và contentUid của attachment được chọn. Trong cùng sáu endpoint hiện tại, bổ sung hai field:

- document_id: ID bản ghi iDesk.
- attachment_id: contentUid của attachment đã được chuyển thành PDF.

Khóa production:

    document_key = SHA-256(tenant + document_id + attachment_id)

Không thêm endpoint mới. Đây chỉ là mở rộng payload lookup/process.

Chế độ migration khi frontend cũ chưa gửi hai field:

- Nếu đủ cả sáu metadata, có thể dùng legacy composite key và ghi identity_kind=legacy_full.
- Nếu metadata thiếu, lookup luôn trả not_found; không cache/join theo metadata.
- Khi process đã có PDF, key tạm phải thêm input SHA-256 để hai file khác nhau không dùng chung projection.
- Không được coi việc log weak_identity là biện pháp ngăn collision.

### 6.8 Metadata frontend phải đi vào harness với provenance

Sáu metadata crawl từ iDesk không chỉ dùng để echo/cache.

MVP truyền client_metadata qua payload worker và cho Harness merge theo quy tắc:

- PDF/OCR vẫn được extract trước.
- Field PDF thiếu thì dùng hint từ frontend.
- Nếu PDF và frontend khác nhau sau normalize, giữ giá trị frontend cho sáu field authoritative, thêm metadata_conflict_{field} vào review_reasons và needs_review=true.
- Không ghép metadata giả vào đầu document text.
- received_on vẫn tách biệt, không lấy từ document_date.

Thay đổi này cần test cùng AI engineer; không thay đổi rule/model policy.

## 7. Các cổng quyết định phải chốt trước khi viết mapper production

Đây là khác biệt nghiệp vụ, không thể giải quyết đúng chỉ bằng code adapter.

### Gate A — Nhiều xử lý chính nhưng frontend chỉ có một processing_unit

Router native trả don_vi_xu_ly_chinh dạng list và rule thực tế có nhiều phần tử. Frontend chỉ chọn một processing_unit.

Khuyến nghị:

- Nghiệp vụ phải chuẩn hóa rule về đúng một xử lý chính; phần còn lại được phân loại lại thành phối hợp hoặc theo dõi nếu đúng nghĩa.
- 1 phần tử -> map thành processing_unit.
- 0 phần tử -> processing_unit=null và bắt buộc frontend chặn Duyệt cho đến khi người dùng chọn thủ công.
- Nhiều hơn 1 -> không tự lấy phần tử đầu và không tự chuyển vai trò. Lưu projection ở trạng thái internal completed_review, đặt processing_unit=null và đưa danh sách ứng viên vào top-level review để frontend cho người dùng chọn.
- Native job đã completed không được chạy lại chỉ vì mapper gặp nhiều ứng viên.

Lý do: lấy phần tử đầu có thể chuyển sai lãnh đạo/đơn vị. Trả 422 đơn thuần cũng không tốt vì làm mất kết quả/candidate đã tính và dễ tạo vòng retry vô ích.

### Gate B — Nhiều lãnh đạo theo dõi nhưng frontend chỉ có một monitoring_leader

Áp dụng cùng chính sách:

- 0 phần tử -> null.
- 1 phần tử -> label đó.
- Nhiều hơn 1 -> monitoring_leader=null, lưu candidates/review flag; không tự lấy phần tử đầu.

### Gate C — summary và notes

Harness hiện không sinh bản tóm tắt văn bản; reason là lý do định tuyến, không phải summary. Frontend còn dùng notes hoặc summary để điền trường Nội dung.

MVP an toàn:

- summary = null nếu chưa có summarizer được kiểm chứng.
- notes = null.
- Không gán reason vào summary/notes vì có thể tự động ghi lý do kỹ thuật vào hồ sơ iDesk.
- Frontend bắt buộc chỉ sửa ô Nội dung khi notes hoặc summary có text không rỗng; nếu cả hai null thì giữ nguyên giá trị form.

Nếu nghiệp vụ bắt buộc có tóm tắt, mở một hạng mục riêng để bổ sung structured summary vào harness và test độ trung thực. Không giả lập bằng trích yếu hoặc routing reason.

### Gate D — Độ khẩn

Router trả do_khan, nhưng hợp đồng 13 field không có priority. Frontend hiện còn một bug: khi backend không trả priority, form filler đặt dropdown về 0 dù iDesk đã có độ khẩn gốc.

Backend không được tự thêm priority hoặc đoán mapping. Cần sửa riêng frontend để giữ doc.priority lấy từ iDesk. Đây là điều kiện bắt buộc trước production, nhưng không thêm endpoint backend.

### Gate E — Contract của AI local

Trước khi tích hợp phải xác nhận inference server thực tế:

- Có tương thích POST {INFERENCE_SERVER_URL}/v1/chat/completions hay không.
- Base URL không chứa sẵn /v1.
- Model có tool-calling đúng OpenAI schema hay chỉ prompt-only.
- Timeout, context length và max tokens.
- Harness cần model cho mọi document hay chỉ fallback khi không có matched rule.

MVP giữ nguyên hành vi hiện tại của Harness: rule-first, model chỉ fallback khi không có matched rule rõ. Không đổi policy AI trong cùng PR với API compatibility.

Lưu ý: các file app/orchestrator/skills/*.md hiện không được load trong runtime. Không được giả định rằng chúng đã tham gia luồng cho đến khi có test chứng minh.

## 8. Hợp đồng chi tiết của từng endpoint

### 8.1 POST /api/v1/auth/token

Request:

    {
      "username": "principal-name",
      "password": "the-principal-api-key"
    }

Thiết kế tối giản:

- username phải là key trong ROUTER_API_KEYS.
- password phải khớp token của principal bằng secrets.compare_digest.
- access_token trả về chính là API key đó.
- Compatibility endpoints chấp nhận Authorization: Bearer cùng token.
- Native endpoints tiếp tục chấp nhận X-API-Key.
- Không tạo JWT, session table hoặc dependency auth thứ hai.

Response frontend thực sự cần:

    {
      "access_token": "...",
      "token_type": "bearer"
    }

Frontend chỉ đọc access_token. Không công bố expires_in 24 giờ nếu backend không thực sự enforce TTL.

Lỗi:

- 401 INVALID_CREDENTIALS cho username hoặc password sai.
- Không cho biết username có tồn tại.
- Không log password/token.

Đây là compatibility shim cho service principal, không phải đăng nhập người dùng cuối.

### 8.2 POST /api/v1/files/presign

Request:

    {
      "filename": "document.pdf",
      "content_type": "application/pdf"
    }

MVP chỉ hỗ trợ application/pdf vì frontend không gửi DOCX/TXT.

Response:

    {
      "upload_url": "https://host/api/v1/files/upload/{opaque-token}",
      "public_url": "https://host/api/v1/files/ref/{opaque-token}",
      "upload_method": "PUT",
      "upload_headers": {
        "Content-Type": "application/pdf"
      },
      "expires_in": 600
    }

public_url là capability reference chỉ để gửi lại vào /documents/process. Không có GET /files/ref và không coi đây là URL public để tải file.

Token phải:

- Sinh bằng secrets.token_urlsafe.
- Gắn với owner/principal đã auth.
- Không chứa filename/path.
- Có TTL.
- Không thể liệt kê.

### 8.3 PUT /api/v1/files/upload/{token}

Request:

- Authorization: Bearer.
- Content-Type phải đúng application/pdf.
- Body là bytes thô, không multipart, không JSON, không base64.

Xử lý:

- Stream theo chunk xuống file tạm; không request.body() toàn bộ.
- Dừng khi vượt max_upload_bytes.
- File rỗng -> 400 EMPTY_FILE.
- Sai content type -> 400 UPLOAD_CONTENT_TYPE_MISMATCH.
- Token sai/hết hạn/khác owner -> 404 UPLOAD_TOKEN_INVALID.
- Vượt giới hạn -> 413 FILE_TOO_LARGE.
- Kho tạm đầy -> 503 SERVER_BUSY.
- Kiểm tra magic %PDF- trước khi đánh uploaded.
- Tính SHA-256 trong lúc stream.

Response thành công: 204 No Content. Frontend cũng chấp nhận 200 nhưng backend nên dùng 204.

### 8.4 POST /api/v1/documents/lookup

Request giữ sáu field phẳng và bổ sung hai định danh ổn định:

    {
      "document_id": "idesk-record-id",
      "attachment_id": "selected-contentUid",
      "document_number": "...",
      "document_type": "...",
      "issuing_agency": "...",
      "document_date": "YYYY-MM-DD hoặc chuỗi rỗng",
      "signer": "...",
      "subject": "..."
    }

Frontend luôn gửi đủ sáu key nhưng value có thể rỗng. Chính sách tương thích:

- Trim/collapse whitespace và Unicode NFC trước khi hash.
- Casefold chỉ dùng cho identity hash, không sửa giá trị hiển thị.
- document_id và attachment_id là khóa production.
- Nếu chưa có hai ID nhưng đủ cả sáu metadata, dùng legacy_full key trong giai đoạn migration.
- Nếu thiếu ID và thiếu bất kỳ metadata nào, không tra cache: trả not_found để tránh collision.
- Cả sáu metadata rỗng và không có document_id -> 422 INVALID_LOOKUP_PAYLOAD.
- Ghi identity_kind và metric weak_identity để biết client nào chưa nâng cấp.

Response luôn 200 cho trạng thái nghiệp vụ:

    {"found": false, "state": "not_found", "data": null}

    {"found": false, "state": "processing", "data": null}

    {"found": false, "state": "failed_retryable", "data": null}

    {"found": true, "state": "completed", "data": {"stt": 1}}

Mapping:

- Không có row -> not_found.
- Row/job queued hoặc running -> processing.
- Row completed/completed_review -> completed + 13 field và optional top-level review.
- Lỗi transient -> failed_retryable.

Frontend hiện không poll processing mà gọi process ngay, nên process phải join job đang có.

### 8.5 POST /api/v1/documents/process

Request:

    {
      "document_id": "idesk-record-id",
      "attachment_id": "selected-contentUid",
      "metadata": {
        "document_number": "...",
        "document_type": "...",
        "issuing_agency": "...",
        "document_date": "YYYY-MM-DD hoặc chuỗi rỗng",
        "signer": "...",
        "subject": "..."
      },
      "file_url": "reference do backend phát"
    }

Thuật toán bắt buộc:

1. Validate cấu trúc JSON và metadata.
2. Tính document_key từ tenant + document_id + attachment_id; chỉ dùng fallback theo mục 6.7 trong migration.
3. Tra router_documents theo tenant + document_key.
4. Nếu completed/completed_review và cache chưa bị operator invalidate, trả cache ngay; chưa resolve file_url.
5. Nếu processing, reconcile attempt_key/current_job_id với router_jobs. Native job completed/failed phải được phản chiếu vào projection ngay cả khi request tạo job trước đã disconnect.
6. Nếu cần attempt mới, resolve và validate token/file upload trước khi chuyển projection sang processing.
7. Đọc bytes + filename + SHA từ TempUploadStore; process chỉ đọc artifact immutable có state=uploaded.
8. Atomically reserve attempt trong SQLite bằng compare-and-swap, đồng thời lưu attempt_number, deterministic attempt_key, job_owner và lease_until trước khi submit.
9. Request thua CAS phải join/reconcile attempt đang có; không submit job thứ hai.
10. Tạo payload đúng internal contract của JobManager:

       {
         "document_id": "docflow:{document_key}",
         "received_on": "ngày server UTC+7",
         "input_sha256": "digest của input",
         "text": "",
         "files": [
           {
             "name": "document.pdf",
             "base64": "...",
             "sha256": "..."
           }
         ]
       }

11. Submit JobManager với deterministic attempt_key.
12. Nếu crash xảy ra sau submit nhưng trước khi lưu current_job_id, lookup/process/startup dùng AuditStore.find_key(job_owner, attempt_key) để tìm lại job.
13. Lưu current_job_id rồi chờ status qua AuditStore.
14. Compatibility wait có wall-clock timeout riêng, tính cả queue time. Hết thời gian thì trả 503 PROCESSING_PENDING nhưng không hủy hoặc submit lại job; request sau join tiếp.
15. Nếu native job completed, map result và commit projection + provenance atomically.
16. Nếu native job failed, mọi exit path phải chuyển state rõ; không để processing với current_job_id rỗng.
17. Chỉ sau khi projection completed đã commit bền vững mới xóa file tạm. Lỗi transient phải gia hạn lease upload để retry cùng public_url.
18. Trả source=processed.

received_on không được lấy từ document_date. Khi frontend chưa gửi ngày nhận, dùng ngày tại server theo UTC+7. Có thể thêm received_on vào contract trong phiên bản frontend sau.

Response:

    {
      "source": "processed",
      "data": {
        "stt": 1,
        "document_number": "...",
        "document_type": "...",
        "issuing_agency": "...",
        "document_date": "2026-09-11",
        "signer": "...",
        "subject": "...",
        "summary": null,
        "processing_unit": "...",
        "monitoring_leader": null,
        "implementation_deadline": "2026-09-15",
        "coordinating_units": [],
        "notes": null
      },
      "review": {
        "needs_review": true,
        "requires_confirmation": true,
        "degraded": false,
        "review_reasons": [],
        "primary_candidates": [],
        "monitoring_candidates": []
      }
    }

Cache hit:

    {
      "source": "cache",
      "data": {"stt": 1}
    }

Trong response thật, data luôn phải có đủ 13 key và không có field thừa. review nằm ngoài data để không làm bẩn schema legacy. Frontend cũ bỏ qua field này; frontend production phải hiển thị/cưỡng chế review theo mục 20.

Compatibility wait timeout phải nhỏ hơn timeout reverse proxy. Queue wait có thể dài hơn job_timeout; không được chỉ lấy job_timeout + vài giây rồi giả định đủ.

### 8.6 PATCH /api/v1/documents/{stt}

Body là subset không rỗng của:

- summary.
- processing_unit.
- monitoring_leader.
- implementation_deadline.
- coordinating_units.
- notes.

Quy tắc:

- extra=forbid.
- stt phải thuộc owner của Bearer token.
- Chỉ PATCH row completed.
- Không gửi field = giữ nguyên.
- null/chuỗi rỗng ở scalar = xóa.
- coordinating_units null hoặc [] = lưu [].
- coordinating_units luôn trả ra là array.
- Chỉ UPDATE các cột có trong request để các PATCH fire-and-forget khác field không ghi đè nhau.
- Dùng transaction SQLite; last-write-wins nếu hai PATCH cùng một field.

Response 200:

    {
      "data": {
        "...": "đủ 13 field sau cập nhật"
      }
    }

Lỗi:

- 404 DOCUMENT_NOT_FOUND.
- 409 DOCUMENT_NOT_COMPLETED.
- 422 INVALID_UPDATE_PAYLOAD.

Không ép PATCH legacy vào native feedback endpoint. Feedback native cần full decision, router recipient ID và hash; PATCH frontend chỉ là partial label strings nên semantics khác.

## 9. Mapping kết quả native sang 13 field

| Field legacy | Nguồn | Chính sách |
|---|---|---|
| stt | router_documents.stt | SQLite tự cấp |
| document_number | metadata request | Frontend authoritative; blank lưu/trả null |
| document_type | metadata request | Frontend authoritative; blank lưu/trả null |
| issuing_agency | metadata request | Frontend authoritative; blank lưu/trả null |
| document_date | metadata request | Không lấy từ AI để ghi đè; blank trả null |
| signer | metadata request | Frontend authoritative; blank lưu/trả null |
| subject | metadata request | Frontend authoritative; blank lưu/trả null |
| summary | null trong MVP | Không giả lập từ reason |
| processing_unit | recipients.don_vi_xu_ly_chinh[].name | 1 -> string; 0 hoặc nhiều -> null + review |
| monitoring_leader | recipients.lanh_dao_theo_doi[].name | 1 -> string; 0 hoặc nhiều -> null; nhiều -> review |
| implementation_deadline | han_thuc_hien | ISO YYYY-MM-DD hoặc null |
| coordinating_units | recipients.phoi_hop_xu_ly[].name | Dedupe, luôn list |
| notes | null trong MVP | Không tự điền routing reason |

Ưu tiên recipients.*.name thay vì router ID vì frontend đang match text với cây đơn vị iDesk.

Không thêm priority vào object legacy. Độ khẩn phải được xử lý từ metadata iDesk ở frontend cho đến khi hai bên chốt contract mới.

LegacyDocument response model phải enforce:

- stt là integer >= 1.
- Sáu identity field là string hoặc null; blank input được normalize thành null trong projection.
- summary, processing_unit, monitoring_leader, implementation_deadline và notes là string hoặc null.
- coordinating_units là list string, tối đa 50 phần tử, không bao giờ null.
- data có đúng 13 key, extra=forbid.
- process bọc source/data/review; lookup trả found/state/data/review ở top-level; auth và presign không bọc data.

## 10. Lưu trữ và state machine

router_jobs hiện là execution log cho từng attempt; nó không thay thế được document cache mutable vì không có stt, sáu metadata hay PATCH projection.

Mở rộng AuditStore.init() bằng migration idempotent, không thêm ORM/Alembic:

    CREATE TABLE IF NOT EXISTS router_documents (
      stt INTEGER PRIMARY KEY AUTOINCREMENT,
      tenant TEXT NOT NULL,
      document_key TEXT NOT NULL,
      identity_kind TEXT NOT NULL,
      state TEXT NOT NULL,
      job_owner TEXT,
      current_job_id TEXT,
      attempt_key TEXT,
      attempt INTEGER NOT NULL DEFAULT 0,
      lease_until TEXT,
      idesk_document_id TEXT,
      attachment_id TEXT,
      input_sha256 TEXT,
      document_number TEXT,
      document_type TEXT,
      issuing_agency TEXT,
      document_date TEXT,
      signer TEXT,
      subject TEXT,
      summary TEXT,
      processing_unit TEXT,
      monitoring_leader TEXT,
      implementation_deadline TEXT,
      coordinating_units_json TEXT NOT NULL DEFAULT '[]',
      notes TEXT,
      rules_sha256 TEXT,
      directory_version TEXT,
      tier TEXT,
      degraded INTEGER,
      needs_review INTEGER NOT NULL DEFAULT 1,
      requires_confirmation INTEGER NOT NULL DEFAULT 1,
      review_json TEXT NOT NULL DEFAULT '{}',
      last_error TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      completed_at TEXT,
      UNIQUE(tenant, document_key)
    );

    CREATE TABLE IF NOT EXISTS router_uploads (
      token_hash TEXT PRIMARY KEY,
      owner TEXT NOT NULL,
      filename TEXT NOT NULL,
      content_type TEXT NOT NULL,
      path TEXT NOT NULL,
      state TEXT NOT NULL,
      size_bytes INTEGER,
      sha256 TEXT,
      expires_at TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

Document state:

    absent
      -> processing
      -> completed
      -> completed_review

    processing
      -> failed_retryable
      -> processing (attempt mới)

    processing
      -> failed_terminal

completed_review là kết quả đã tính xong nhưng cần người dùng xử lý ambiguity/review flag. Nó không được submit AI lại. failed_terminal giữ provenance/lỗi và không tự retry quá attempt ceiling.

Lỗi xảy ra trước reserve không tạo/chuyển row. Lỗi input vĩnh viễn sau reserve chuyển failed_terminal hoặc xóa row nếu stt chưa từng được trả cho client. Phải chọn một quy tắc nhất quán và test; không có nhánh nào được để processing vô hạn.

Khi app restart:

1. AuditStore.recover() đánh native queued/running thành failed như hiện tại.
2. Với router_documents còn processing, tìm job bằng current_job_id; nếu thiếu thì tìm bằng job_owner + attempt_key.
3. Nếu job completed, chạy mapper và commit projection.
4. Nếu job failed, map state/error.
5. Chỉ khi không tìm thấy job và lease đã hết mới chuyển failed_retryable với server_restarted.

Completed projection có thể được giữ độc lập với retention của router_jobs, nhưng phải giữ input/rule/directory/review provenance tối thiểu như schema trên. Trước khi purge native job, cần bảo đảm projection đã reconcile. Chính sách cache khi rule/directory đổi phải được operator chốt: MVP không tự ghi đè manual PATCH; operator invalidate có kiểm soát khi rollout rule mới.

Owner và tenant là hai khái niệm khác nhau:

- owner là service principal tạo job/upload, dùng cho auth/audit.
- tenant là phạm vi chia sẻ document cache.

Nếu chỉ có một principal thì tenant=owner. Nếu mỗi workstation có token riêng nhưng cần chia sẻ cache/PATCH trong cùng cơ quan, phải cấu hình mapping principal -> tenant; không vô tình tạo cache tách rời hoặc mở cross-department access.

## 11. Idempotency và xử lý race

Frontend không gửi Idempotency-Key và có thể retry process sau lỗi mạng.

Backend phải quản hai lớp:

- document_key = lifecycle/cache của một văn bản.
- job idempotency key = một attempt xử lý cụ thể.

Đề xuất key:

    docflow:{stt}:attempt:{attempt_number}

reserve/start_attempt phải atomic bằng SQLite transaction. Một request thắng quyền submit; request còn lại đọc current_job_id và cùng chờ job đó.

Trước khi submit phải ghi attempt_key/job_owner/lease vào projection. Sau submit mới bổ sung current_job_id. Nếu khoảng giữa hai bước bị crash, reconcile dùng AuditStore.find_key(job_owner, attempt_key), không tạo attempt khác ngay.

Nếu attempt failed_retryable, request kế tiếp tăng attempt_number rồi mới submit. Không dùng lại một idempotency key native đã failed vì JobManager sẽ trả lại job failed cũ.

Đặt attempt ceiling, mặc định 3 lần cho lỗi catch-all/transient. Khi đạt trần, state=failed_terminal và process trả 422 PROCESSING_FAILED_FINAL; lookup không được kích hoạt thêm AI vô hạn. Các lỗi có nguyên nhân vận hành rõ như server restart có thể được operator reset.

PATCH chỉ update đúng field được gửi để tránh lost update khi các thao tác UI chạy gần nhau.

## 12. TempUploadStore

Tạo store stdlib + SQLite metadata, không thêm S3/MinIO trong MVP:

- Root là thư mục temp riêng, không nằm trong source tree.
- Metadata bền vững nằm trong router_uploads; chỉ lưu SHA-256 của opaque token, không lưu raw token.
- Bytes nằm trên disk để không nhân đôi file lớn trong RAM trước khi JobManager base64 payload.
- Một ASGI worker như kiến trúc hiện tại.
- PUT phải compare-and-swap pending -> uploading để chỉ có một writer.
- Stream vào file .part riêng, fsync/close rồi atomic rename; chỉ sau đó đổi state=uploaded.
- Process chỉ đọc file immutable có state=uploaded; không thể đọc file đang upload.
- Duplicate/concurrent PUT được trả lỗi ổn định hoặc idempotent 204 nếu cùng artifact đã hoàn tất; policy phải có test.
- Cleanup opportunistic khi presign/upload/process và startup.
- Sau crash, file orphan được dọn ở startup theo mtime/TTL.
- Không dùng filename người dùng làm path.
- Tổng dung lượng tạm bị giới hạn.
- Graceful shutdown không xóa upload chưa hết hạn; nếu không retry sau restart sẽ hỏng.
- Mỗi khi process bắt đầu hoặc trả lỗi transient, gia hạn expires_at ít nhất đến sau job_timeout + compatibility wait/backoff. TTL không được ngắn hơn toàn retry horizon.

Config đề xuất:

- ROUTER_PUBLIC_BASE_URL.
- ROUTER_COMPAT_UPLOAD_TTL_SEC=1200 hoặc giá trị đã tính từ retry budget.
- ROUTER_COMPAT_UPLOAD_DIR.
- ROUTER_COMPAT_MAX_TMP_BYTES.
- ROUTER_COMPAT_WAIT_TIMEOUT_SEC.
- ROUTER_COMPAT_MAX_ATTEMPTS=3.

Giữ compatibility max file 25 MiB như contract cũ. Native API có thể tiếp tục 20 MiB; BodyLimitMiddleware phải chọn limit theo path. Filename có thể mang đuôi .docx vì iDesk tải view=pdf nhưng giữ tên gốc; validate theo Content-Type và magic bytes, không theo extension.

## 13. Xác thực, CORS và request ID

### Xác thực

Tái sử dụng ROUTER_API_KEYS làm nguồn principal duy nhất:

- Native: X-API-Key.
- Compatibility: Bearer cùng token.
- /auth/token chỉ là adapter cho build hiện tại.

Mỗi máy/trạm nên có principal riêng để owner scope và audit có ý nghĩa.

### CORS

Cập nhật middleware:

- allow_methods: GET, POST, PUT, PATCH, OPTIONS.
- allow_headers: Content-Type, Accept, Authorization, X-API-Key, Idempotency-Key, X-Request-Id.
- expose_headers: X-Request-Id, Retry-After.
- allow_origins phải là origin rõ ràng; không dùng wildcard.
- allow_credentials=false như hiện tại.

GM_xmlhttpRequest chủ yếu bị kiểm soát bởi Tampermonkey @connect, không phải page CORS. Nếu dùng hostname mới, phải update Script-Idesk/src/meta.js.

### Request ID

Middleware:

- Nhận X-Request-Id hợp lệ 8–128 ký tự hoặc tự sinh uuid.
- Gắn x-request-id vào mọi response, kể cả lỗi.
- Ghi request ID vào log structured.
- Không log token, raw PDF, full request body hoặc AI prompt.
- Request-ID middleware phải là lớp ngoài cùng.
- BodyLimitMiddleware hiện tự trả {"detail":"request_body_too_large"} trước route. Phải sửa middleware này thành path-aware để /api/v1 trả legacy envelope + request ID cho cả Content-Length quá lớn và chunked overflow.

Frontend đang parse header không case-normalize; nên sửa riêng để luôn lowercase key. Backend vẫn phải expose header đúng chuẩn.

### Error envelope

Mọi lỗi compatibility:

    {
      "error": {
        "code": "STABLE_CODE",
        "message": "Thông báo an toàn",
        "detail": null
      }
    }

Validation handler chỉ đổi envelope cho path /api/v1; không làm vỡ lỗi của native /v1.

Reverse proxy 413/504 cũng phải được format hoặc tránh phát sinh bằng limit/timeout cao hơn lớp ứng dụng; nếu proxy trả HTML, frontend không đọc được error code/request ID.

## 14. Map lỗi native sang lỗi frontend hiểu

Frontend chỉ retry HTTP 429 và 503. Vì vậy HTTP status quan trọng hơn error code.

| Nguồn lỗi | HTTP legacy | Code đề xuất | Retry |
|---|---:|---|---|
| Thiếu/sai Bearer | 401 | UNAUTHORIZED | Không; frontend phải refresh auth |
| Sai username/password tại auth/token | 401 | INVALID_CREDENTIALS | Không |
| QueueFull | 429 | RATE_LIMITED | Có |
| Compatibility wait hết nhưng job còn chạy/queued | 503 | PROCESSING_PENDING | Có; join cùng job |
| job_timeout | 503 | PROCESSING_TIMEOUT | Có |
| processing_failed dưới attempt ceiling | 503 | PROCESSING_FAILED | Có |
| processing_failed đạt attempt ceiling | 422 | PROCESSING_FAILED_FINAL | Không |
| server_restarted/server_stopping | 503 | SERVER_BUSY | Có |
| configuration_changed | 503 | SERVER_BUSY | Có sau khi hệ thống ổn định |
| invalid_pdf/invalid_pdf_signature | 422 | INVALID_DOCUMENT | Không |
| Magic bytes sai ngay lúc PUT | 415 | PDF_REQUIRED | Không |
| encrypted_pdf | 422 | ENCRYPTED_PDF | Không |
| no_document_content | 422 | NO_DOCUMENT_CONTENT | Không |
| page_limit_exceeded | 413 | DOCUMENT_LIMIT_EXCEEDED | Không |
| extracted_text_limit_exceeded | 413 | DOCUMENT_LIMIT_EXCEEDED | Không |
| PUT token sai/hết hạn/khác owner | 404 | UPLOAD_TOKEN_INVALID | Không |
| Process nhận reference malformed/ngoài backend | 422 | INVALID_FILE_URL | Không |
| Process reference đúng dạng nhưng token sai/hết hạn/khác owner | 404 | UPLOAD_TOKEN_INVALID | Không |
| payload process sai | 422 | INVALID_PROCESS_PAYLOAD | Không |
| payload lookup sai | 422 | INVALID_LOOKUP_PAYLOAD | Không |
| lỗi DB bất ngờ | 503 | SERVER_BUSY | Có; detail chỉ ở server log |

429/503 nên có Retry-After. Frontend hiện chưa đọc header này nhưng nó hữu ích cho client native và quan sát vận hành.

Catch-all processing_failed không được retry vô hạn. Backend ghi attempt count/cooldown và dừng ở ceiling; log nội bộ giữ exception theo request/job ID nhưng response không lộ stack trace.

## 15. File cần thêm/sửa

### Thêm

1. app/api/compat.py
   - Sáu route compatibility.
   - Bearer dependency.
   - Wait/join job.
   - Mapper lỗi và response wrapper.

2. app/models/compat.py
   - IdentityMetadata.
   - ProcessRequest.
   - PresignRequest/Response.
   - LegacyDocument 13 field.
   - PatchDocument extra=forbid.
   - Native-to-legacy mapper.

3. app/storage/uploads.py
   - TempUploadStore.
   - Token hash/owner/TTL/lease.
   - Stream/size/hash/magic validation.
   - CAS upload, atomic rename và cleanup.

4. tests/test_compat_api.py
   - Consumer contract và end-to-end façade.

### Sửa

1. app/main.py
   - Include compat router với prefix /api/v1.
   - Khởi tạo/đóng TempUploadStore trong lifespan.
   - Request-ID/error middleware.
   - CORS method/header/expose.

2. app/config.py và .env.example
   - Public compatibility base URL, temp path, TTL/cap, wait timeout, attempt ceiling.
   - Validation path/cap.

3. app/storage/audit.py
   - Migration router_documents và router_uploads.
   - get/reserve/reconcile/start/complete/fail/patch/recover.

4. app/worker.py, app/orchestrator/harness.py và app/extract/metadata.py
   - Truyền client_metadata vào worker.
   - Merge hint có provenance.
   - Conflict tạo review reason; không silent overwrite.

5. README.md và doc/api-integration.md
   - Tách rõ native API và Script-Idesk compatibility API.
   - Ghi synchronous timeout và security boundary.

6. doc/openapi.json
   - Regenerate bằng tools/export_contract.py sau khi test contract chốt.

7. Script-Idesk/src/services/ai.js và controller/form filler liên quan
   - Gửi document_id + attachment_id trong lookup/process.
   - Giữ textarea khi summary/notes rỗng.
   - Refresh token một lần khi 401.
   - Đọc Retry-After/backoff phù hợp.
   - Nhận và lưu top-level review.

8. Script-Idesk/src/automation/formFiller.js và UI review
   - Không hạ priority khi backend không trả priority.
   - Chặn Duyệt nếu processing_unit còn null.
   - Hiển thị review flags/candidates tối thiểu.

Không sửa app/jobs.py trừ khi test chứng minh cần hook completion. Reconciliation nằm ở compatibility store/service để core queue giữ ổn định.

## 16. Kế hoạch triển khai theo phase

### Phase 0 — Chốt contract và cổng nghiệp vụ, 0.5–1 ngày

- Chốt Gate A/B với owner rulebase.
- Xác nhận endpoint/model/tool-calling của AI local.
- Xác nhận public base URL và reverse proxy.
- Rotate mọi credential cũ đã xuất hiện trong repository/tài liệu.
- Chụp fixture request trực tiếp từ services/ai.js.
- Chốt policy summary/notes=null và priority do iDesk authoritative.
- Chốt tenant boundary và stable identity document_id + attachment_id.
- Chốt policy stale cache khi rule/directory đổi.

Deliverable:

- Decision record ngắn.
- Bộ JSON/binary fixture không chứa dữ liệu nhạy cảm.

### Phase 1 — Storage và contract models, 1–2 ngày

- Tạo Pydantic models compatibility.
- Migration router_documents + router_uploads.
- Implement canonical identity/hash.
- Implement state transition, attempt lease và reconciliation/recovery.
- Implement atomic partial PATCH repository.
- Unit test normalization, projection và race cơ bản.

Exit criteria:

- Migration chạy lặp không lỗi.
- Principal ngoài tenant không lookup/PATCH được row tenant khác; policy chia sẻ trong cùng tenant được test.
- coordinating_units luôn là array.
- Crash window trước/sau JobManager.submit có thể reconcile bằng attempt_key.

### Phase 2 — Auth, request ID và upload, 1–2 ngày

- Bearer resolver dùng cùng ROUTER_API_KEYS.
- /auth/token.
- TempUploadStore.
- presign + raw PUT.
- File type/size/owner/TTL/capacity.
- Persist token metadata, CAS writer, atomic rename và lease extension.
- Legacy error envelope.
- CORS, request ID và path-aware BodyLimitMiddleware.

Exit criteria:

- Upload khác owner bị từ chối.
- URL tùy ý không thể đến network.
- File hết TTL/orphan được dọn; upload chưa hết hạn sống qua restart.
- Mọi response compatibility có request ID.
- File 25 MiB theo legacy limit được xử lý; file vượt limit có đúng envelope.

### Phase 3 — Process/lookup và JobManager bridge, 2–3 ngày

- Cache-before-file validation.
- Atomic reserve + attempt.
- Submit JobManager trực tiếp.
- Join job đang chạy.
- Wall-clock wait tính cả queue, trả PROCESSING_PENDING trước proxy timeout.
- Reconcile terminal job khi request gốc disconnect hoặc service restart.
- Map result/error.
- Truyền và merge client_metadata có provenance.
- Commit projection rồi mới cleanup upload.
- lookup bốn state.

Exit criteria:

- Hai request đồng thời cùng identity chỉ tạo một native job.
- Response bị mất rồi retry trả source=cache.
- Queue full/timeout trả status frontend có thể retry.
- Native /v1/jobs vẫn hoạt động như cũ.
- Native review/provenance được giữ trong projection.

### Phase 4 — Contract tests và E2E, 1–2 ngày

- TestClient cho toàn bộ sáu route.
- Test PDF thật qua worker subprocess với model off.
- Test fake inference OpenAI-compatible cho nhánh T1/T2.
- Test middleware Content-Length và chunked oversized body.
- Test crash/reconcile và client disconnect.
- Test local AI/OCR smoke trên máy đích.
- Test frontend build gọi backend mới.
- Test reverse proxy timeout/body limit.

Exit criteria:

- Tất cả test native cũ và compat mới pass.
- Không gọi Internet ngoài inference/OCR endpoint được cấu hình nội bộ.
- Kết quả đúng 13 field và không có field AI ghi đè sáu metadata FE.
- Metadata conflict tạo review flag và không mất provenance.

### Phase 5 — Cập nhật consumer Script-Idesk bắt buộc, 1–2 ngày

- Gửi document_id + attachment_id mà không thêm endpoint.
- Parse/lưu top-level review.
- Chặn Duyệt nếu chưa có processing_unit.
- Giữ Nội dung nếu summary/notes null.
- Giữ priority iDesk nếu backend không trả.
- Refresh auth một lần khi 401.
- Honor Retry-After và tăng retry horizon phù hợp queue/job local.
- Normalize response header và escape AI text.

Exit criteria:

- Không thể submit văn bản có processing_unit null.
- Backend review/degraded/extraction warnings nhìn thấy trên card.
- Không xóa Nội dung và không hạ độ khẩn.
- Retry PROCESSING_PENDING join cùng job, không upload/submit trùng.

### Phase 6 — Staging với iDesk, 1–2 ngày

- Deploy sau HTTPS/reverse proxy.
- Cấu hình một principal riêng cho máy test.
- Dùng bộ văn bản đã ẩn dữ liệu hoặc được phép.
- Kiểm thử lookup/cache, PDF scan/text, chỉnh tay, reload, retry và batch.
- Đối chiếu tên đơn vị với cây fbyvsphere thật.
- Đo p50/p95 cho upload, cache, PDF text và OCR scan.

Exit criteria:

- Văn thư/nghiệp vụ xác nhận mapping.
- Không tự chuyển sai trường hợp multi-primary.
- Không hạ độ khẩn iDesk.
- Log đủ request ID/job ID/stt để truy vết.

Ước lượng tổng: 8–13 ngày kỹ thuật nếu inference server và rule mapping đã sẵn sàng; không gồm thời gian chờ nghiệp vụ duyệt Gate A/B hoặc benchmark model/OCR.

## 17. Ma trận kiểm thử tối thiểu

### Contract

- Auth đúng/sai.
- Thiếu Bearer.
- Exact status 200/204 như frontend chấp nhận.
- Error envelope và request ID trên 4xx/5xx.
- Sáu metadata đủ, thiếu một phần, tất cả rỗng, date sai.
- Stable document_id + attachment_id, legacy_full fallback và weak identity bypass cache.
- Hai văn bản metadata giống/thiếu không dùng nhầm projection.
- coordinating_units luôn list.
- PATCH từng field, nhiều field, body rỗng, extra field.
- PATCH enforce scalar tối đa 5.000 ký tự; list tối đa 50 phần tử; mỗi phần tử string tối đa 500 ký tự.
- PATCH -> lookup -> process cache đều trả bản đã sửa.
- Assert exact wrapper/unwrapped shape, status và type của đủ 13 field.

### Upload và security

- PDF hợp lệ.
- Body rỗng.
- Content-Type lệch.
- Magic không phải PDF.
- Filename .docx nhưng Content-Type/magic là PDF vẫn được chấp nhận.
- Quá max bytes.
- Token hết hạn.
- Token owner khác.
- public_url giả, localhost, metadata-service IP, URL ngoài.
- Temp capacity đầy.
- Cleanup sau completed và cleanup orphan startup.
- Restart còn đọc được upload chưa hết hạn.
- Hai PUT đồng thời không làm process đọc file dở.
- Content-Length và chunked body quá limit cùng trả legacy envelope + request ID.

### Lifecycle/idempotency

- not_found -> processing -> completed.
- lookup trong lúc job chạy.
- process thứ hai join job thứ nhất.
- cache hit trước expired file_url.
- response mất rồi retry.
- client disconnect sau submit, lần lookup sau reconcile completed.
- crash sau submit trước khi lưu current_job_id.
- QueueFull.
- job_timeout.
- compatibility wait hết khi job vẫn queued/running.
- server restart giữa job.
- failed_retryable tạo attempt mới.
- hai PATCH khác field không lost update.

### Mapping

- Một primary -> scalar.
- Không primary -> null + review; frontend chặn Duyệt.
- Nhiều primary -> null + candidates/review; không rerun AI.
- Không/một/nhiều monitoring leader.
- Dedupe coordinating units.
- Deadline ISO/null.
- summary/notes không bị gán routing reason.
- Labels lấy từ recipients.name, không router ID.
- needs_review/requires_confirmation/degraded/review_reasons được lưu và frontend nhìn thấy.

### Regression native

- /v1/jobs và GET job.
- /classify.
- /v1/directory.
- feedback owner/idempotency.
- PDF/OCR/harness tests hiện có.
- DB exclusive single ASGI worker.

## 18. Cấu hình triển khai

Backend:

    ROUTER_API_KEYS={"idesk-workstation-01":"<random-32-plus-char-token>"}
    ROUTER_ALLOWED_ORIGINS=["https://vpdt.gialai.gov.vn"]
    ROUTER_COMPAT_BASE_URL=https://api.example.internal/api/v1
    ROUTER_COMPAT_UPLOAD_TTL_SEC=1200
    ROUTER_COMPAT_UPLOAD_DIR=D:/router-tmp/uploads
    ROUTER_COMPAT_MAX_TMP_BYTES=209715200
    ROUTER_COMPAT_MAX_UPLOAD_BYTES=26214400
    ROUTER_COMPAT_WAIT_TIMEOUT_SEC=310
    ROUTER_COMPAT_MAX_ATTEMPTS=3
    ROUTER_JOB_TIMEOUT=300
    HARNESS_TOOL_MODE=auto
    INFERENCE_SERVER_URL=http://127.0.0.1:<port>
    INFERENCE_MODEL=<model-name>
    INFERENCE_API_KEY=<internal-key-or-EMPTY>
    INFERENCE_TOOL_CALLING=true

INFERENCE_SERVER_URL không thêm /v1 vì HttpInferenceClient hiện tự nối /v1/chat/completions.

ROUTER_COMPAT_BASE_URL là full compatibility base và đã chứa đúng một /api/v1. Code không được nối thêm /api/v1 lần nữa. Upload lease được gia hạn khi process/retry; giá trị TTL ban đầu không phải trần cứng của một job đang xử lý.

Chạy FastAPI với đúng một ASGI worker:

    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1

Reverse proxy:

- HTTPS.
- Body limit lớn hơn max upload + overhead.
- Read timeout lớn hơn ROUTER_COMPAT_WAIT_TIMEOUT_SEC; app phải chủ động trả 503 trước timeout proxy.
- Không public inference/OCR port.
- Có thể rate limit /auth/token và upload tại proxy.

Frontend:

- AUTH_BASE_URL phải là https://host/api/v1.
- AUTH_USERNAME là principal name.
- AUTH_PASSWORD là token tương ứng cho compatibility shim.
- lookup/process gửi document_id và attachment_id.
- Nếu đổi hostname, cập nhật @connect rồi build lại.
- build.mjs chỉ đọc .env hoặc process environment, không đọc .env.local.

Phương án ít thay đổi frontend nhất là giữ hostname production hiện có và đổi upstream reverse proxy sang FastAPI mới.

## 19. Bảo mật và dữ liệu nhạy cảm

- Credential cũ đang xuất hiện dạng plaintext trong tài liệu tracked và credential build-time nằm trong userscript. Phải rotate trước staging; không sao chép giá trị cũ sang backend mới.
- Service credential trong userscript không thể được coi là bí mật mạnh. Giảm rủi ro bằng token riêng từng máy, firewall/VPN, TLS, owner scope và rotation.
- Không log Authorization, password, PDF bytes hoặc prompt chứa toàn văn.
- SQLite hiện lưu extracted full text trong audit_text; bảo vệ file DB và áp dụng retention đã duyệt.
- PDF tạm phải nằm trên volume được bảo vệ và được dọn theo TTL.
- Không dùng arbitrary URL fetch.
- AI output là untrusted text; backend validate plain text/length. Frontend nên escape trước khi innerHTML để tránh XSS.
- Feedback native chưa được gọi khi người dùng bấm Duyệt; không được diễn giải PATCH là bằng chứng văn bản đã được chuyển thành công.

## 20. Các sửa frontend bắt buộc trước production

Không thêm endpoint, nhưng các sửa này là điều kiện correctness/safety:

1. Gửi doc.id thành document_id và contentUid của attachment được chọn thành attachment_id trong lookup/process.
2. Khi backend trả 401, xóa cachedAuthToken, login lại một lần rồi retry.
3. Không đặt priority về 0 khi AI response không có priority; giữ doc.priority từ iDesk.
4. Chỉ set CONTENT_TEXTAREA khi notes/summary có text; null phải giữ nguyên Nội dung hiện có.
5. Đọc top-level review; hiển thị needs_review/degraded/review_reasons/candidates và chặn Duyệt khi processing_unit chưa được người dùng chốt.
6. Honor Retry-After, xử lý PROCESSING_PENDING bằng cách gọi lại process để join job; backoff 1/2 giây hiện tại không đủ cho queue AI.
7. Normalize tên response header sang lowercase trước khi đọc x-request-id.
8. Escape summary/subject/error/AI label trước khi render innerHTML.

Nếu chạy local, thêm localhost hoặc 127.0.0.1 vào @connect. Nếu upload_url khác host API, cũng phải thêm host đó; kế hoạch này tránh việc đó bằng same-origin upload.

## 21. Definition of Done

Backend được coi là kết nối thành công khi:

- Sáu route compatibility hoạt động dưới /api/v1.
- Frontend hiện tại chỉ cần đổi AUTH_BASE_URL/credential và @connect nếu đổi host.
- PDF từ iDesk được upload raw, không để backend truy cập session/cookie iDesk.
- Process đi qua JobManager -> worker -> extractor/OCR -> RuleEngine -> Harness -> AI local.
- Không có code OCR/rule/harness bị copy sang façade.
- Process đồng bộ trả HTTP 200 với đủ đúng 13 field.
- Sáu metadata FE không bị AI ghi đè.
- Lookup/cache/PATCH bền vững qua restart.
- Request trùng không tạo hai job song song.
- Retry sau mất response không cần upload lại nếu kết quả đã commit.
- Owner khác không xem/PATCH/upload được dữ liệu.
- URL tùy ý không được fetch.
- Multi-primary/multi-leader có policy nghiệp vụ đã ký duyệt; trước đó fail safe.
- Tất cả test native và compatibility pass.
- Smoke test dùng inference/OCR local thật pass trên máy triển khai.
- Credential cũ đã rotate và không có secret mới được commit.

## 22. Việc cố ý để ngoài MVP

- Redis/Celery/Kafka.
- S3/MinIO presigned URL.
- PostgreSQL migration.
- Multi-ASGI-worker.
- Ward/organization catalog API cũ.
- Tự động gửi feedback khi PATCH.
- Tự xác nhận giao dịch Duyệt trên iDesk.
- AI document summarization.
- Metadata hint/conflict merge vào Harness.
- Remote arbitrary file_url.
- Reprocess tự động khi rule/directory đổi.

Chỉ bổ sung các hạng mục này khi có yêu cầu nghiệp vụ hoặc số đo vận hành chứng minh cần thiết.
