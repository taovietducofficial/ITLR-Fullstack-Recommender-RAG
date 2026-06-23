# Đối chứng phân phối dữ liệu synthetic vs thật (Trụ cột I)

| Thuộc tính | Synthetic | Thật |
|---|---|---|
| Số item | 50002 | 4088 |
| Số chuyên mục | 27 | 4 |
| Độ dài mô tả TB | 155.8 | 218.2 |
| Độ dài mô tả trung vị | 155.0 | 225.0 |
| Kích thước từ vựng (title, mẫu 5k) | 564 | 2945 |

**Top chuyên mục (synthetic):** {'Phát triển Game': 2014, 'Phân tích nghiệp vụ (BA)': 1993, 'Đồ họa máy tính': 1976, 'An ninh mạng': 1963, 'Điện toán lượng tử': 1962, 'Khoa học máy tính': 1954, 'Kiểm thử phần mềm': 1945, 'IoT & Hệ thống nhúng': 1938}

**Top chuyên mục (thật):** {'Web Development': 1190, 'Computer Science': 1125, 'Information Technology': 942, 'Data Science': 831}

*Biện luận tính đại diện: so sánh độ dài mô tả & độ phong phú từ vựng để đánh giá dữ liệu synthetic có mô phỏng hợp lý dữ liệu thật không; chênh lệch lớn -> nêu rõ giới hạn. Catalog thật là tiếng Anh (Coursera/Udemy) — embeddings đa ngữ xử lý chéo Anh–Việt; nhãn category giữ nguyên tiếng Anh.*