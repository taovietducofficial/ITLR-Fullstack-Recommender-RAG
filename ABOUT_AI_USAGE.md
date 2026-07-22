# Về việc dùng AI trong dự án này

Dự án này được xây dựng với sự hỗ trợ của AI coding assistant (Claude Code). Tôi không giấu điều
đó — nhưng "dùng AI" và "AI tự làm hết" là hai chuyện khác nhau, và phần việc thật sự thuộc về
tôi nằm ở những chỗ AI không tự quyết định được:

- **Kiến trúc & phạm vi**: quyết định tích hợp DataLake vào recommender theo hướng nào (batch qua
  Dagster thay vì CDC mới, giữ song song domain Olist, đóng vòng lặp dữ liệu về CF thay vì chỉ đổ
  vào dashboard một chiều) — đây là 3 quyết định đánh đổi thật, không có đáp án đúng sẵn, phải tự
  cân nhắc effort vs. giá trị.
- **Đọc hiểu và phản biện**: khi AI đề xuất thiết kế (vd star schema đầy đủ cho Gold layer), tôi
  yêu cầu giải thích rõ trade-off và tự quyết định bỏ bớt phần không cần thiết.
- **Debug thật**: khi chạy thử với dữ liệu Postgres thật, gặp lỗi sai password (do đoán nhầm giá
  trị mặc định) và lỗi cú pháp SQL (`;` cuối câu làm connectorx-Postgres crash trong khi
  connectorx-MySQL lại chấp nhận) — đây là 2 bug thật, chỉ lộ ra khi chạy trên môi trường thật,
  không phải bug lý thuyết.
- **Giới hạn thật**: máy chỉ có 7.7GB RAM, không đủ chạy hết stack Spark+Hive Metastore+Trino
  cùng lúc — phải tự quyết định dừng ở đâu, verify phần nào trước, phần nào để lại.

AI là công cụ tăng tốc viết code và tra cứu pattern — giống compiler hay IDE autocomplete, không
phải người thay tôi ra quyết định. Toàn bộ số liệu đánh giá khoa học (HitRate, off-policy
evaluation, Cohen's Kappa...) và các phát hiện trung thực về giới hạn dữ liệu trong README đều là
kết quả đo đạc thật trên code thật, không phải do AI "bịa" ra cho có vẻ chuyên nghiệp.

Nếu có câu hỏi kỹ thuật cụ thể về bất kỳ quyết định nào trong dự án, tôi trả lời được — đó mới là
thước đo đáng tin, không phải việc code có "mùi AI" hay không.
