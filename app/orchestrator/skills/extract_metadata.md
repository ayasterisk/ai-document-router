# Skill: extract_metadata

Trích từ nội dung văn bản các trường nghiệp vụ:
- Số hiệu văn bản
- Loại văn bản
- Cơ quan ban hành
- Người ký
- Ngày văn bản
- Trích yếu
- Hạn thực hiện (ngày cụ thể, hoặc "khẩn"/"hỏa tốc", hoặc null)

Dùng regex deterministic trước; phần không bắt được (cơ quan ban hành, người ký...) thì model bổ sung.
