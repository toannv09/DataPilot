# Kế hoạch thực hiện chi tiết

> Dựa trên IDEAS.md — 11 ideas chia 3 nhóm theo thứ tự ưu tiên.
> Mỗi task ghi rõ: file cần sửa, thay đổi cụ thể, cách test, chú ý.
> **Nguyên tắc:** Hoàn thành và test từng task trước khi sang task tiếp theo. Không làm song song.

---

## NHÓM 1 — Làm ngay (~2–3 ngày)

> Tất cả độc lập, không dependency. Làm trước để có nền ổn định cho Nhóm 2.

---

### TASK 1.1 — Fix DOMAIN_ELECTRICITY hardcode
**Từ:** IDEA-04 (2.2)
**Effort:** 15 phút
**File:** `llm/prompts/insight_prompt.py`, `agents/insight_generator.py`

**Làm gì:**

1. Thêm `DOMAIN_GENERIC` vào `insight_prompt.py`:
```python
DOMAIN_GENERIC = """
Không có thông tin domain cụ thể. Hãy phân tích theo nguyên tắc chung:
- Diễn giải tên cột theo nghĩa đen (vd: cột "revenue" → doanh thu)
- Tập trung vào pattern thống kê: phân phối, tương quan, bất thường, xu hướng
- Dùng ngôn ngữ trung lập ("cột này", "giá trị này") thay vì giả định nghiệp vụ
- Mô tả pattern quan sát được, không suy diễn nguyên nhân nghiệp vụ
"""
```

2. Sửa `insight_generator.py` dòng 39:
```python
# Trước
domain_context or DOMAIN_ELECTRICITY

# Sau
domain_context or DOMAIN_GENERIC
```

**Test:** Upload dataset không liên quan điện lực (vd: file sales), không nhập domain → insight không đề cập MW, phụ tải, miền Bắc/Trung/Nam.

**Chú ý:** `DOMAIN_ELECTRICITY` vẫn giữ nguyên trong file — dùng khi muốn demo dataset điện lực có context tốt hơn.

---

### TASK 1.2 — Prompt optimization: PLANNER
**Từ:** IDEA-04 (4.1)
**Effort:** 1–2 giờ
**File:** `llm/prompts/planner_prompt.py`, `agents/eda_planner.py`, `agents/eda_agent.py`

**Làm gì:**

**Bước 1** — Sửa `PLANNER_USER` trong `planner_prompt.py`, thêm 4 phần:

```python
PLANNER_USER = """
Câu hỏi: {user_query}

Thông tin dataset:
{file_info}

Các cột có trong dataset (CHỈ dùng đúng tên này, không tự đặt tên khác):
{available_columns}

Mô tả nghiệp vụ (nếu có):
{domain_context}

Quy tắc bắt buộc:
- Sinh 4–8 bước, không nhiều hơn
- Bước đầu tiên phải là check_missing hoặc check_duplicates
- Nếu dataset có cột thời gian (DatetimeIndex): phải có ít nhất 1 bước time series
- Kết thúc bằng ít nhất 1 visualization

KHÔNG được:
- Dùng tên param khác ngoài danh sách (không dùng "column", "dataset", "data", "dataframe")
- Gọi tool không có trong danh sách bên dưới
- Thêm text hoặc giải thích bên ngoài JSON

Ví dụ output hợp lệ:
{{
  "steps": [
    {{"tool": "check_missing", "params": {{}}}},
    {{"tool": "basic_stats", "params": {{"cols": ["col_a", "col_b"]}}}},
    {{"tool": "plot_time_series", "params": {{"col": "col_a"}}}}
  ],
  "explanation": "Lý do chọn các bước này"
}}

Tool có sẵn (tên tool và params chính xác — chỉ dùng đúng tên param này):
...
"""
```

**Bước 2** — Sửa `eda_planner.py`, thêm param `available_columns`:
```python
def plan(user_query, file_info, domain_context="", available_columns=None):
    prompt = PLANNER_USER.format(
        user_query=user_query,
        file_info=file_info,
        domain_context=domain_context,
        available_columns=", ".join(available_columns) if available_columns else "Không rõ",
    )
```

**Bước 3** — Sửa `eda_agent.py`, truyền `list(self.df.columns)`:
```python
plan_data = eda_plan(
    context.user_query,
    detection["schemas"],
    context.domain_context,
    available_columns=list(self.df.columns),   # thêm dòng này
)
```

**Test:** Chạy EDA, xem log — kiểm tra không còn `"error": "unexpected keyword argument"`. Nếu vẫn còn lỗi ở bước nào, xem LLM sinh param gì → bổ sung vào negative instruction.

**Chú ý:**
- Giữ nguyên `_normalize_params` như backup — không xóa dù đã fix prompt
- Few-shot example dùng tên cột generic (`col_a`, `col_b`) không phải tên cột thật → LLM không bị anchor vào tên cố định

---

### TASK 1.3 — Prompt optimization: INSIGHT constraint
**Từ:** IDEA-04 (4.2)
**Effort:** 30 phút
**File:** `llm/prompts/insight_prompt.py`

**Làm gì:** Sửa `INSIGHT_USER`, thêm 3 constraint:
```python
INSIGHT_USER = """
Kết quả phân tích:
{analysis_results}

Domain/nghiệp vụ: {domain_context}

Hãy diễn giải kết quả bằng tiếng Việt theo cấu trúc:
1. Tóm tắt tổng quan về dữ liệu (số dòng, cột, khoảng giá trị)
2. Các vấn đề phát hiện được (missing, outlier, duplicate nếu có)
3. Insight chính — với mỗi insight: (1) quan sát → (2) nguyên nhân có thể → (3) gợi ý hành động
4. Gợi ý bước phân tích hoặc xử lý tiếp theo

Yêu cầu bắt buộc:
- Mỗi insight phải kèm con số cụ thể từ kết quả (vd: "mean=18.500, std=2.300")
- Không viết nhận xét định tính mà không có số liệu dẫn chứng
- Tổng độ dài: 250–400 từ
- Mỗi section tối đa 3 câu, section 3 tối đa 5 bullet points
"""
```

**Test:** Đọc output insight — mỗi điểm phải có con số. Nếu LLM vẫn viết chung chung, thêm vào SYSTEM: "Không được viết insight mà không có số liệu".

---

### TASK 1.4 — Prompt optimization: ML prompts
**Từ:** IDEA-04 (4.3, 4.4)
**Effort:** 30 phút
**File:** `llm/prompts/ml_prompt.py`

**Làm gì:**

1. Thêm whitelist model vào `TASK_DETECTION_USER`:
```python
"""
Model có sẵn (chỉ chọn từ danh sách này):
- regression: LinearRegression, Ridge, RandomForestRegressor, XGBRegressor
- classification: LogisticRegression, RandomForestClassifier, XGBClassifier
- clustering: KMeans

Ví dụ output:
{{"task_type": "regression", "target_col": "revenue",
  "suggested_models": ["LinearRegression", "XGBRegressor"],
  "metric": "rmse", "reason": "Dự báo giá trị liên tục"}}
"""
```

2. Thêm guard vào `REPORT_USER`:
```python
"Nếu ml_results là null hoặc rỗng: bỏ qua section 4 hoàn toàn, không suy đoán kết quả ML."
```

---

### TASK 1.5 — user_query cho Evaluation + Inference + Training
**Từ:** IDEA-09 Nhóm 1
**Effort:** 30 phút
**File:** `llm/prompts/ml_prompt.py`, `agents/evaluation_agent.py`, `agents/inference_agent.py`, `agents/training_agent.py`

**Làm gì:**

1. Sửa `ML_EXPLANATION_USER` — thêm field:
```python
ML_EXPLANATION_USER = """
Yêu cầu của người dùng: {user_query}

Kết quả model: {model_results}
Feature importance: {feature_importance}
Domain: {domain_context}

Giải thích kết quả bằng tiếng Việt, điều chỉnh theo yêu cầu user:
...
"""
```

2. Sửa `EXPLAIN_PREDICTION_PROMPT` trong `inference_agent.py` — thêm `{user_query}`.

3. Truyền `context.user_query` vào `call_llm` ở 3 agent.

**Test:** Nhập query "giải thích đơn giản, không dùng thuật ngữ kỹ thuật" → output không có RMSE, F1, không có "heteroscedasticity".

---

### TASK 1.6 — Per-chart Caption (Hướng A — template)
**Từ:** IDEA-11
**Effort:** 30 phút
**File:** `agents/eda_agent.py`, `ui/components/chart_viewer.py`, `agents/report_generator.py`

**Làm gì:**

1. Thêm `CAPTION_TEMPLATES` trong `eda_agent.py`:
```python
CAPTION_TEMPLATES = {
    "plot_distribution":    "Phân phối của cột {col}",
    "plot_time_series":     "Biến động {col} theo thời gian",
    "plot_heatmap":         "Ma trận tương quan",
    "plot_boxplot":         "Boxplot — {col}",
    "plot_decomposition":   "Phân rã trend/seasonality — {col}",
    "plot_seasonal_pattern":"Pattern theo {by} — {col}",
    "plot_missing_heatmap": "Bản đồ missing value",
    "plot_scatter":         "{col1} vs {col2}",
    "plot_violin":          "Phân phối violin — {col}",
    "plot_mi_scores":       "Mutual Information score với target",
}

def _make_caption(tool_name, params):
    template = CAPTION_TEMPLATES.get(tool_name, tool_name.replace("_", " ").title())
    try:
        return template.format(**params)
    except KeyError:
        return template
```

2. Đổi `charts.append(output)` → `charts.append({"path": output, "caption": _make_caption(tool_name, params)})`.

3. Sửa `chart_viewer.py`:
```python
def render_charts(charts):
    for item in charts:
        path = item["path"] if isinstance(item, dict) else item
        caption = item.get("caption", "") if isinstance(item, dict) else ""
        st.image(path)
        if caption:
            st.caption(caption)
```

**Chú ý:** Dùng `isinstance(item, dict)` để backward compatible — pipeline_agent gộp charts từ nhiều agent, có thể có format cũ.

**Test:** Chạy EDA, xem charts có caption bên dưới không. Check pipeline không crash khi gộp charts.

---

### TASK 1.7 — Input Summary + Clarification
**Từ:** IDEA-06 + IDEA-07 (gộp lại)
**Effort:** 1–2 giờ
**File:** `ui/views/run_experiment.py`

**Làm gì:**

1. Thêm hàm `_detect_ambiguity(user_query)`:
```python
GENERIC_WORDS = {"phân tích", "xem", "check", "thử", "xem thử", "phân tích dữ liệu", ""}

def _detect_ambiguity(user_query):
    q = user_query.strip().lower()
    return len(q) < 15 or q in GENERIC_WORDS
```

2. Thêm hàm `_render_input_summary(context)`:
```python
def _render_input_summary(context):
    st.subheader("Xác nhận trước khi chạy")
    st.info(f"""
**Loại experiment:** {context.experiment_type}
**File dữ liệu:** {', '.join(f'{k} ({len(v)} dòng × {len(v.columns)} cột)' for k, v in context.files.items())}
**Yêu cầu:** {context.user_query or '_(không có)_'}
**Domain:** {'Từ file nghiệp vụ' if context.domain_context else 'Dùng phân tích chung (không có file nghiệp vụ)'}
    """)

    if _detect_ambiguity(context.user_query):
        st.warning("Yêu cầu chưa rõ ràng. Bạn có thể làm rõ thêm:")
        q1 = st.text_input("Bạn muốn tập trung vào cột nào? (để trống nếu phân tích tất cả)")
        q2 = st.text_input("Bạn muốn phân tích theo thời gian, phân phối, hay quan hệ giữa các cột?")
        if q1 or q2:
            extra = " ".join(filter(None, [q1, q2]))
            context.user_query = f"{context.user_query} {extra}".strip()
            st.session_state.context = context
```

3. Sửa `render()` trong `run_experiment.py` — thêm bước confirm:
```python
# Thêm session state
if "input_confirmed" not in st.session_state:
    st.session_state.input_confirmed = False

# Trước khi chạy agent
if not st.session_state.input_confirmed:
    _render_input_summary(context)
    col1, col2 = st.columns(2)
    if col1.button("Xác nhận & Chạy"):
        st.session_state.input_confirmed = True
        st.rerun()
    if col2.button("Chỉnh lại"):
        st.session_state.page = "experiment_config"
        st.rerun()
    return
```

4. Reset `input_confirmed = False` khi user quay lại config.

**Chú ý:** Clarification questions chỉ hiện khi `_detect_ambiguity()` trả về True. Không hỏi khi query đã rõ ràng.

---

### TASK 1.8 — skewness_kurtosis vào TOOL_REGISTRY
**Từ:** IDEA-02 (quick win)
**Effort:** 5 phút
**File:** `agents/eda_agent.py`

**Làm gì:** Thêm 1 dòng vào `TOOL_REGISTRY`:
```python
"skewness_kurtosis": stats_engine.skewness_kurtosis,
```

Và thêm vào `planner_prompt.py` danh sách tool:
```
- skewness_kurtosis(col): col là tên 1 cột số
```

**Test:** Chạy EDA, xem plan có gọi `skewness_kurtosis` không. Nếu không, thêm vào few-shot example.

---

## NHÓM 2 — Core EDA (~3–4 ngày)

> Làm sau khi Nhóm 1 đã ổn định và test xong.

---

### TASK 2.1 — Hoàn thiện tool Bi/Multivariate
**Từ:** IDEA-02
**Effort:** 2–3 giờ
**File:** `tools/stats_engine.py`, `tools/viz_engine.py`, `agents/eda_agent.py`, `llm/prompts/planner_prompt.py`

**Làm gì:**

**stats_engine.py** — thêm:
```python
def spearman_correlation(df, cols):
    """Spearman correlation — robust hơn Pearson khi có outlier."""
    return df[cols].corr(method="spearman")

def normality_test(df, col):
    """Shapiro-Wilk (n<5000) hoặc KS test."""
    from scipy import stats
    series = df[col].dropna()
    if len(series) < 5000:
        stat, p = stats.shapiro(series[:5000])
        test = "shapiro"
    else:
        stat, p = stats.kstest(series, "norm")
        test = "ks"
    return {"col": col, "test": test, "statistic": float(stat),
            "p_value": float(p), "is_normal": p > 0.05}
```

**viz_engine.py** — thêm:
```python
def plot_scatter(df, col1, col2):
    """Scatter plot + regression line giữa 2 cột."""
    fig, ax = plt.subplots(figsize=(7, 5))
    sns.regplot(data=df, x=col1, y=col2, ax=ax, scatter_kws={"alpha": 0.4})
    ax.set_title(f"{col1} vs {col2}")
    return _save(fig, f"scatter_{col1}_{col2}")

def plot_violin(df, col):
    """Violin plot — thấy cả shape phân phối lẫn outlier."""
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.violinplot(y=df[col].dropna(), ax=ax)
    ax.set_title(f"Violin plot — {col}")
    return _save(fig, f"violin_{col}")

def plot_boxplot_by(df, col, by):
    """Boxplot nhóm theo cột categorical."""
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.boxplot(data=df, x=by, y=col, ax=ax)
    ax.set_title(f"{col} theo {by}")
    return _save(fig, f"boxplot_by_{col}_{by}")
```

**Chú ý:** `plot_scatter` dùng `sns.regplot` — nếu dataset lớn (>10k rows) thêm `sample_frac=0.3` để tránh render chậm.

**Cập nhật** `TOOL_REGISTRY` và `planner_prompt.py` với tool mới.

---

### TASK 2.2 — Mutual Information scoring
**Từ:** IDEA-03 Hướng A
**Effort:** 2–3 giờ
**File:** `tools/relationship.py` (mới), `tools/viz_engine.py`, `agents/eda_agent.py`, `llm/prompts/planner_prompt.py`

**Làm gì:**

Tạo `tools/relationship.py`:
```python
from sklearn.feature_selection import mutual_info_regression, mutual_info_classif
from tools.schema_analyzer import detect_datetime_columns

def mutual_info_scores(df, target_col):
    """MI score giữa mỗi feature và target. Bắt được quan hệ non-linear."""
    dt_cols = detect_datetime_columns(df)
    X = df.drop(columns=[target_col] + dt_cols, errors="ignore") \
          .select_dtypes(include="number").dropna()
    y = df[target_col].loc[X.index].dropna()
    X = X.loc[y.index]

    # Tự detect regression vs classification
    is_continuous = y.nunique() > 20
    fn = mutual_info_regression if is_continuous else mutual_info_classif
    scores = fn(X, y, random_state=42)
    result = dict(zip(X.columns, scores))
    return dict(sorted(result.items(), key=lambda x: -x[1]))  # sort desc
```

Thêm `plot_mi_scores()` vào `viz_engine.py`:
```python
def plot_mi_scores(df, scores):
    """Bar chart MI score ranking."""
    fig, ax = plt.subplots(figsize=(8, max(4, len(scores) * 0.4)))
    cols = list(scores.keys())
    vals = list(scores.values())
    sns.barplot(x=vals, y=cols, ax=ax, orient="h")
    ax.set_title("Mutual Information Score với target")
    ax.set_xlabel("MI Score")
    return _save(fig, "mi_scores")
```

**Chú ý:**
- `mutual_info_scores` cần `target_col` — LLM phải biết cột nào là target. Thêm hướng dẫn trong `planner_prompt.py`: "Tool này cần target_col — chỉ gọi khi user đề cập cột target hoặc bài toán prediction rõ ràng."
- Nếu không có target_col rõ ràng, bỏ qua tool này.

---

### TASK 2.3 — Self-Generating Questions
**Từ:** IDEA-05 Hướng A
**Effort:** 3–4 giờ
**File:** `agents/question_generator.py` (mới), `agents/eda_agent.py`, `llm/prompts/planner_prompt.py`

**Làm gì:**

Tạo `agents/question_generator.py`:
```python
from llm.client import MODEL_8B, call_llm
import json, re

QUESTION_GEN_SYSTEM = """
Bạn là data analyst. Nhìn vào schema dataset, sinh ra các câu hỏi phân tích
phù hợp nhất để hiểu dữ liệu này. Chỉ trả về JSON.
"""

QUESTION_GEN_USER = """
Schema dataset:
{schemas}

Câu hỏi của user (có thể rỗng): {user_query}
Có DatetimeIndex: {has_datetime}

Sinh 3–5 câu hỏi phân tích cụ thể, trả về:
{{"questions": ["câu hỏi 1", "câu hỏi 2", ...],
  "focus": "tóm tắt 1 câu về trọng tâm phân tích"}}

Ưu tiên câu hỏi liên quan đến: phân phối, chất lượng dữ liệu, tương quan,
pattern theo thời gian (nếu có datetime), outlier.
"""

def generate_questions(schemas, user_query="", domain_context="", has_datetime=False):
    prompt = QUESTION_GEN_USER.format(
        schemas=json.dumps(schemas, ensure_ascii=False, default=str)[:3000],
        user_query=user_query or "(không có)",
        has_datetime=has_datetime,
    )
    response = call_llm(prompt, system=QUESTION_GEN_SYSTEM, model=MODEL_8B)
    try:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        return json.loads(match.group(0)) if match else {"questions": [], "focus": ""}
    except Exception:
        return {"questions": [], "focus": ""}
```

Sửa `eda_agent.run()` — thêm bước question generation:
```python
# Sau detect(), trước eda_plan()
has_datetime = bool(detect_datetime_columns(self.df))
question_data = generate_questions(
    detection["schemas"], context.user_query,
    context.domain_context, has_datetime
)
questions = question_data.get("questions", [])

# Gộp questions vào user_query cho planner
enriched_query = context.user_query
if questions:
    enriched_query += "\n\nCác câu hỏi cần trả lời:\n" + "\n".join(f"- {q}" for q in questions)

plan_data = eda_plan(enriched_query, detection["schemas"], ...)
```

**Chú ý:**
- Dùng `MODEL_8B` cho question generation — nhanh hơn, đủ dùng
- Không thêm quá 5 câu hỏi — planner sẽ bị overwhelm
- Nếu user_query đã rõ ràng và dài (>50 chars), có thể skip question generation

---

### TASK 2.4 — Statistical Scoring Phần 1
**Từ:** IDEA-08 Phần 1
**Effort:** 2–3 giờ
**File:** `tools/scorer.py` (mới), `agents/eda_agent.py`, `llm/prompts/insight_prompt.py`

**Làm gì:**

Tạo `tools/scorer.py`:
```python
from scipy import stats
import pandas as pd

def score_trend(series):
    """Mann-Kendall trend test. p_value < 0.05 → xu hướng có ý nghĩa."""
    try:
        from scipy.stats import kendalltau
        n = len(series.dropna())
        tau, p = kendalltau(range(n), series.dropna().values)
        return {"tau": round(float(tau), 3), "p_value": round(float(p), 4),
                "significant": p < 0.05, "direction": "tăng" if tau > 0 else "giảm"}
    except Exception:
        return {"significant": False}

def score_correlation(r, n):
    """P-value cho Pearson correlation."""
    try:
        t = r * ((n - 2) ** 0.5) / ((1 - r**2) ** 0.5)
        p = 2 * (1 - stats.t.cdf(abs(t), df=n-2))
        return {"r": round(r, 3), "p_value": round(float(p), 4), "significant": p < 0.05}
    except Exception:
        return {"significant": False}

def score_distribution_diff(df, col, by):
    """Kruskal-Wallis test — khác biệt phân phối giữa các nhóm."""
    try:
        groups = [g[col].dropna().values for _, g in df.groupby(by)]
        stat, p = stats.kruskal(*groups)
        return {"statistic": round(float(stat), 3), "p_value": round(float(p), 4),
                "significant": p < 0.05}
    except Exception:
        return {"significant": False}
```

Sửa `eda_agent.execute_plan()` — gắn score sau tool stats:
```python
SCORABLE_TOOLS = {"time_series_decompose", "correlation_matrix", "hourly_pattern",
                  "weekly_pattern", "monthly_pattern", "lag_correlation"}

if tool_name in SCORABLE_TOOLS and tool_name not in CHART_TOOLS:
    # gắn thêm significance score vào result
    if tool_name in ("hourly_pattern", "weekly_pattern", "monthly_pattern"):
        series = output[col] if isinstance(output, pd.DataFrame) else None
        if series is not None:
            results[tool_name + "_score"] = score_trend(series)
```

Cập nhật `INSIGHT_USER` — thêm hướng dẫn dùng score:
```
Khi kết quả có trường "significant: true" và "p_value < 0.05":
ưu tiên đề cập insight đó trước, đánh dấu là "có ý nghĩa thống kê".
```

---

## NHÓM 3 — Depth & Polish (~3–4 ngày, nếu còn thời gian)

---

### TASK 3.1 — Adaptive Replanning (2-Phase)
**Từ:** IDEA-10
**Effort:** 3–4 giờ
**File:** `agents/eda_agent.py`, `llm/prompts/planner_prompt.py`

**Làm gì:**

Tách `eda_agent.run()` thành 2 phase:
```python
async def run(self, context=None):
    detection = self.detect()
    self.df = self._prepare_dataframe(detection)

    # Phase 1: quality checks cứng — không cần LLM plan
    phase1_tools = ["check_missing", "check_duplicates", "check_type_mismatch", "basic_stats"]
    phase1_results, _, phase1_log = self._run_fixed_tools(phase1_tools)

    # Trigger-based auto-append
    extra_steps = _trigger_rules(phase1_results, self.df)

    # Phase 2: LLM plan với context từ Phase 1
    plan_data = eda_plan(
        context.user_query, detection["schemas"],
        context.domain_context,
        phase1_results=phase1_results,  # context mới
    )
    plan_data["steps"] = extra_steps + plan_data.get("steps", [])

    results2, charts, log2 = self.execute_plan(plan_data, self.df)
    results = {**phase1_results, **results2}
    ...
```

Trigger rules:
```python
def _trigger_rules(phase1_results, df):
    extra = []
    missing = phase1_results.get("check_missing", {})
    if missing.get("pct_missing", 0) > 0.2:
        extra.append({"tool": "plot_missing_heatmap", "params": {}})
    corr = phase1_results.get("correlation_matrix", {})
    # nếu có cặp correlation > 0.9 → thêm heatmap
    return extra
```

**Chú ý:** Phase 1 tools cần `basic_stats` với tất cả cột số — truyền `cols=list(df.select_dtypes("number").columns)`.

---

### TASK 3.2 — Hypothesis Generation
**Từ:** IDEA-05 Hướng B
**Effort:** 3–4 giờ
**Dependency:** TASK 1.1 (DOMAIN_GENERIC) phải xong trước

**Làm gì:**

Tạo `agents/hypothesis_generator.py`:
```python
def generate_hypotheses(schemas, domain_context=""):
    if not domain_context or "Không có thông tin" in domain_context:
        return []  # Không sinh hypothesis nếu không có domain
    ...
```

Cập nhật `INSIGHT_USER` — thêm section kết luận hypothesis:
```
Nếu có hypotheses, kết luận từng cái:
H1: [XÁC NHẬN / BÁC BỎ / KHÔNG ĐỦ DỮ LIỆU] — {lý do + số liệu}
```

---

### TASK 3.3 — ydata-profiling hybrid
**Từ:** IDEA-01
**Effort:** 4–5 giờ
**Dependency:** TASK 1.2 (planner prompt) phải xong trước

**Làm gì:**

Tạo `tools/profiler.py`:
```python
from ydata_profiling import ProfileReport

TOP_CORR_THRESHOLD = 0.7
KEEP_STATS = {"mean", "std", "min", "max", "p_missing", "n_missing", "type"}

def run_profiling(df):
    profile = ProfileReport(df, minimal=True, progress_bar=False)
    desc = profile.description_set
    variables = {col: {k: v for k, v in stats.items() if k in KEEP_STATS}
                 for col, stats in desc["variables"].items()}
    alerts = [{"col": a.column_name, "type": str(a.alert_type)} for a in desc["alerts"]]
    top_corr = []
    pearson = desc.get("correlations", {}).get("pearson")
    if pearson is not None:
        for c1 in pearson.columns:
            for c2 in pearson.index:
                if c1 >= c2: continue
                val = pearson.loc[c2, c1]
                if abs(val) >= TOP_CORR_THRESHOLD:
                    top_corr.append({"col1": c1, "col2": c2, "r": round(val, 3)})
    return {"n_rows": desc["table"]["n"], "n_cols": desc["table"]["n_var"],
            "variables": variables, "alerts": alerts, "top_correlations": top_corr}
```

**Chú ý:** `minimal=True` bắt buộc — không có thì chạy rất chậm. Test với dataset nhỏ trước khi chạy với dữ liệu điện lực.

---

## DEFER — Không làm trước bảo vệ

```
IDEA-08 Phần 2  — Insight ranking + dedup (đụng AgentResult, rủi ro cao)
IDEA-09 Nhóm 2  — Preprocessing planner (effort cao, không critical)
IDEA-03 Hướng C — Cross-lag MI matrix (quá phức tạp so với gain)
IDEA-03 Hướng B — Granger Causality (nice-to-have, không bắt buộc)
```

---

## TASK BỔ SUNG — Eval Metrics (quan trọng cho bảo vệ)

**Không có trong IDEAS.md nhưng bắt buộc để có số liệu khi trình bày.**
**Effort:** 2–3 giờ
**File:** `tests/eval_metrics.py` (mới)

**Làm gì:**

```python
"""Script đo Planning Success Rate và Execution Pass Rate từ logs."""
import json, glob, os

def evaluate_logs(log_dir="outputs/logs"):
    results = []
    for f in glob.glob(f"{log_dir}/*.json"):
        data = json.load(open(f, encoding="utf-8"))
        if not isinstance(data, list) or len(data) < 2:
            continue
        steps = [s for s in data if isinstance(s, dict) and s.get("step")]
        total = len(steps)
        success = sum(1 for s in steps if s.get("decision", {}).get("status") == "success")
        errors = sum(1 for s in steps if s.get("decision", {}).get("error"))
        results.append({
            "run_id": os.path.basename(f),
            "total_steps": total,
            "success_steps": success,
            "error_steps": errors,
            "execution_pass_rate": round(success / total, 3) if total else 0,
        })

    if not results:
        return {}
    avg_pass_rate = sum(r["execution_pass_rate"] for r in results) / len(results)
    return {
        "n_runs": len(results),
        "avg_execution_pass_rate": round(avg_pass_rate, 3),
        "runs": results,
    }

if __name__ == "__main__":
    import json
    print(json.dumps(evaluate_logs(), indent=2, ensure_ascii=False))
```

**Con số cần có cho slide:**
- Execution Pass Rate trước/sau fix prompt (so sánh logs 11/6 vs 14/6)
- Số lần chạy thành công / tổng số lần chạy
- Số tool calls lỗi trung bình mỗi run

---

## PHẦN BỔ SUNG — Còn lại sau khi test thật từng flow (19/6)

> Nhóm 1/2/3 + Eval Metrics ở trên đã hoàn thành, đồng thời phát hiện và fix thêm nhiều bug
> nghiêm trọng không có trong kế hoạch gốc qua việc chạy thử thật từng flow trong Docker
> (không chỉ đọc code): IQR=0 phá hủy cột nhị phân, class imbalance khiến model chỉ đoán
> majority class, `seaborn xticklabels=None` crash toàn bộ Evaluation/Inference classification,
> `report_generator` không tương thích format chart dict mới, target bị scale làm RMSE/MAE
> vô nghĩa, `target_col` fallback cho Inference khi data mới không có cột target, datetime
> false-positive (`overtime_hours` chứa substring "time"), correlation attribution bug trong
> `_auto_score`, Preprocessing Planner (IDEA-09 Nhóm 2 — đã làm, không defer nữa), refinement
> loop (góp ý + chạy lại), data preview trước/sau xử lý, và clustering thiếu scaling +
> `NumericScaler` không ghi nhận `fill_values`. Bài học chung: **flow nào chưa test thật qua
> agent.run() thì coi như chưa biết có bug hay không**, dù code đọc qua có vẻ ổn.

### TASK BS.1 — Đo Execution Pass Rate / Tool Hit Rate cụ thể
**Effort:** 2–3 giờ — **Ưu tiên: Cao**

Mở rộng `tests/eval_metrics.py` (đã có khung) để:
- Gom `outputs/logs/*.json` qua nhiều dataset khác nhau (điện lực, retail_sales, hr_employees)
- Đếm tần suất `status=skipped, reason=tool không tồn tại` theo tên tool — đây là gap signal
  trực tiếp cho biết tool nào LLM hay cố gọi mà chưa có
- Tính Tool Hit Rate = bước thực thi thành công / tổng bước LLM yêu cầu
- Xuất số liệu cụ thể để đưa vào slide (ROADMAP.md Tuần 3 yêu cầu, hiện chưa có số nào)

### TASK BS.2 — Retest multi-file merge flow
**Effort:** 1 giờ — **Ưu tiên: Trung bình**

`file_detector.py`/`file_merger.py`/`schema_analyzer.py` chưa được chạy lại từ đầu session
sau toàn bộ thay đổi EDA (Phase 1/2, trigger rules, datetime guard mới). Cần test:
- Upload 2+ file có cột chung (vd dataset điện lực gốc: phu_tai + thoi_tiet)
- Xác nhận merge plan đề xuất đúng, `detect_datetime_columns` fix (loại trừ cột số) không
  làm hỏng việc detect cột thời gian thật dùng để join

### TASK BS.3 — Kiểm tra report Full Pipeline với ml_results
**Effort:** 30 phút — **Ưu tiên: Trung bình**

Mới verify `report_generator.generate()` với `eda_results` (EDA-only). Chưa xác nhận report
khi `ml_results` có dữ liệu thật (Full Pipeline chạy hết training+evaluation) — đặc biệt
`report_prompt.py` xử lý `ml_results` lồng cả `leaderboard` + `evaluation_metrics` có đúng
format LLM đọc được không, và chart từ nhiều agent (EDA dict-format + ML string-format) gộp
vào 1 report có lỗi gì không khi số lượng chart lớn.

### TASK BS.4 — UI polish
**Effort:** 1–2 giờ — **Ưu tiên: Thấp**

- Rà soát tiếng Việt đồng nhất giữa các màn hình (vài chỗ còn lai thuật ngữ Anh)
- Loading state rõ ràng hơn cho các bước tốn thời gian (Full Pipeline, ydata-profiling)
- Polish lại nút/label sau khi thêm nhiều UI mới (confirm screen, refinement box, data preview)

### Defer xác nhận lại (không đổi so với quyết định gốc)
```
IDEA-08 Phần 2  — Insight ranking + dedup (đụng AgentResult, rủi ro cao)
IDEA-03 Hướng C — Cross-lag MI matrix (quá phức tạp so với gain)
IDEA-03 Hướng B — Granger Causality (khó diễn giải tiếng Việt tự nhiên cho no-code)
IDEA-11 Hướng B — Batch LLM caption (template hiện tại đã đủ dùng)
```
**Lưu ý:** IDEA-09 Nhóm 2 (Preprocessing Planner) đã được làm — KHÔNG còn defer như ghi ở
mục DEFER phía trên (mục đó đã lỗi thời, giữ lại để biết lịch sử quyết định).

---

## Checklist tổng kết

### Nhóm 1 (bắt buộc)
- [ ] TASK 1.1 — DOMAIN_GENERIC thay hardcode điện lực
- [ ] TASK 1.2 — PLANNER_PROMPT: few-shot + whitelist cột + negative instruction
- [ ] TASK 1.3 — INSIGHT_PROMPT: số liệu cụ thể + length constraint
- [ ] TASK 1.4 — ML_PROMPT: whitelist model + guard ml_results rỗng
- [ ] TASK 1.5 — user_query cho Evaluation + Inference + Training
- [ ] TASK 1.6 — Per-chart caption (template)
- [ ] TASK 1.7 — Input summary + clarification
- [ ] TASK 1.8 — skewness_kurtosis vào TOOL_REGISTRY

### Nhóm 2 (nên có)
- [ ] TASK 2.1 — Scatter, violin, Spearman tools
- [ ] TASK 2.2 — Mutual Information scoring
- [ ] TASK 2.3 — Self-Generating Questions
- [ ] TASK 2.4 — Statistical Scoring (p-value)

### Nhóm 3 (nếu còn thời gian)
- [ ] TASK 3.1 — Adaptive Replanning
- [ ] TASK 3.2 — Hypothesis Generation
- [ ] TASK 3.3 — ydata-profiling hybrid

### Bổ sung
- [ ] Eval Metrics script
- [ ] Test end-to-end ≥3 lần không crash
- [ ] UI polish (loading state, tiếng Việt đồng nhất)
- [ ] Slide kiến trúc + demo script
