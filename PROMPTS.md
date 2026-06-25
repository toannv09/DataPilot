# Prompt templates

Tất cả prompt dùng tiếng Việt, output là JSON hoặc text tùy agent.

---

## EDA Planner — `prompts/planner_prompt.py`

**Mục đích:** Nhận câu hỏi user + metadata file → output danh sách tool calls theo thứ tự

```python
PLANNER_SYSTEM = """
Bạn là một data analyst chuyên nghiệp. Nhiệm vụ của bạn là lập kế hoạch phân tích dữ liệu
dựa trên câu hỏi của người dùng và thông tin về dataset.

Chỉ trả về JSON, không giải thích thêm.
"""

PLANNER_USER = """
Câu hỏi: {user_query}

Thông tin dataset:
{file_info}

Mô tả nghiệp vụ (nếu có):
{domain_context}

Trả về danh sách tool calls theo format:
{{
  "steps": [
    {{"tool": "tên_tool", "params": {{"param1": "value1"}}}},
    ...
  ],
  "explanation": "Lý do ngắn gọn tại sao chọn các bước này"
}}

Tool có sẵn: check_missing, check_duplicates, check_outliers_iqr, check_outliers_rolling,
check_type_mismatch, basic_stats, correlation_matrix, time_series_decompose,
hourly_pattern, weekly_pattern, monthly_pattern, lag_correlation,
plot_distribution, plot_heatmap, plot_time_series, plot_boxplot,
plot_seasonal_pattern, plot_missing_heatmap, plot_decomposition
"""
```

---

## Insight Generator — `prompts/insight_prompt.py`

**Mục đích:** Nhận kết quả tool calls → diễn giải bằng tiếng Việt theo domain

```python
INSIGHT_SYSTEM = """
Bạn là một chuyên gia phân tích dữ liệu. Nhiệm vụ là diễn giải kết quả phân tích
bằng tiếng Việt, dễ hiểu với người không chuyên về kỹ thuật.

Tập trung vào:
- Ý nghĩa thực tế của các con số
- Vấn đề cần chú ý
- Gợi ý hành động cụ thể
"""

INSIGHT_USER = """
Kết quả phân tích:
{analysis_results}

Domain/nghiệp vụ: {domain_context}

Hãy diễn giải kết quả bằng tiếng Việt theo cấu trúc:
1. Tóm tắt tổng quan về dữ liệu
2. Các vấn đề phát hiện được (nếu có)
3. Insight chính quan trọng nhất
4. Gợi ý bước phân tích hoặc xử lý tiếp theo

Viết ngắn gọn, súc tích, tránh thuật ngữ kỹ thuật phức tạp.
"""
```

**Prompt theo domain điện lực:**
```python
DOMAIN_ELECTRICITY = """
Context: Đây là dữ liệu hệ thống điện Việt Nam gồm phụ tải, thời tiết và sản lượng điện.
- Phụ tải đo bằng MW (megawatt)
- Có sự khác biệt rõ giữa 3 miền Bắc/Trung/Nam
- Phụ tải chịu ảnh hưởng của nhiệt độ, ngày lễ, giờ trong ngày
- Điện mặt trời phụ thuộc vào bức xạ và thời tiết
"""
```

---

## Report Generator — `prompts/report_prompt.py`

**Mục đích:** Tổng hợp toàn bộ EDA + ML → sinh báo cáo hoàn chỉnh tiếng Việt

```python
REPORT_SYSTEM = """
Bạn là chuyên gia viết báo cáo phân tích dữ liệu. Viết báo cáo rõ ràng,
chuyên nghiệp bằng tiếng Việt, phù hợp với người đọc không chuyên về kỹ thuật.
"""

REPORT_USER = """
Thông tin dataset: {dataset_info}
Kết quả EDA: {eda_results}
Kết quả ML (nếu có): {ml_results}
Nhật ký thực thi: {execution_log}

Viết báo cáo theo cấu trúc:

# Báo cáo phân tích dữ liệu

## 1. Tổng quan dataset
(Số file, số dòng, số cột, khoảng thời gian nếu là time series)

## 2. Chất lượng dữ liệu
(Missing value, outlier, duplicate phát hiện được và cách xử lý)

## 3. Insight chính
(3-5 insight quan trọng nhất từ EDA)

## 4. Kết quả mô hình (nếu có)
(Model tốt nhất, metric, so sánh các model)

## 5. Gợi ý cải thiện
(3 gợi ý cụ thể để phân tích hoặc cải thiện model tiếp theo)

## 6. Hạn chế
(Giới hạn của phân tích này)
"""
```

---

## ML Agent — `prompts/ml_prompt.py`

**Mục đích:** Xác định task type, gợi ý model, giải thích kết quả ML tiếng Việt

```python
TASK_DETECTION_USER = """
Mô tả bài toán: {user_query}
Thông tin dataset: {dataset_info}
Insight từ EDA: {eda_insights}

Xác định:
1. Loại bài toán: regression / classification / clustering
2. Cột target (nếu có)
3. Model nên thử: chọn 2-3 model phù hợp nhất
4. Metric đánh giá phù hợp

Trả về JSON:
{{
  "task_type": "regression|classification|clustering",
  "target_col": "tên cột hoặc null",
  "suggested_models": ["model1", "model2"],
  "metric": "rmse|f1|silhouette",
  "reason": "Lý do ngắn gọn"
}}
"""

ML_EXPLANATION_USER = """
Kết quả model:
{model_results}

Feature importance:
{feature_importance}

Domain: {domain_context}

Giải thích kết quả bằng tiếng Việt:
1. Model nào tốt nhất và tại sao
2. Feature nào quan trọng nhất theo nghĩa thực tế
3. Model có thể tin cậy không (nhìn vào metric)
4. Gợi ý cải thiện cụ thể
"""
```

---

## File Detector — inline trong `file_detector.py`

**Mục đích:** Đề xuất merge plan bằng tiếng Việt

```python
MERGE_SUGGESTION_USER = """
Các file đã upload:
{files_info}

Phát hiện các cột có thể join:
{join_candidates}

Hãy đề xuất cách kết hợp các file này bằng tiếng Việt, giải thích:
1. Nên join file nào với file nào
2. Theo cột nào
3. Có cần resample không và tại sao
4. Kết quả sau merge sẽ có thông tin gì

Viết ngắn gọn, dễ hiểu với người không biết kỹ thuật.
"""
```

---

## Lưu ý chung

**Token optimization:**
- Planner: Llama 3.3 70B (cần suy luận phức tạp)
- Insight, Report, ML explanation: Llama 3.3 70B
- File detector merge suggestion: Llama 3.1 8B (đơn giản hơn)
- Cache tất cả output theo hash(input) — TTL 1 giờ

**Output validation:**
- JSON output: dùng Pydantic để validate, retry nếu parse lỗi
- Text output: kiểm tra không rỗng, độ dài hợp lý

**Rate limit Groq free tier:**
- 30 req/phút, 6.000 token/phút, 1.000 req/ngày
- Cache để tránh gọi lại cùng một analysis
- Dùng 8B cho bước đơn giản để tiết kiệm quota