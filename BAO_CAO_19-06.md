# Báo cáo tiến độ — 19/06/2026

> Tổng hợp toàn bộ công việc đã làm trong ngày, kèm lợi ích cụ thể của từng phần.
> Dùng để báo cáo nhanh cho mentor — chi tiết kỹ thuật đầy đủ xem [EDA_FLOW.md](EDA_FLOW.md), [PLAN.md](PLAN.md).

---

## Tóm tắt 1 phút

Hôm nay tập trung **hoàn thiện toàn bộ module EDA** (11 idea trong `IDEAS.md`, chia 3 nhóm) và **test thật từng flow** (không chỉ đọc code) — qua đó phát hiện và fix **10 bug nghiêm trọng** mà nếu không test sẽ không biết tồn tại, trong đó có 1 bug khiến **toàn bộ flow Đánh giá/Suy luận mô hình cho bài toán classification bị crash 100%**. Ngoài ra thêm 1 tính năng UX mới: **góp ý → chạy lại** cho cả 6 loại experiment.

---

## Phần 1 — Hoàn thiện module EDA (11 idea, 3 nhóm)

### Nhóm 1 — Nền tảng (8 việc)

| Việc | Lợi ích |
|---|---|
| Bỏ hardcode domain điện lực, thêm `DOMAIN_GENERIC` | EDA dùng được cho **mọi loại dữ liệu**, không chỉ điện lực — đã verify với data bán lẻ, nhân sự |
| Tối ưu prompt planner (whitelist tên cột, few-shot, ràng buộc số bước) | Giảm hẳn lỗi LLM bịa tên cột/tham số không tồn tại |
| Tối ưu prompt insight (bắt buộc số liệu cụ thể) | Insight không còn chung chung kiểu "dữ liệu có vẻ ổn" |
| `user_query` được đọc ở Đánh giá/Suy luận/Huấn luyện | User góp ý "giải thích đơn giản, đừng dùng thuật ngữ" → AI thực sự điều chỉnh theo |
| Caption cho từng biểu đồ | User nhìn ảnh biết ngay đây là biểu đồ gì, không phải đọc hết insight mới hiểu |
| Màn xác nhận trước khi chạy + hỏi làm rõ khi câu hỏi mơ hồ | Tránh chạy nhầm, tốn LLM call vô ích khi user nhập sai/thiếu thông tin |
| Đăng ký `skewness_kurtosis` vào hệ thống tool | 1 dòng code, tận dụng được tool đã viết nhưng bị bỏ quên |

### Nhóm 2 — Phân tích sâu hơn (4 việc)

| Việc | Lợi ích |
|---|---|
| Thêm tool Bivariate/Multivariate (scatter, violin, boxplot theo nhóm, Spearman, group_stats) | EDA giờ phân tích đủ 3 tầng Univariate → Bivariate → Multivariate, trước đây thiếu hẳn tầng quan hệ giữa biến |
| Mutual Information scoring | Bắt được quan hệ phi tuyến mà Pearson correlation bỏ sót (vd nhiệt độ ảnh hưởng phụ tải kiểu chữ U) |
| Self-Generating Questions | Giải quyết pain point lớn nhất: **user không biết nên hỏi gì** — AI tự sinh 3-5 câu hỏi phân tích từ schema |
| Statistical Scoring (p-value tự động) | Insight có cơ sở thống kê thật, phân biệt được khác biệt thật với nhiễu ngẫu nhiên |

### Nhóm 3 — Nâng cao (3 việc)

| Việc | Lợi ích |
|---|---|
| Adaptive Replanning (2 giai đoạn) | Giai đoạn 1 chạy chắc kiểm tra chất lượng dữ liệu (không cần AI), giai đoạn 2 AI lập kế hoạch dựa trên kết quả thật — không bỏ sót, không lặp lại |
| Hypothesis Generation | EDA giờ có "giả thuyết khoa học" để kiểm chứng (XÁC NHẬN/BÁC BỎ/KHÔNG ĐỦ DỮ LIỆU), không chỉ chạy tool rồi tổng hợp — báo cáo có chiều sâu hơn hẳn |
| ydata-profiling hybrid | Quét toàn bộ dataset không bỏ sót cột nào, bổ trợ cho phần AI tự lập kế hoạch |

---

## Phần 2 — Bug nghiêm trọng phát hiện qua test thật (10 bug)

> Đây là phần quan trọng nhất của hôm nay: **chủ động chạy thử từng flow thật** (qua Docker, gọi trực tiếp agent) thay vì chỉ đọc code — nhờ vậy lộ ra nhiều bug mà code "nhìn qua tưởng ổn".

| # | Bug | Mức độ | Ảnh hưởng nếu không fix |
|---|---|---|---|
| 1 | Cột `overtime_hours` bị nhận nhầm là cột thời gian (do tên chứa chữ "time") | Cao | Toàn bộ dữ liệu bị set sai index, các cột liên quan biến mất, lỗi lan ra nhiều chỗ |
| 2 | Boxplot/violin được gọi trên cột nhị phân (0/1) | Trung bình | Biểu đồ vô nghĩa (chỉ có 2 vạch ngang) |
| 3 | Tính sai tên cột khi tìm tương quan mạnh + liệt kê trùng lặp cặp tương quan | Cao | Insight nói sai hoàn toàn cột nào tương quan với cột nào |
| 4 | Giả thuyết AI sinh ra không kiểm chứng được bằng tool có sẵn | Trung bình | Phần "kiểm chứng giả thuyết" luôn ra "không đủ dữ liệu", tính năng coi như vô dụng |
| 5 | Xử lý dữ liệu: cột nhị phân bị xóa mất nhãn thật khi loại outlier | **Nghiêm trọng** | Âm thầm phá hủy dữ liệu — nhãn `attrition`/`is_promoted` bị ép về 1 giá trị |
| 6 | Huấn luyện: dữ liệu mất cân bằng → model chỉ đoán 1 đáp án | **Nghiêm trọng** | Accuracy báo 90% nhưng model **vô dụng thực tế** — không nhận diện được trường hợp cần dự đoán |
| 7 | Đánh giá/Suy luận mô hình: lỗi thư viện vẽ biểu đồ | **Nghiêm trọng nhất** | **100% flow classification của Đánh giá + Suy luận mô hình bị crash**, không thể demo |
| 8 | Báo cáo tổng hợp không đọc được định dạng biểu đồ mới | Cao | Full Pipeline không xuất được báo cáo |
| 9 | Xử lý dữ liệu: cột target bị chuẩn hóa | Cao | RMSE/MAE báo ra là số vô nghĩa (0.3) thay vì số tiền thật (8.9 triệu) |
| 10 | Phân nhóm (Clustering): thiếu chuẩn hóa dữ liệu | **Nghiêm trọng** | 1 cột có số lớn nhất (lương) áp đảo hoàn toàn, "phân nhóm theo đặc điểm" thực chất chỉ là phân theo lương |

**Tất cả 10 bug đã fix và verify lại bằng cách chạy thật, không chỉ sửa code.**

---

## Phần 3 — Tính năng UX mới

| Việc | Lợi ích |
|---|---|
| Màn xác nhận trước khi chạy áp dụng cho **cả 6 loại experiment** (trước đó Full Pipeline và Tùy chỉnh bị thiếu) | Tránh chạy nhầm cấu hình ở loại experiment tốn kém nhất |
| Preprocessing Planner — Xử lý dữ liệu giờ đọc được yêu cầu của user | User có thể nói "đừng chuẩn hóa", "dùng z-score thay vì IQR" và hệ thống làm đúng theo |
| **Góp ý → chạy lại** cho cả 6 loại experiment | Sau khi xem kết quả, user góp ý ("tập trung vào region", "đừng mã hóa cột này") → hệ thống chạy lại, kết hợp kết quả cũ + góp ý mới, không cần làm lại từ đầu |
| Xem trước dữ liệu (5 dòng) trước khi chạy + trước/sau khi xử lý | User thấy rõ data thật trước khi tin vào kết quả phân tích |
| Cho phép nhập tên cột target thủ công | An toàn hơn khi data suy luận không có sẵn cột target để chọn từ danh sách |
| Tạm ẩn "Tùy chỉnh" khỏi UI | Loại bỏ lựa chọn gây nhiễu, không thực sự dùng dữ liệu — gọn câu chuyện demo còn 5 module + Full Pipeline |

---

## Phần 4 — Tài liệu

- **[EDA_FLOW.md](EDA_FLOW.md)** — mô tả chi tiết flow EDA hiện tại (10 bước), giải thích từng module/lớp làm gì — vấn đề gì — lợi ích gì, và 5 ưu điểm tổng thể. Thay thế phần EDA đã lỗi thời trong `FLOW.md`.
- **[PLAN.md](PLAN.md)** — cập nhật mục "Còn lại sau test" với 4 việc cụ thể cho lần sau.

---

## Còn lại cho lần sau (đã ghi trong PLAN.md)

| Việc | Ưu tiên |
|---|---|
| Đo Execution Pass Rate / Tool Hit Rate bằng số cụ thể cho slide | Cao |
| Retest flow merge nhiều file sau các thay đổi EDA | Trung bình |
| Kiểm tra báo cáo Full Pipeline khi có cả kết quả ML (mới test phần EDA) | Trung bình |
| UI polish (tiếng Việt đồng nhất, loading state) | Thấp |

---

## Điểm nhấn để báo cáo mentor

1. Module EDA đã đủ sâu (Uni/Bi/Multivariate + feature relationship + hypothesis-driven), tổng quát hóa được mọi domain — đã verify bằng 2 dataset hoàn toàn khác ngoài điện lực.
2. **Test thật phát hiện 10 bug mà đọc code không thấy** — trong đó có bug khiến cả flow classification của Đánh giá/Suy luận crash 100%. Đây là minh chứng quan trọng cho việc cần test thật trước khi defense, không chỉ tin vào code "nhìn ổn".
3. Hệ thống giờ có vòng phản hồi (góp ý → chạy lại) — tăng cảm giác "agent thông minh có tương tác" thay vì chạy 1 lần cứng.
