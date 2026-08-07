# AI Document Router — Sở Nông nghiệp và Môi trường tỉnh Gia Lai

> Trạng thái: **Giai đoạn thiết kế & thu thập rule** — chưa có code triển khai. Repo hiện chỉ chứa tài liệu (`doc/`).

## Mục đích

Thiết kế một server AI nhận payload (6 trường thông tin văn bản) + file PDF đính kèm, tự động xác định danh sách cơ quan/lãnh đạo chịu trách nhiệm tiếp nhận và xử lý văn bản đến, dựa trên rule do admin cấu hình (không dùng RAG — xem lý do trong tài liệu thiết kế).

## Nội dung thư mục `doc/`

| File                                  | Nội dung                                                                                                               |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `thiet-ke-ai-document-router.md`    | Thiết kế kiến trúc tổng thể: bài toán, kiến trúc, tech stack, lộ trình xây dựng                           |
| `rulebase.md`                       | Rulebase phân luồng văn bản đã chuẩn hóa —**nguồn chính** dùng để nạp vào context khi triển khai |
| `rule.txt`                          | Rule thô ban đầu (nguồn tham khảo, đã được chuẩn hóa vào`rulebase.md`)                                   |
| `info.md`                           | Danh bạ nhân sự/đơn vị trực thuộc Sở                                                                           |
| `HUONG DAN CHUYEN VAN BAN DEN.docx` | Văn bản nguồn quy trình chuyển văn bản đến                                                                     |
| `QĐ 899...pdf`                     | Quyết định phân công nhiệm vụ Giám đốc, các Phó Giám đốc Sở                                             |
| `file_17695872361.pdf`              | Quyết định kiện toàn Hội đồng thẩm định (nguồn nhân sự Chi cục Quản lý đất đai)                     |
| `luongvb.jpg`                       | Sơ đồ luồng xử lý văn bản đến                                                                                 |
| `van-phong-reference.md`            | Phụ lục văn phong: cấu trúc thể thức, mã ký hiệu → đơn vị/lãnh đạo, thư viện cụm từ trích yếu theo lĩnh vực (rút từ `source/`) |
| `tu-dien-linh-vuc.yaml`             | Phiên bản máy đọc của `van-phong-reference.md` — dùng nạp vào context Claude reasoning khi rule cứng không match |

## Quyết định kiến trúc quan trọng

- **Không dùng RAG**: rule là tập hữu hạn, có cấu trúc rõ ràng → xử lý bằng rule engine code thuần (deterministic) + Claude reasoning chỉ cho phần rule không match rõ.
- **Bảo mật dữ liệu**: văn bản có thể thuộc loại nhạy cảm/mật, không được rời mạng nội bộ → gọi Claude qua **Amazon Bedrock/Google Vertex AI** trong **VPC riêng**, kết nối private (PrivateLink/Private Service Connect), không qua Internet công cộng. Chi tiết xem Mục 3 và Mục 8 trong `thiet-ke-ai-document-router.md`.

## Bước tiếp theo

Xem Mục 9 trong `thiet-ke-ai-document-router.md` — scaffold code skeleton (FastAPI + rule engine + harness) cho giai đoạn demo.
