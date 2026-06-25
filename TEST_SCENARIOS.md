# Kịch bản test đầy đủ — demo cho mentor

> Mỗi kịch bản có: mục tiêu (chứng minh điều gì), file/query cụ thể, bước làm, và điểm cần
> chỉ ra cho mentor. Chạy thử lần lượt tối nay để chắc không lỗi trước khi demo thật.

## Chuẩn bị

- [ ] Docker đang chạy: `docker ps` thấy `vdt2026-ui-1` và `vdt2026-api-1` ở trạng thái `Up`
- [ ] Mở `http://localhost:8501`
- [ ] File test có sẵn ở `data/raw/`: `retail_sales.csv`, `hr_employees.csv` (dữ liệu giả lập, không phải điện lực — dùng để chứng minh hệ thống tổng quát hóa được)
- [ ] File domain mẫu: `data/domain/hr_domain.txt` (dùng để demo Hypothesis Generation)
- [ ] Dataset điện lực gốc vẫn còn: `phu_tai.csv`, `thoi_tiet.csv` (dùng cho TC7 — merge nhiều file)

---

## TC1 — Khám phá dữ liệu: tổng quát hóa domain + Self-Generating Questions

**Mục tiêu:** Chứng minh hệ thống không hardcode domain điện lực, và tự sinh câu hỏi khi user không biết hỏi gì.

1. Tạo bài toán mới → chọn **Khám phá dữ liệu**
2. Upload `hr_employees.csv` — **KHÔNG** upload file domain, **KHÔNG** nhập câu hỏi (để trống)
3. Bấm "Bắt đầu" → màn confirm sẽ hiện cảnh báo "Yêu cầu chưa rõ ràng" — đây là tính năng **Communicative Dehallucination**, có thể điền thử 1 câu trả lời hoặc bỏ qua
4. Bấm "Xác nhận & Chạy"

**Điểm chỉ ra cho mentor:**
- Insight không hề đề cập MW, phụ tải, miền Bắc/Trung/Nam (domain generic hoạt động đúng cho data nhân sự)
- Đọc phần "Tóm tắt" — kế hoạch phân tích phải có trọng tâm rõ ràng dù query để trống (vì có Self-Generating Questions dẫn hướng phía sau, không phải kế hoạch generic)
- Insight viết tự nhiên — không có kiểu `cột=số liệu`, có giải thích "vì sao" cho mỗi điểm

---

## TC2 — Khám phá dữ liệu: Hypothesis Generation + Statistical Scoring

**Mục tiêu:** Chứng minh EDA có "giả thuyết khoa học" để kiểm chứng, có p-value đứng sau insight.

1. Tạo bài toán mới → **Khám phá dữ liệu**
2. Upload `hr_employees.csv` + upload file domain `data/domain/hr_domain.txt`
3. Query: `Phân tích các yếu tố ảnh hưởng đến việc nhân viên nghỉ việc`
4. Xác nhận & Chạy

**Điểm chỉ ra cho mentor:**
- Cuối insight có section **"5. Kiểm chứng giả thuyết"** — mỗi giả thuyết có kết luận XÁC NHẬN/BÁC BỎ/KHÔNG ĐỦ DỮ LIỆU kèm giải thích tại sao bằng lời thường
- Trong insight chính, tìm câu có nhắc "có ý nghĩa thống kê" hoặc p-value dạng lời thường (vd "khác biệt này khó nói là ngẫu nhiên") — đây là Statistical Scoring tự động
- Có ít nhất 1 biểu đồ pairplot ("Quan hệ đồng thời giữa nhiều biến số") — multivariate tự động trigger, không cần AI chọn

---

## TC3 — Khám phá dữ liệu: time series tự động (retail_sales)

**Mục tiêu:** Chứng minh hệ thống tự nhận diện cột thời gian đúng, không nhận nhầm cột số.

1. Tạo bài toán mới → **Khám phá dữ liệu**
2. Upload `retail_sales.csv`, query: `phân tích xu hướng doanh thu theo thời gian`
3. Xác nhận & Chạy

**Điểm chỉ ra cho mentor:**
- Có biểu đồ "Biến động total_revenue theo thời gian" — đúng vì có cột `date` thật
- Charts có caption rõ ràng dưới mỗi ảnh

---

## TC4 — Xử lý dữ liệu: Preprocessing Planner đọc được yêu cầu

**Mục tiêu:** Chứng minh "Xử lý dữ liệu" không hardcode cứng, AI quyết định bước nào làm theo yêu cầu user.

**Lần 1 — mặc định:**
1. Tạo bài toán mới → **Xử lý dữ liệu**
2. Upload `hr_employees.csv`, để query trống
3. Xác nhận & Chạy → xem preview "trước" và "sau" khi xử lý

**Lần 2 — có yêu cầu cụ thể:**
4. Quay lại, tạo lại → **Xử lý dữ liệu**, query: `Giữ nguyên thang đo gốc của các cột số, đừng chuẩn hóa gì cả`
5. Xác nhận & Chạy

**Điểm chỉ ra cho mentor:**
- Lần 1: cột số bị chuẩn hóa (giá trị nhỏ, có số âm)
- Lần 2: preview "sau khi xử lý" — cột `monthly_salary` vẫn là số VND thật (hàng chục triệu), KHÔNG bị chuẩn hóa — đúng theo yêu cầu
- Đây là minh chứng AI thực sự đọc và phản hồi đúng `user_query`, không chạy 1 pipeline cứng

---

## TC5 — Huấn luyện mô hình: Classification với data mất cân bằng

**Mục tiêu:** Chứng minh model không bị "ăn gian" bằng cách chỉ đoán 1 đáp án khi data mất cân bằng.

1. Tạo bài toán mới → **Huấn luyện mô hình**
2. Upload `hr_employees.csv`
3. Loại bài toán: Classification, Cột target: `attrition`
4. Xác nhận & Chạy

**Điểm chỉ ra cho mentor:**
- Leaderboard — 3 model (LogisticRegression, RandomForest, XGBoost) có metric **khác nhau** (không phải 3 số giống y nhau — nếu giống y nhau tức là bug đoán-toàn-1-đáp-án đã quay lại)
- Có thể mở terminal nói thêm: "đã tự động xử lý mất cân bằng bằng class_weight + stratified split"

---

## TC6 — Huấn luyện mô hình: Clustering có scaling đúng

**Mục tiêu:** Chứng minh phân nhóm dựa trên nhiều đặc điểm thật, không bị 1 cột áp đảo.

1. Tạo bài toán mới → **Huấn luyện mô hình**
2. Upload `hr_employees.csv`
3. Loại bài toán: Clustering (không cần target)
4. Xác nhận & Chạy

**Điểm chỉ ra cho mentor:**
- `silhouette` ra số hợp lý (không cần giải thích sâu, chỉ cần chạy không lỗi, có biểu đồ so sánh model)
- Nói thêm: "đã fix bug — trước đây lương (số hàng chục triệu) áp đảo hoàn toàn tuổi/kinh nghiệm khi phân nhóm, giờ đã chuẩn hóa trước khi phân nhóm"

---

## TC7 — Đánh giá + Suy luận mô hình: Classification không crash

**Mục tiêu:** Đây là bug nghiêm trọng nhất đã fix — chứng minh giờ chạy được hoàn toàn.

**Đánh giá:**
1. Tạo bài toán mới → **Đánh giá mô hình**
2. Chọn model `.pkl` vừa train ở TC5 (LogisticRegression/RandomForestClassifier)
3. Upload lại `hr_employees.csv` làm test data
4. Xác nhận & Chạy

**Suy luận — với data KHÔNG có cột target:**
5. Tạo bài toán mới → **Suy luận mô hình**
6. Chọn cùng model
7. Upload `hr_employees.csv` nhưng **xóa cột `attrition` trước khi upload** (mở file, xóa cột, lưu lại — hoặc dùng file `hr_employees_no_target.csv` nếu đã chuẩn bị sẵn)
8. Để trống "Cột target" (vì dropdown sẽ không có `attrition` để chọn — đây chính là tình huống thật khi suy luận)
9. Xác nhận & Chạy

**Điểm chỉ ra cho mentor:**
- Cả 2 đều chạy thành công, có confusion matrix / kết quả dự đoán — KHÔNG còn crash như trước
- Bước Suy luận đặc biệt: dù không chọn được `attrition` trong dropdown (vì data mới không có), hệ thống vẫn tự biết đây là model dự đoán attrition (lấy từ thông tin lưu sẵn trong model lúc train) và vẫn dự đoán đúng

---

## TC8 — Full Pipeline: end-to-end + refinement loop

**Mục tiêu:** Chứng minh toàn bộ pipeline chạy mượt, và tính năng góp ý/chạy lại.

1. Tạo bài toán mới → **Full Pipeline**
2. Upload `hr_employees.csv`, query: `Dự đoán nhân viên có nghỉ việc hay không`
3. Cấu hình: Classification, target `attrition`
4. Xác nhận & Chạy → đi qua từng stage (EDA → Xử lý → Huấn luyện → Đánh giá), bấm "Tiếp tục" sau mỗi stage
5. Ở màn "Kết quả tổng hợp" cuối cùng — kéo xuống dưới, nhập vào ô góp ý: `Tôi muốn tập trung phân tích theo phòng ban (department)`
6. Bấm "Chạy lại với góp ý này"

**Điểm chỉ ra cho mentor:**
- Toàn bộ 4 stage chạy không lỗi, có báo cáo HTML xuất ra cuối cùng
- Sau khi góp ý, hệ thống chạy lại **toàn bộ pipeline**, lần này EDA tập trung theo phòng ban rõ rệt hơn — chứng minh hệ thống "lắng nghe" phản hồi thay vì chạy 1 lần cứng

---

## TC9 (bonus, nếu còn thời gian) — Merge nhiều file, dataset điện lực gốc

**Mục tiêu:** Chứng minh vẫn hoạt động tốt trên dataset gốc của đề tài, không chỉ data mới test.

1. Tạo bài toán mới → **Khám phá dữ liệu**
2. Upload cả `phu_tai.csv` và `thoi_tiet.csv`
3. Xác nhận & Chạy → màn đề xuất merge sẽ hiện trước, đọc gợi ý merge bằng tiếng Việt
4. Bấm "Đồng ý kết hợp"

**Điểm chỉ ra cho mentor:**
- Đề xuất merge đọc tự nhiên, đúng cột thời gian, đúng tần suất resample nếu khác nhau
- Sau khi merge, EDA chạy trên data đã ghép — có thể chỉ ra biểu đồ lag_correlation giữa thời tiết và phụ tải (đặc trưng domain điện lực)

---

## Checklist nhanh trước khi đi ngủ (chạy hết 1 lượt, không cần demo kỹ)

- [ ] TC1 — chạy được, không lỗi
- [ ] TC2 — có section Kiểm chứng giả thuyết
- [ ] TC3 — có chart time series
- [ ] TC4 — preview trước/sau khác nhau đúng theo góp ý
- [ ] TC5 — 3 model leaderboard có số khác nhau
- [ ] TC6 — clustering chạy không lỗi
- [ ] TC7 — Đánh giá + Suy luận classification cả 2 không crash
- [ ] TC8 — Full Pipeline chạy hết 4 stage + refinement loop hoạt động
- [ ] TC9 — merge 2 file điện lực vẫn ổn (nếu kịp test)

Nếu có TC nào lỗi tối nay — ưu tiên fix TC5/TC7 trước (đây là 2 bug nghiêm trọng nhất từng gặp), các TC còn lại có thể bỏ qua nếu hết thời gian.
