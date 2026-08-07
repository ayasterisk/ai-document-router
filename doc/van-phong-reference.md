# PHỤ LỤC: VĂN PHONG & MÃ KÝ HIỆU THAM CHIẾU

> **Nguồn:** rút từ 10 văn bản **đi** thật của Sở NN&MT tỉnh Gia Lai (thư mục `source/`) + `source/Book1.xlsx`.
> **Mục đích:** hỗ trợ Claude reasoning nhận diện đúng lĩnh vực/thuật ngữ ngành khi rule cứng trong `rulebase.md` không match rõ ràng trên trích yếu văn bản đến. **Không dùng làm ground-truth routing** — các văn bản nguồn là văn bản do Sở tự ban hành (Kính gửi ra ngoài), không phải văn bản đến cần định tuyến.
> **Cách dùng:** nạp phần II và III vào context cố định (system prompt, hưởng lợi từ prompt caching) khi Claude cần suy luận lĩnh vực cho văn bản đến chưa khớp rule cứng.

---

## I. Cấu trúc thể thức nhận diện trong PDF

Quan sát từ các file thật, văn bản hành chính của Sở có cấu trúc tuần tự cố định, hữu ích để `extract_pdf_content`/`verify_metadata` định vị đúng vùng dữ liệu:

```
[Quốc hiệu, tiêu ngữ]                    ← góc trên phải
[Tên cơ quan ban hành]  [Số: .../ký-hiệu-đơn-vị]   ← góc trên trái, cùng dòng số hiệu
[Trích yếu — bắt đầu "V/v..." hoặc là dòng tiêu đề in đậm ngay dưới số hiệu]
Kính gửi: [tên cơ quan/đơn vị/cá nhân nhận]
[Nội dung chính]
Nơi nhận: [danh sách đơn vị nhận — nếu là văn bản đến thật, đây là nơi cần đối chiếu với payload]
```

Lưu ý khi áp dụng cho **văn bản đến**: trường `Trích yếu văn bản` trong payload JSON cần được đối chiếu với dòng "V/v..." hoặc tiêu đề ngay dưới số hiệu trong PDF — nếu không khớp, đây là dấu hiệu sai lệch cần skill `verify_metadata` gắn cờ.

---

## II. Bảng mã ký hiệu văn bản → đơn vị → lãnh đạo phụ trách

Đối chiếu ký hiệu thật trong `source/` với `rulebase.md` Mục III. Đây là **bổ sung** cho rulebase — nếu văn bản đến có nhắc/trích dẫn số hiệu dạng này (ví dụ "theo Công văn số .../SNNMT-QLĐĐ"), có thể dùng làm tín hiệu phụ để xác định lĩnh vực.

| Mã ký hiệu | Đơn vị/lĩnh vực | Lãnh đạo phụ trách | Cấp | Nguồn đối chiếu |
|---|---|---|---|---|
| **KL** | Lâm nghiệp, Kiểm lâm | PGĐ Nguyễn Văn Hoan | PGĐ | 8795/SNNMT-KL |
| **QLĐĐ** | Quản lý đất đai | GĐ Cao Thanh Thương | GĐ | 8719, 8708, 8622/SNNMT-QLĐĐ |
| **CNTY** | Chăn nuôi và Thú y | PGĐ Đoàn Ngọc Có | PGĐ | 8682, 8680/SNNMT-CNTY |
| **TNN** | Tài nguyên nước, KTTV | PGĐ Vũ Ngọc An | PGĐ | 8544/SNNMT-TNN |
| **VPĐK** | Văn phòng Đăng ký đất đai | GĐ Cao Thanh Thương | GĐ | 8609/SNNMT-VPĐK |
| **TTr-SNNMT** | Tờ trình (không cố định lĩnh vực — theo nội dung) | tùy nội dung | — | 1126/TTr-SNNMT (nội dung nước sạch nông thôn → PGĐ Vũ Ngọc An) |
| **KH-SNNMT** | Kế hoạch (không cố định lĩnh vực — theo nội dung) | tùy nội dung | — | 115/KH-SNNMT (nội dung CCHC/kỷ luật hành chính → GĐ Cao Thanh Thương) |

> **Lưu ý:** `TTr` (Tờ trình) và `KH` (Kế hoạch) là *loại văn bản*, không phải mã đơn vị cố định như `KL`, `QLĐĐ`, `CNTY`, `TNN`, `VPĐK` — lĩnh vực của các văn bản này phải xác định qua nội dung/trích yếu, không suy ra trực tiếp từ ký hiệu.

**Đề xuất:** đưa bảng mã ký hiệu (trừ 2 dòng TTr/KH) vào `rulebase.md` như phụ lục tra cứu chính thức, vì đây là dữ liệu ổn định (mã đơn vị của Sở không đổi thường xuyên).

---

## III. Thư viện cụm từ trích yếu theo lĩnh vực (few-shot cho Claude reasoning)

Dùng khi trích yếu văn bản đến **không chứa từ khóa khớp thẳng** với `rules.yaml`, nhưng có cấu trúc câu/thuật ngữ tương tự các ví dụ dưới đây → Claude suy luận cùng lĩnh vực.

### Chăn nuôi và Thú y (PGĐ Đoàn Ngọc Có)
- *"tăng cường quản lý hoạt động nhập khẩu, buôn bán, sử dụng thuốc thú y..."* (8682/SNNMT-CNTY)
- *"tăng cường kiểm tra, giám sát dịch bệnh động vật, vệ sinh thú y, an toàn thực phẩm và chất cấm trong chăn nuôi..."* (8680/SNNMT-CNTY)
- **Tín hiệu ngữ nghĩa:** dịch bệnh động vật, thuốc thú y, vệ sinh thú y, chất cấm trong chăn nuôi, an toàn thực phẩm (nguồn gốc chăn nuôi).

### Quản lý đất đai (GĐ Cao Thanh Thương)
- *"rà soát, công bố công khai, lập danh mục các thửa đất nhỏ hẹp, nằm xen kẹt và việc giao đất, cho thuê đất..."* (8708/SNNMT-QLĐĐ)
- *"Giải quyết cấp Giấy chứng nhận quyền sử dụng đất, quyền sở hữu tài sản gắn liền với đất..."* (8622/SNNMT-QLĐĐ)
- **Tín hiệu ngữ nghĩa:** giao đất, cho thuê đất, thửa đất, Giấy chứng nhận QSDĐ, tài sản gắn liền với đất.
- **Phân biệt với VPĐK:** nội dung về *đăng ký đất đai, kê khai đất đai lần đầu* → thuộc Văn phòng Đăng ký đất đai (xem ví dụ dưới), khác với *giao đất/cho thuê đất/cấp GCN* → Chi cục Quản lý đất đai. Cả hai cùng thuộc GĐ Cao Thanh Thương nhưng khác đơn vị tham mưu.

### Văn phòng Đăng ký đất đai (GĐ Cao Thanh Thương)
- *"báo cáo khó khăn, vướng mắc trong công tác tổ chức thực hiện kê khai, đăng ký đất đai lần đầu"* (8609/SNNMT-VPĐK)
- **Tín hiệu ngữ nghĩa:** kê khai đất đai, đăng ký đất đai lần đầu, đăng ký biến động.

### Tài nguyên nước (PGĐ Vũ Ngọc An)
- *"công bố giá trị dòng chảy tối thiểu ở hạ lưu các đập, hồ chứa"* (8544/SNNMT-TNN)
- *"Phê duyệt Kế hoạch cấp nước an toàn khu vực nông thôn"* (1126/TTr-SNNMT)
- **Tín hiệu ngữ nghĩa:** dòng chảy tối thiểu, đập/hồ chứa, cấp nước an toàn, nước sạch nông thôn.

### Lâm nghiệp, Kiểm lâm (PGĐ Nguyễn Văn Hoan)
- *"phúc đáp Công văn của Công ty TNHH Trồng rừng... đăng ký tham gia Chính sách hỗ trợ phát triển rừng trồng cây gỗ lớn..."* (8795/SNNMT-KL)
- **Tín hiệu ngữ nghĩa:** rừng trồng, rừng sản xuất/gỗ lớn, chính sách hỗ trợ phát triển rừng.

### Cải cách hành chính / tổng hợp (GĐ Cao Thanh Thương)
- *"tăng cường kỷ luật, kỷ cương hành chính; chấn chỉnh lề lối làm việc và nâng cao hiệu quả hoạt động..."* (115/KH-SNNMT)
- **Tín hiệu ngữ nghĩa:** kỷ luật/kỷ cương hành chính, lề lối làm việc — văn bản mang tính tổng hợp, áp dụng toàn ngành, không thuộc riêng một PGĐ → về GĐ theo Mục II.1 của `rulebase.md`.

---

## IV. Ghi chú văn phong khi sinh giải thích quyết định (`explain_decision`)

Nếu sau này skill `explain_decision` cần sinh nội dung theo văn phong hành chính nội bộ (không chỉ JSON kỹ thuật), tham khảo giọng văn trang trọng, súc tích của các văn bản thật, ví dụ mở đầu kiểu: *"Sở Nông nghiệp và Môi trường trân trọng..."*, *"Thực hiện Chỉ thị số... của..."*, *"V/v triển khai thực hiện Quyết định số... của..."*.

---

## V. Giới hạn của phụ lục này

- Đây là văn phong **văn bản đi** — có thể khác văn phong văn bản đến từ UBND tỉnh, sở ngành khác, doanh nghiệp, công dân (súc tích hơn hoặc theo văn phong bên gửi).
- Chỉ có 7/12 lĩnh vực trong `rulebase.md` Mục III có ví dụ thật (KL, QLĐĐ, VPĐK, TNN, CNTY, và 1 ví dụ tổng hợp GĐ). Chưa có ví dụ cho: Trồng trọt & BVTV, Khuyến nông, Địa chất khoáng sản, Bảo vệ môi trường, Thủy sản, Phát triển nông thôn/NTM — cần bổ sung khi có văn bản mẫu.
- Nên định kỳ bổ sung phụ lục này mỗi khi có văn bản đi mới, và ưu tiên thu thập thêm **văn bản đến thật** để cân bằng nguồn văn phong.
