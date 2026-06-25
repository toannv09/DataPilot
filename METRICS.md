# Bộ tiêu chí đánh giá

Đây là đầu ra số 3 theo yêu cầu mentor. Đánh giá 3 chiều: LLM output, data analysis, ML model.

---

## Nhóm 1 — Task Success (ưu tiên cao nhất)

### 1.1 Planning Success Rate
**Đo lường:** Tỷ lệ EDA Planner hiểu đúng ý định và tạo ra plan hợp lý

**Cách đo:**
- Tạo 20 test cases với câu hỏi đa dạng
- Đánh giá thủ công: plan có chứa đúng tool cần thiết không? (1/0)
- `Planning Success Rate = số plan đúng / tổng test cases`

**Target:** ≥ 80%

---

### 1.2 Execution Pass Rate
**Đo lường:** Tỷ lệ code/tool calls chạy thành công không lỗi

**Cách đo:**
```python
def measure_execution_pass_rate(test_cases):
    success = 0
    for case in test_cases:
        try:
            result = execute_plan(case['plan'], case['df'])
            if result is not None:
                success += 1
        except Exception:
            pass
    return success / len(test_cases)
```

**Target:** ≥ 90%

---

## Nhóm 2 — Efficiency (thể hiện hybrid approach)

### 2.1 Token Consumption
**Đo lường:** So sánh token tiêu thụ giữa hybrid approach vs pure code generation

**Cách đo:**
- Chạy cùng 10 test cases với 2 cách
- Log token count từ Groq API response header
- So sánh tổng token

```python
# Log trong llm/client.py
def call_llm(prompt, model):
    response = groq_client.chat.completions.create(...)
    tokens_used = response.usage.total_tokens
    wandb.log({"tokens_per_call": tokens_used})
    return response
```

**Expected:** Hybrid tiết kiệm 30-50% token so với pure code gen

---

### 2.2 Retry Iterations
**Đo lường:** Số lần retry trung bình để tool/code chạy thành công

**Cách đo:**
```python
# Log trong eda_agent.py
retry_count = 0
while retry_count < 3:
    try:
        result = execute_step(step)
        wandb.log({"retry_count": retry_count})
        break
    except Exception as e:
        retry_count += 1
        # fix và retry
```

**Target:** Trung bình ≤ 1.5 lần retry

---

## Nhóm 3 — Output Quality

### 3.1 EDA Completeness Checklist
**Đo lường:** Báo cáo EDA có đủ các thành phần cần thiết không

**Checklist (1 điểm mỗi mục):**
- [ ] Thống kê cơ bản (mean, median, std)
- [ ] Kiểm tra missing value
- [ ] Kiểm tra outlier
- [ ] Correlation matrix
- [ ] Biểu đồ phân phối
- [ ] Pattern theo thời gian (nếu time series)
- [ ] Nhận xét bằng tiếng Việt
- [ ] Gợi ý bước tiếp theo

**Score = số mục có / 8**

**Target:** ≥ 7/8

---

### 3.2 Insight Quality (LLM tự đánh giá)
**Đo lường:** Chất lượng insight tiếng Việt có phù hợp domain không

**Cách đo:** Dùng LLM làm judge (tiết kiệm hơn human eval)

```python
JUDGE_PROMPT = """
Đánh giá chất lượng insight sau trên thang 1-5:
Insight: {insight_text}
Domain: {domain}
Tiêu chí: (1) Có liên quan đến câu hỏi? (2) Diễn giải đúng domain? (3) Gợi ý hữu ích?
Chỉ trả về số điểm từ 1-5.
"""
```

**Target:** Trung bình ≥ 3.5/5

---

## Nhóm 4 — ML Model Quality

### 4.1 Baseline Model Performance

**Regression (dự báo phụ tải):**

| Metric | Target |
|--------|--------|
| RMSE | < 500 MW |
| MAE | < 300 MW |
| R² | > 0.85 |

**Classification:**

| Metric | Target |
|--------|--------|
| F1 Score | > 0.75 |
| Accuracy | > 0.80 |

*Target có thể điều chỉnh sau khi chạy thử trên dataset thực.*

---

### 4.2 Complexity Levels Robustness

Chia test cases thành 3 cấp độ, mỗi cấp 5 cases:

| Level | Mô tả | Ví dụ |
|-------|-------|-------|
| Easy | Yêu cầu đơn giản, 1 file | "Dữ liệu phụ tải có bao nhiêu missing value?" |
| Medium | Nhiều bước, 2 file | "Phân tích ảnh hưởng nhiệt độ lên phụ tải miền Nam" |
| Hard | Phức tạp, custom logic | "Loại bỏ outlier theo IQR, tạo feature theo giờ, so sánh RandomForest vs XGBoost" |

**Đo:** Execution Pass Rate theo từng level

---

## Tổng hợp dashboard

```python
# Chạy tất cả metrics và log vào W&B
def run_evaluation(test_cases, df):
    metrics = {
        "planning_success_rate": measure_planning_success(test_cases),
        "execution_pass_rate": measure_execution_pass_rate(test_cases),
        "avg_retry_count": measure_avg_retry(test_cases),
        "token_hybrid_vs_pure": measure_token_comparison(test_cases),
        "eda_completeness": measure_eda_completeness(test_cases),
        "ml_rmse": measure_ml_performance(df),
    }
    wandb.log(metrics)
    return metrics
```

---

## Không làm (ngoài scope prototype)

- Win Rate / Human Preference — cần nhiều người đánh giá, không thực tế
- Prompt Robustness (typo, ambiguous) — nice-to-have tuần 4 nếu còn thời gian
- Data-Table Accuracy so sánh từng cell — tốn thời gian chuẩn bị ground truth