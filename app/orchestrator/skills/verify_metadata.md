# Skill: verify_metadata

Sau khi trích metadata từ nội dung, kiểm tra tính nhất quán nội bộ (ví dụ: loại văn bản
ở tiêu đề có khớp trích yếu không; số hiệu có khớp cơ quan ban hành không).

- Nếu mâu thuẫn nghiêm trọng → trả `needs_review: true` và nêu lý do, KHÔNG tự định tuyến.
- Nếu hợp lệ → tiếp tục bước classify.
