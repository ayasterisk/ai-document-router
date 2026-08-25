# Skill: verify_metadata

Đối chiếu 6 trường metadata (số hiệu, loại, cơ quan ban hành, người ký, ngày, trích yếu)
với nội dung PDF. Phát hiện sai lệch (ví dụ trích yếu không khớp nội dung, người ký sai).

- Nếu sai lệch nghiêm trọng → dừng, trả `needs_review: true` và nêu lý do, KHÔNG tự định tuyến.
- Nếu khớp → trả về xác nhận để tiếp tục bước classify.
