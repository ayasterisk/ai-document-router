# Skill: classify_document

Xác định đặc điểm văn bản để rule engine dùng:
- `nguon_gui`: cap_tren | so_nganh | khac
- `linh_vuc`: đất đai / thủy lợi-nước / thủy sản / khoáng sản / trồng trọt / chăn nuôi / lâm nghiệp / môi trường / ...
- `khan`: true nếu hạn xử lý còn ≤ 2 ngày (hoặc trễ hạn)

Trả JSON: `{"nguon_gui": "...", "linh_vuc": "...", "khan": false, "giai_thich": "..."}`
