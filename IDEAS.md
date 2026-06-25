# Ý tưởng cải tiến — chưa implement

> File này tổng hợp các hướng cải tiến đang cân nhắc. Mỗi ý tưởng ghi rõ động lực, thiết kế đề xuất, và đánh giá sơ bộ. Khi đã đủ ý tưởng và quyết định thực thi, chuyển sang plan cụ thể trước khi code.

---

## TỔNG HỢP — 11 Ideas

### Bảng tổng quan

| # | Idea | Layer | EDA? | Effort | Gain | Dependency |
|---|---|---|---|---|---|---|
| 01 | ydata-profiling hybrid | Execution | ✅ | Trung bình | Cao | IDEA-04 trước |
| 02 | Uni/Bi/Multivariate tools | Tool depth | ✅ | Thấp | Cao | Độc lập |
| 03 | Feature Relationship (MI, Granger) | Tool depth | ✅ | Thấp→Cao | Cao | Độc lập |
| 04 | Prompt optimization | Planning | ✅ | Thấp | Cao nhất | Độc lập |
| 05 | Hypothesis + Self-Q | Pre-planning | ✅ | Trung bình | Cao nhất | IDEA-04 trước |
| 06 | Input summary + confirm | UX | Gián tiếp | Rất thấp | Trung bình | Độc lập |
| 07 | Communicative Dehallucination | UX | Gián tiếp | Thấp | Trung bình | Gộp IDEA-06 |
| 08 | Insight Ranking + Scoring | Output | ✅ | Thấp→Cao | Trung bình | P2: sau IDEA-05 |
| 09 | user_query đồng nhất | Input | Gián tiếp | Rất thấp | Cao | Độc lập |
| 10 | Adaptive Replanning | Planning | ✅ | Trung bình | Cao | IDEA-04 trước |
| 11 | Per-chart Caption | Output/UX | ✅ | Rất thấp | Trung bình | Độc lập |

---

### Coverage theo layer EDA

```
Input handling    → IDEA-06, 07, 09
Pre-planning      → IDEA-05 (Hypothesis/Self-Q)
Planning          → IDEA-04 (prompt fix), IDEA-10 (adaptive)
Execution         → IDEA-01 (ydata hybrid)
Tool depth        → IDEA-02 (Uni/Bi/Multi), IDEA-03 (MI/Granger)
Output/Insight    → IDEA-08 (ranking), IDEA-11 (caption)
```

Toàn bộ 6 layer đều được cover — không có blind spot.

---

### Thứ tự thực thi đề xuất

**Nhóm 1 — Làm ngay (độc lập, effort thấp, gain cao):**
```
IDEA-04   Prompt optimization          → fix bug param mismatch ngay
IDEA-09   user_query Nhóm 1            → 3 agent dùng được query, 10 phút
IDEA-06   Input summary                → UX confirm trước khi chạy
IDEA-07   Communicative Dehallucination → gộp với IDEA-06
IDEA-11   Per-chart caption Hướng A    → template caption, 30 phút
IDEA-02   skewness_kurtosis register   → 1 dòng quick win
```

**Nhóm 2 — Core EDA (sau Nhóm 1 xong):**
```
IDEA-02   Scatter/Violin/Spearman      → hoàn thiện Uni/Bi/Multi tools
IDEA-03   Mutual Information Hướng A   → feature relationship discovery
IDEA-05   Self-Generating Questions    → EDA có mục đích rõ ràng
IDEA-08   Statistical Scoring Phần 1  → p-value cho từng insight
```

**Nhóm 3 — Depth + Polish (nếu còn thời gian):**
```
IDEA-01   ydata-profiling hybrid       → coverage tự động
IDEA-10   Adaptive Replanning          → 2-phase planning
IDEA-05   Hypothesis Generation        → sau DOMAIN_GENERIC ổn
IDEA-03   Granger Causality Hướng B    → domain time-series
IDEA-11   Batch LLM caption Hướng B    → caption giàu ngữ nghĩa
```

**Defer / làm cuối:**
```
IDEA-08   Insight Ranking Phần 2       → đụng AgentResult, sau IDEA-05
IDEA-09   Preprocessing Planner        → effort cao nhất trong IDEA-09
IDEA-03   Cross-lag MI Hướng C         → phức tạp, deadline dependent
```

---

## IDEA-01 — Hybrid EDA: ydata-profiling + LLM time-series

**Trạng thái:** Đang thu thập ý kiến

**Động lực:**
- Flow hiện tại LLM phải plan cả quality check lẫn time series → dễ sinh sai param (đã thấy bug `unexpected keyword argument` trong logs 11/6)
- `_normalize_params` là patch tạm, không giải quyết gốc rễ
- `insight_generator` chỉ nhận kết quả từ tool LLM chọn → nếu LLM bỏ sót `basic_stats` thì insight thiếu context

**Điểm mạnh ydata-profiling:**
- Coverage tự động toàn bộ cột, không bỏ sót
- Alerts system: high correlation, high cardinality, skewed, constant column, many zeros
- Correlation đa dạng: Pearson, Spearman, Kendall, Cramér's V (categorical)
- Deterministic — không phụ thuộc LLM, không bao giờ crash do param sai

**Điểm yếu ydata-profiling:**
- Chậm: dataset 100k rows mất 30–60s
- Output JSON rất lớn (500KB–2MB) → không nhét thẳng vào LLM prompt được
- Time series yếu: không có decomposition, hourly/weekly pattern, lag correlation
- Không biết user hỏi gì → không targeted

**Thiết kế đề xuất:**

```
df (sau merge)
    │
    ├── [LAYER 1] ProfileReport(minimal=True)     ← tự động, không cần LLM
    │   → extract_profiling_summary()              ← filter xuống ~5KB
    │     (alerts, per-col stats, top correlations)
    │
    ├── [LAYER 2] eda_planner.plan(               ← LLM chỉ plan time-series
    │       user_query,
    │       profiling_summary,
    │       domain_context
    │   )
    │
    ├── [LAYER 3] execute_plan(plan, df)           ← không đổi
    │
    └── [LAYER 4] insight_generator.generate(
            profiling_summary + ts_results         ← context đầy đủ hơn
        )
```

**Thay đổi code cần làm:**
1. Tạo `tools/profiler.py` — `run_profiling(df) -> dict` (filtered summary ~5KB)
2. Sửa `eda_agent.py` — thêm profiling layer, bỏ quality tools khỏi `TOOL_REGISTRY`
3. Sửa `planner_prompt.py` — giới hạn LLM chỉ plan time-series tools
4. Sửa `insight_generator` — nhận `profiling_summary` làm context bổ sung

**Đánh giá sơ bộ:**
- Gain rõ: giảm rủi ro param mismatch, insight context đầy đủ hơn
- Rủi ro: thêm 5–15s chạy profiling, cần viết filter layer cẩn thận
- Nên làm sau khi đã có đủ ý tưởng khác để tránh sửa đi sửa lại

---

## IDEA-02 — Hoàn thiện phân tích Univariate + Bivariate + Multivariate

**Trạng thái:** Đang thu thập ý kiến

**Động lực:**
- EDA hiện tại không có cấu trúc 3 tầng rõ ràng — LLM plan tùy tiện, dễ bỏ sót cả tầng
- `skewness_kurtosis` đã implement trong `stats_engine.py:34` nhưng thiếu trong `TOOL_REGISTRY` → LLM không gọi được (quick win)
- Chỉ có Pearson correlation → bị ảnh hưởng bởi outlier, không bắt được quan hệ non-linear
- Không có scatter plot, violin plot, boxplot by group → thiếu công cụ bivariate visual cơ bản

**Thực trạng từng tier:**

| Tier | Đã có | Thiếu |
|---|---|---|
| Univariate | basic_stats, plot_distribution, plot_boxplot | skewness_kurtosis (code xong, chưa register), violin plot, normality test |
| Bivariate | correlation_matrix (Pearson), plot_heatmap, lag_correlation | Scatter plot, Spearman/Kendall, boxplot by group |
| Multivariate | plot_heatmap | Pairplot, PCA loadings, feature clustering |

**Thay đổi cụ thể đề xuất:**

*Quick win (không cần code thêm):*
- Thêm `skewness_kurtosis` vào `TOOL_REGISTRY` trong `eda_agent.py` — 1 dòng

*Thêm vào `stats_engine.py`:*
- `spearman_correlation(df, cols)` — thêm `method` param vào `correlation_matrix` hoặc hàm riêng
- `normality_test(df, col)` — Shapiro-Wilk (n<5000) hoặc KS test

*Thêm vào `viz_engine.py`:*
- `plot_scatter(df, col1, col2)` — scatter + regression line (seaborn `regplot`)
- `plot_violin(df, col)` — violin thay boxplot khi cần thấy shape phân phối
- `plot_boxplot_by(df, col, by)` — boxplot nhóm theo cột categorical (vd: load theo ngày lễ/thường)
- `plot_pairplot(df, cols)` — scatter matrix top N cột

**Đánh giá sơ bộ:**
- Effort thấp, gain rõ — hầu hết là thêm hàm mới, không sửa logic cũ
- `skewness_kurtosis` là quick win nhất, làm được ngay
- Nên kết hợp với IDEA-03 (Mutual Information) vì cùng tầng "phân tích quan hệ feature"

---

## IDEA-03 — Feature Relationship Discovery

**Trạng thái:** Đang thu thập ý kiến

**Động lực:**
- Pearson correlation bỏ sót quan hệ non-linear — ví dụ nhiệt độ vs phụ tải có dạng U (cả nóng lẫn lạnh đều tăng load), Pearson gần 0 trong khi thực tế quan hệ rất mạnh
- `lag_correlation` hiện tại chỉ chạy được 2 cột, không có cái nhìn tổng thể "feature nào quan trọng nhất với target ở lag bao nhiêu"
- Thiếu hẳn công cụ để trả lời câu hỏi "feature nào drive target?" trước khi train model

**Ba hướng theo độ phức tạp:**

### Hướng A — Mutual Information scoring (khuyến nghị làm trước)

- Bắt được quan hệ non-linear, không giả định phân phối
- 5 dòng sklearn (`mutual_info_regression` / `mutual_info_classif`)
- Output: ranking feature theo MI score với target → biết ngay feature nào quan trọng nhất
- Visual: bar chart MI score, dễ giải thích cho người không chuyên

```python
# tools/relationship.py
from sklearn.feature_selection import mutual_info_regression

def mutual_info_scores(df, target_col):
    X = df.drop(columns=[target_col]).select_dtypes(include="number").dropna()
    y = df[target_col].loc[X.index]
    scores = mutual_info_regression(X, y, random_state=42)
    return dict(zip(X.columns, scores))  # {feature: mi_score}
```

### Hướng B — Granger Causality (domain-specific cho time series)

- Kiểm định: "nhiệt độ có *gây ra* thay đổi phụ tải không?" — khác với chỉ tương quan
- `statsmodels.tsa.stattools.grangercausalitytests` có sẵn
- Output: p-value cho từng feature → feature nào có Granger causality với target
- Phù hợp đặc biệt với dataset điện lực, gây ấn tượng về mặt domain knowledge

### Hướng C — Cross-lag MI matrix (kết hợp A + lag)

- Chạy MI giữa target và mỗi feature tại nhiều lag: 0h, 1h, 6h, 24h, 168h (1 tuần)
- Tìm: "feature X tại lag Y có MI cao nhất với target"
- Ứng dụng: biết thông tin nào đến sớm nhất → dùng làm lagged feature cho forecasting model
- Phức tạp hơn nhưng output có giá trị nhất cho bài toán dự báo phụ tải

**Thay đổi code cần làm:**
1. Tạo `tools/relationship.py` — `mutual_info_scores()`, `granger_causality()`, `cross_lag_mi()`
2. Thêm các hàm mới vào `TOOL_REGISTRY` trong `eda_agent.py`
3. Thêm `plot_mi_scores()` vào `viz_engine.py` — bar chart MI
4. Cập nhật `planner_prompt.py` — thêm chữ ký hàm mới vào bảng tool

**Đánh giá sơ bộ:**
- Hướng A: effort thấp, gain cao, làm trước
- Hướng B: effort trung bình, domain value cao, làm sau A
- Hướng C: effort cao, làm cuối hoặc bỏ nếu thiếu thời gian
- Nên kết hợp với IDEA-01 (hybrid profiling): profiling cover Pearson/Spearman, relationship.py cover MI/Granger → không trùng lặp

---

## IDEA-04 — Tối ưu Prompt

**Trạng thái:** Đang thu thập ý kiến

**Động lực:**
- Prompt là nơi dễ cải thiện nhất, không cần đổi kiến trúc hay thêm tool
- `planner_prompt` là nguyên nhân gốc của class bug param mismatch (logs 11/6) — fix prompt giảm lỗi ngay
- Các prompt hiện tại quá generic, không ràng buộc output format đủ chặt

---

### 4.1 — PLANNER_PROMPT (ưu tiên cao nhất)

**Vấn đề:**
- SYSTEM không có JSON schema → LLM đôi khi thêm text bên ngoài JSON
- USER không ràng buộc tên cột → LLM tự đặt tên cột không tồn tại trong df
- Không có few-shot → LLM hay sinh sai tên param (`column` thay vì `col`, `dataset` thay vì không có param)
- Không có constraint số bước → đôi khi sinh 15+ bước, đôi khi 2 bước

**Cải tiến đề xuất:**

1. **Few-shot example** trong USER — ví dụ 1 plan hợp lệ:
```
Ví dụ output đúng:
{"steps": [
  {"tool": "check_missing", "params": {}},
  {"tool": "basic_stats", "params": {"cols": ["col_a", "col_b"]}},
  {"tool": "plot_time_series", "params": {"col": "col_a"}}
], "explanation": "..."}
```

2. **Whitelist tên cột** — truyền `list(df.columns)` vào prompt:
```
Các cột có trong dataset (chỉ dùng đúng tên này):
{available_columns}
```
→ Cần sửa `eda_planner.plan()` để nhận thêm `available_columns` param, `eda_agent.py` truyền `list(self.df.columns)`

3. **Ràng buộc số bước và thứ tự**:
```
Quy tắc:
- 4–8 bước, không nhiều hơn
- Bắt đầu bằng check_missing hoặc check_duplicates
- Nếu df có DatetimeIndex: phải có ít nhất 1 bước time series (hourly/weekly/monthly_pattern hoặc time_series_decompose)
- Kết thúc bằng ít nhất 1 visualization
```

4. **Negative instruction**:
```
KHÔNG được:
- Dùng tên param khác ngoài danh sách (không dùng "column", "dataset", "data", "dataframe")
- Gọi tool không có trong danh sách
- Thêm text, markdown, hoặc giải thích bên ngoài JSON
```

---

### 4.2 — INSIGHT_PROMPT

**Vấn đề:**
- SYSTEM role quá generic: "chuyên gia phân tích dữ liệu" không gắn với domain nào
- Không yêu cầu số liệu cụ thể → LLM viết insight chung chung kiểu "dữ liệu có giá trị cao vào buổi tối"
- Không có length constraint → output dài ngắn không nhất quán
- **Hiện tại `DOMAIN_ELECTRICITY` được hardcode làm default** trong `insight_generator.py:40` → nếu user upload dataset tài chính, logistics, y tế thì insight bị sai hoàn toàn

**Cải tiến đề xuất:**

1. **Bỏ hardcode DOMAIN_ELECTRICITY** — thay bằng `DOMAIN_GENERIC` dùng được cho mọi dataset:
```python
# insight_generator.py — hiện tại (SAI)
domain_context or DOMAIN_ELECTRICITY  # ← fallback cứng về điện lực

# Nên đổi thành:
domain_context or DOMAIN_GENERIC
```

Luồng domain_context sau khi sửa:
```
user upload file nghiệp vụ  →  domain_context = nội dung file đó
user không upload           →  domain_context = DOMAIN_GENERIC
user chọn template điện lực →  domain_context = DOMAIN_ELECTRICITY  (giữ nguyên)
```

`DOMAIN_GENERIC` mô tả **cách tiếp cận phân tích** thay vì **nội dung domain** — dùng được cho bất kỳ dataset nào:
```python
DOMAIN_GENERIC = """
Không có thông tin domain cụ thể. Hãy phân tích theo nguyên tắc chung:
- Diễn giải tên cột theo nghĩa đen (vd: cột "revenue" → doanh thu, "temperature" → nhiệt độ)
- Tập trung vào pattern thống kê: phân phối, tương quan, bất thường, xu hướng
- Khi đề xuất hành động, dùng ngôn ngữ trung lập ("cột này", "giá trị này")
  thay vì giả định nghiệp vụ
- Nếu phát hiện pattern rõ (seasonality, outlier, high correlation), mô tả pattern đó,
  không giải thích nguyên nhân nghiệp vụ
"""
```

**Thay đổi code:** thêm `DOMAIN_GENERIC` vào `insight_prompt.py`, sửa 1 dòng trong `insight_generator.py:39`.

2. **SYSTEM không embed domain** — giữ generic, domain đến từ `{domain_context}` trong USER:
```
Bạn là chuyên gia phân tích dữ liệu. Khi có thông tin domain từ user,
ưu tiên diễn giải theo góc nhìn domain đó. Khi không có, diễn giải theo
ngữ nghĩa thống kê thuần túy.
```

3. **Yêu cầu số liệu cụ thể** — không cho phép insight chung chung:
```
Mỗi insight phải kèm con số cụ thể từ kết quả phân tích.
Không viết nhận xét định tính mà không có số liệu dẫn chứng.
```

4. **Length constraint**: 250–400 từ, mỗi section 1–3 câu.

5. **Chain-of-thought cho section "Insight chính"**:
```
Với mỗi insight: (1) quan sát → (2) nguyên nhân có thể → (3) gợi ý hành động
```

---

### 4.3 — ML_PROMPT / TASK_DETECTION

**Vấn đề:**
- `suggested_models` không ràng buộc → LLM đề xuất "LightGBM", "GradientBoosting" không có trong `model_selector.py`
- Không có few-shot → JSON output đôi khi thiếu field

**Cải tiến đề xuất:**

1. **Whitelist model names** trong prompt — liệt kê đúng tên có trong codebase:
```
Model có sẵn:
- regression: LinearRegression, Ridge, RandomForestRegressor, XGBRegressor
- classification: LogisticRegression, RandomForestClassifier, XGBClassifier
- clustering: KMeans
Chỉ chọn từ danh sách trên.
```

2. **Few-shot example** — 1 ví dụ JSON hợp lệ.

---

### 4.4 — REPORT_PROMPT

**Vấn đề nhỏ:**
- Không xử lý case `ml_results` rỗng → LLM đôi khi bịa kết quả ML
- `execution_log` có thể dài → cần truncate hoặc chỉ truyền summary

**Cải tiến đề xuất:**
```
Nếu ml_results là null hoặc rỗng: bỏ qua section 4, không tự suy đoán kết quả ML.
```

---

**Thứ tự thực thi:**
1. Thêm `DOMAIN_GENERIC` vào `insight_prompt.py` + sửa fallback trong `insight_generator.py` — 1 dòng, fix được generalization ngay
2. Thêm few-shot + whitelist cột vào `PLANNER_USER` — giải quyết class bug param mismatch
3. Thêm negative instruction vào `PLANNER_USER`
4. Thêm số liệu constraint vào `INSIGHT_USER`
5. Whitelist model names vào `TASK_DETECTION_USER`

**Đánh giá sơ bộ:**
- Tất cả thay đổi đều ở file prompt, không đụng logic agent hay tool
- Fix `DOMAIN_ELECTRICITY` là bắt buộc trước khi test với dataset ngoài điện lực
- Few-shot + whitelist cột là cặp hiệu quả nhất, nên làm cùng lúc

---

## IDEA-05 — Hypothesis Generation + Self-Generating Questions

**Trạng thái:** Đang thu thập ý kiến

**Động lực:**
- Flow hiện tại `eda_planner` nhận `user_query` nhưng nếu user chỉ nhập "phân tích dữ liệu này" thì LLM không có gì để bám vào → plan generic, tool calls trùng lặp hoặc không đúng trọng tâm
- EDA hiện tại chạy tool rồi sinh insight, nhưng không có **reasoning trước khi chạy** → output trông như "chạy hết tool rồi tổng hợp" thay vì "phân tích có mục đích"
- Mentor nhìn vào sẽ thấy rõ hơn nếu hệ thống biết **tại sao** chạy từng bước

---

### Hướng A — Self-Generating Questions (làm trước)

**Cơ chế:** LLM nhìn schema + user_query → tự sinh câu hỏi phân tích → plan trả lời từng câu hỏi.

```
Schema: {columns, dtypes, sample}
User query: "phân tích dữ liệu này"

→ LLM sinh:
  Q1: Phân phối của các cột số như thế nào?
  Q2: Cột nào có missing value đáng kể?
  Q3: Các cột số có tương quan với nhau không?
  Q4: Có pattern theo thời gian không? (nếu có datetime)

→ eda_planner nhận questions làm context
→ plan có tool calls trả lời từng Q
→ insight_generator format theo Q: "Q1: ..." / "Q2: ..."
```

**Ưu điểm:**
- Hoạt động tốt kể cả không có domain_context
- Phù hợp khi user không biết hỏi gì (user query rỗng hoặc quá chung)
- Không refactor nhiều — chèn thêm 1 bước trước `eda_planner.plan()`

**Thay đổi code:**
1. Thêm `agents/question_generator.py` — `generate_questions(schemas, user_query, domain_context) -> list[str]`
2. Sửa `eda_agent.run()` — gọi `question_generator` trước `eda_plan()`
3. Truyền `questions` vào `eda_planner.plan()` và cập nhật `PLANNER_USER` để nhận thêm field này
4. Cập nhật `INSIGHT_USER` — format output theo từng câu hỏi

---

### Hướng B — Hypothesis Generation (làm sau)

**Cơ chế:** LLM nhìn schema + domain_context → tự đặt giả thuyết có thể kiểm định → EDA plan thiết kế để CONFIRM / REJECT từng giả thuyết.

```
Schema + domain_context (điện lực)

→ LLM sinh:
  H1: Phụ tải có seasonality theo giờ trong ngày
  H2: Nhiệt độ tương quan dương với phụ tải vào mùa hè
  H3: Ngày lễ có phụ tải thấp hơn ngày thường

→ eda_planner plan tool calls để test từng H
→ insight_generator kết luận:
  "H1: XÁC NHẬN — hourly_pattern cho thấy đỉnh 19-21h cao hơn 35%"
  "H2: XÁC NHẬN — lag_correlation(temperature, load, lag=2) = 0.71"
  "H3: KHÔNG ĐỦ DỮ LIỆU — chưa có cột ngày lễ sau merge"
```

**Ưu điểm:**
- Output có cấu trúc khoa học, dễ viết báo cáo
- Mentor thấy rõ reasoning của hệ thống
- Kết hợp tốt với Granger causality (IDEA-03 Hướng B) — hypothesis "A gây ra B" → test bằng Granger

**Nhược điểm:**
- Phụ thuộc `domain_context` — hypothesis yếu nếu dùng `DOMAIN_GENERIC`
- Cần thêm field `hypothesis_results` vào `AgentResult` và `report_generator`

**Thay đổi code:**
1. Thêm `agents/hypothesis_generator.py` — `generate_hypotheses(schemas, domain_context) -> list[str]`
2. Sửa `eda_agent.run()` — gọi sau `question_generator` (nếu có domain) hoặc bỏ qua (nếu DOMAIN_GENERIC)
3. Cập nhật `PLANNER_USER` nhận thêm `hypotheses`
4. Cập nhật `INSIGHT_USER` — format kết luận per hypothesis: XÁC NHẬN / BÁC BỎ / KHÔNG ĐỦ DỮ LIỆU
5. Thêm section "Kiểm định giả thuyết" vào `report_prompt.py`

---

### Hybrid flow đề xuất

```
eda_agent.run()
    │
    ├── [Luôn chạy] question_generator.generate()   → 3–5 câu hỏi từ schema
    │
    ├── [Chỉ khi có domain] hypothesis_generator.generate() → 2–3 giả thuyết
    │
    ▼
eda_planner.plan(user_query, schemas, questions, hypotheses)
    → plan 2 nhóm:
       - Nhóm trả lời questions (coverage rộng)
       - Nhóm kiểm định hypotheses (depth có mục tiêu)
    │
    ▼
execute_plan()  ← không đổi
    │
    ▼
insight_generator.generate(results, questions, hypotheses)
    → Section "Trả lời câu hỏi": Q1... Q2... Q3...
    → Section "Kết quả kiểm định": H1: XÁC NHẬN / H2: BÁC BỎ...
```

**Thứ tự thực thi:**
1. Hướng A (Self-Generating Questions) — không phụ thuộc domain, effort thấp, làm trước
2. Hướng B (Hypothesis Generation) — làm sau khi `DOMAIN_GENERIC` đã ổn định (xem IDEA-04)
3. Hybrid — kết hợp khi cả A và B đã chạy ổn định

**Dependency:**
- IDEA-04 (prompt optimization) nên làm trước — đặc biệt phần `DOMAIN_GENERIC` và whitelist tên cột
- IDEA-03 Hướng B (Granger causality) có thể dùng để test hypothesis "A gây ra B"

**Đánh giá sơ bộ:**
- Đây là tính năng "ăn tiền" nhất về mặt demo — hệ thống trông thông minh có chủ đích thay vì chỉ chạy tool
- Self-Generating Questions giải quyết pain point lớn nhất: user không biết hỏi gì
- Hypothesis Generation làm báo cáo có chiều sâu hơn hẳn
- Cả 2 chỉ thêm 1 LLM call mỗi cái — latency tăng nhưng chấp nhận được

---

## IDEA-06 — Input Summarization + User Confirm trước khi chạy

**Trạng thái:** Đang thu thập ý kiến

**Động lực:**
- Hiện tại user bấm "Bắt đầu" → agent chạy luôn, không có bước xác nhận
- Nếu user nhập query mơ hồ, chọn sai cột target, hoặc upload nhầm file → tốn LLM call, kết quả lệch, phải chạy lại từ đầu
- User không biết hệ thống hiểu yêu cầu của mình như thế nào cho đến khi có kết quả

**Thiết kế đề xuất:**

Thêm bước giữa `experiment_config.py` (user nhập) và `run_experiment.py` (agent chạy):

```
User bấm "Bắt đầu" (experiment_config.py)
    │
    ▼ [MỚI] Hệ thống tóm tắt lại những gì sẽ làm
    │
    │  "Tôi hiểu bạn muốn:
    │   - Phân tích file: phu_tai.csv, thoi_tiet.csv (2 file, sẽ merge theo cột thời gian)
    │   - Yêu cầu: phân tích xu hướng phụ tải và ảnh hưởng của nhiệt độ
    │   - Loại experiment: Khám phá dữ liệu
    │   - Domain: hệ thống điện Việt Nam (từ file nghiệp vụ)"
    │
    ├── [Xác nhận] → agent chạy
    └── [Chỉnh lại] → quay về experiment_config.py
```

**Nội dung summary nên bao gồm:**
- Tên file đã upload + số dòng/cột
- Nếu nhiều file: đề xuất merge hay phân tích riêng
- Diễn giải lại `user_query` bằng ngôn ngữ tự nhiên (LLM paraphrase)
- Loại experiment và cấu hình chính (target_col, task_type nếu có)
- Domain context: từ file user upload hay dùng DOMAIN_GENERIC

**2 cách implement:**

*Cách 1 — Không dùng LLM (nhanh, deterministic):*
- Tóm tắt bằng template cứng từ `ExperimentContext`
- Không tốn LLM call, không thêm latency
- Nhược: không paraphrase được query của user

*Cách 2 — Dùng LLM (chậm hơn ~1s, tự nhiên hơn):*
- LLM diễn giải lại user_query + context thành đoạn tóm tắt
- Tốn thêm 1 LLM call nhỏ (MODEL_8B, prompt ngắn)
- Ưu: user thấy ngay hệ thống có hiểu đúng không trước khi chạy

**Khuyến nghị:** Cách 1 trước — template cứng đủ dùng, không thêm latency, implement nhanh. Cách 2 làm sau nếu cần polish.

**Thay đổi code cần làm:**
1. Thêm `_render_input_summary(context)` trong `run_experiment.py` — hiển thị tóm tắt dạng `st.info()`
2. Thêm 2 nút: "Xác nhận & Chạy" và "Chỉnh lại" thay cho tự động chạy
3. Chỉ gọi `_run_agent(context)` sau khi user bấm "Xác nhận & Chạy"

**Đánh giá sơ bộ:**
- Effort rất thấp (chỉ sửa `run_experiment.py`, không đụng agent/tool/prompt)
- Tránh được class lỗi "chạy xong mới biết input sai"
- UX tốt hơn rõ rệt, phù hợp với human-in-the-loop đã ghi trong FLOW.md
- Nên làm sớm vì không có dependency với idea nào khác

---

## IDEA-07 — Communicative Dehallucination (Hỏi ngược khi input mơ hồ)

**Trạng thái:** Đang thu thập ý kiến

**Động lực:**
- Planner hiện tại nhận user_query mơ hồ ("phân tích dữ liệu", "xem thử") → tự đoán tham số → plan sai nghiệp vụ
- Bài báo ChatDev đề xuất "Communicative Dehallucination": khi input thiếu thông số, agent không tự biên mà hỏi ngược user trước khi lập kế hoạch
- Chat infrastructure đã có sẵn (`chat_box.py`: `render_input`, `render_history`)

**Tối ưu so với bản gốc:**
Không hỏi ngược mặc định — chỉ trigger khi detect được ambiguity:
```
user_query < 15 ký tự
HOẶC user_query chỉ có từ generic ("phân tích", "xem", "check", "thử")
HOẶC user_query rỗng
    → hỏi tối đa 2 câu làm rõ, không hỏi thêm
Còn lại → chạy thẳng, không hỏi
```

**Thiết kế đề xuất:**
```
run_experiment.py
    │
    ├── [MỚI] detect_ambiguity(user_query) → True/False
    │
    ├── Nếu True: hiện clarification questions (tối đa 2)
    │   "Bạn muốn tập trung vào cột nào?"
    │   "Bạn muốn phân tích theo thời gian hay theo phân phối?"
    │   → user trả lời → append vào user_query → tiếp tục
    │
    └── Nếu False: chạy thẳng
```

Gộp với IDEA-06 (Input Summarization): summary + clarification questions hiện ra cùng lúc trong 1 bước confirm trước khi chạy.

**Thay đổi code cần làm:**
1. Thêm `_detect_ambiguity(user_query) -> bool` trong `run_experiment.py` — rule-based, không dùng LLM
2. Thêm `_render_clarification(context)` — hiện tối đa 2 câu hỏi dạng `st.text_input`
3. Thêm session state `clarification_done` để không hỏi lại sau khi user đã trả lời
4. Append câu trả lời vào `context.user_query` trước khi truyền cho planner

**Đánh giá sơ bộ:**
- Effort thấp, không đụng agent/tool/prompt
- Gộp được với IDEA-06 → 1 bước confirm làm cả 2 việc
- Nên làm cùng lúc với IDEA-06

---

## IDEA-08 — Insight Ranking + Statistical Scoring

**Trạng thái:** Đang thu thập ý kiến

**Động lực:**
- Sau khi chạy 15–20 tool calls, insight_generator nhận quá nhiều data → LLM sinh insight dài, generic, không ưu tiên điều quan trọng nhất
- Khi IDEA-05 (Self-Generating Questions) chạy, số lượng insight tăng thêm → vấn đề càng rõ
- InsightPilot và QUIS giải quyết bằng thống kê thay vì LLM → không tốn thêm token

**Tách làm 2 phần độc lập:**

### Phần 1 — Statistical Scoring ở tầng tool (làm ngay, không dependency)

Gắn score thống kê vào kết quả tool trước khi truyền cho LLM:

| Loại insight | Test thống kê | Thư viện |
|---|---|---|
| Xu hướng (trend) | Mann-Kendall | `scipy.stats` (có sẵn qua statsmodels) |
| Khác biệt phân phối | Kruskal-Wallis | `scipy.stats` |
| Tương quan | Pearson p-value | `scipy.stats` |
| Outlier | IQR score | đã có trong quality_checker |

Output: mỗi kết quả tool thêm field `{"stat_score": 0.95, "p_value": 0.001, "significant": true}`

LLM nhận được context "insight này significant (p=0.001)" → ưu tiên diễn giải đúng chỗ, không cần rank thủ công.

**Thay đổi code:**
1. Thêm `tools/scorer.py` — `score_trend(series)`, `score_distribution_diff(df, col, by)`, `score_correlation(r, n)`
2. Sửa `eda_agent.execute_plan()` — sau mỗi tool call, nếu là stats tool thì gắn score vào result
3. Cập nhật `INSIGHT_USER` — thêm hướng dẫn ưu tiên insight có `significant=true`

### Phần 2 — Insight Ranking + Dedup (làm sau IDEA-05)

**Dependency:** IDEA-05 phải chạy trước — chỉ có ý nghĩa khi có nhiều insights cần rank.

**Vấn đề kiến trúc:** `AgentResult.insights` hiện là **1 string** → phải đổi thành `list[dict]`:
```python
# Hiện tại
insights: str = ""

# Sau khi sửa
insights: list[dict] = field(default_factory=list)
# [{"text": "...", "score": 0.9, "type": "trend", "cols": ["col_a"]}]
```
→ Ảnh hưởng: `insight_generator.py`, `AgentResult`, `run_experiment.py`, `report_generator.py`, `pipeline_agent.py`

**Dedup:** Dùng `sklearn TfidfVectorizer + cosine_similarity` (sklearn đã có) thay vì sentence-transformers (quá nặng) — đủ dùng cho tiếng Việt ở mức keyword overlap.

**Top-K filtering:** Giữ top 5 insights có score cao nhất và diverse nhất (cosine similarity < 0.7 với nhau).

**Thứ tự thực thi:**
1. Phần 1 (Statistical Scoring) — làm ngay, effort thấp, gain độc lập
2. Phần 2 (Ranking + Dedup) — làm sau IDEA-05 hoàn thành

**Đánh giá sơ bộ:**
- Phần 1: không đụng kiến trúc, scipy có sẵn, làm được ngay
- Phần 2: đụng `AgentResult` → cần plan cẩn thận, làm sau cùng
- Cả 2 phần đều không thêm LLM call → không tăng latency

---

## IDEA-09 — Xử lý user_query đồng nhất trên tất cả experiment

**Trạng thái:** Đang thu thập ý kiến

**Động lực:**
- 4/6 experiment hiện tại bỏ qua `user_query` hoàn toàn — user nhập vào cho có, không ảnh hưởng kết quả
- Chỉ EDA và Tùy chỉnh thực sự đọc query
- Preprocessing hardcode cứng: fill missing → clip outlier → encode → scale, không có cách nào tùy chỉnh qua query

**Thực trạng từng agent:**

| Agent | user_query | domain_context |
|---|---|---|
| EDA | ✅ Dùng trong eda_planner | ✅ Dùng (nhưng fallback điện lực — xem IDEA-04) |
| Preprocessing | ❌ Bỏ qua hoàn toàn | ❌ Bỏ qua |
| Training | ⚠️ Fallback khi form trống | ✅ Dùng trong LLM explain |
| Evaluation | ❌ Bỏ qua hoàn toàn | ✅ Dùng trong LLM comment |
| Inference | ❌ Bỏ qua hoàn toàn | ✅ Dùng trong explain prediction |
| Tùy chỉnh | ✅ Dùng trực tiếp | — |
| Full Pipeline | ⚠️ EDA dùng, 3 bước còn lại bỏ qua | Mixed |

---

### Nhóm 1 — Quick win: thêm `{user_query}` vào prompt đã có (10 phút, 3 chỗ)

Evaluation, Inference, Training đều đã có LLM call sinh text giải thích — chỉ cần thêm field vào prompt:

```python
# ML_EXPLANATION_USER (dùng cho Training + Evaluation) — thêm:
"Yêu cầu của người dùng: {user_query}
Điều chỉnh cách giải thích theo yêu cầu đó."

# EXPLAIN_PREDICTION_PROMPT (Inference) — thêm:
"Yêu cầu: {user_query}"
```

Tác dụng ngay:
- "giải thích đơn giản cho khách hàng" → LLM bỏ thuật ngữ kỹ thuật
- "tập trung vào false positive" → highlight phần đó trong metrics
- "so sánh với baseline" → frame kết quả theo hướng đó

**Thay đổi code:** sửa `llm/prompts/ml_prompt.py` (2 prompt) + truyền `user_query` vào `call_llm` trong `evaluation_agent.py`, `inference_agent.py`, `training_agent.py`.

---

### Nhóm 2 — Medium: Preprocessing Planner

Preprocessing không có LLM call nào đọc query — cần thêm bước planning tương tự `eda_planner`:

```
user_query + quality_check_results
    │
    ▼ preprocessing_planner (LLM, MODEL_8B)
    → {"steps": ["fill_missing", "encode_categorical"], "skip": ["scale"],
       "method": {"fill_missing": "median", "outlier": "zscore"}}
    │
    ▼ chạy đúng các bước được chọn, với đúng method
```

Tác dụng:
- "chỉ xử lý missing, đừng scale" → skip scale
- "loại bỏ outlier bằng Z-score" → đổi method từ IQR sang Z-score
- "giữ nguyên cột categorical" → skip encode

**Thay đổi code:**
1. Thêm `llm/prompts/preprocessing_prompt.py` — PREPROCESSING_PLANNER_USER với tool list + param
2. Sửa `preprocessing_agent.py` — thêm planning step trước khi chạy pipeline, đọc plan để quyết định bước

---

### Nhóm 3 — Full Pipeline tự được

Không cần sửa thêm — `context.user_query` đã truyền nguyên qua các stage. Fix Nhóm 1 + 2 là pipeline hưởng lợi luôn.

---

**Thứ tự thực thi:**
1. Nhóm 1 (Evaluation + Inference + Training) — sửa prompt, effort cực thấp, làm trước
2. Nhóm 2 (Preprocessing Planner) — effort trung bình, làm sau
3. Full Pipeline — tự được sau 1+2

**Đánh giá sơ bộ:**
- Nhóm 1 là quick win rõ nhất trong toàn bộ IDEAS.md — sửa ít nhất, gain ngay trên 3 experiment
- Nhóm 2 làm Preprocessing trở thành agent thực sự thay vì hardcode pipeline
- Cả 2 nhóm không đụng kiến trúc, không thêm dependency mới

---

## IDEA-10 — Adaptive Replanning (2-Phase Planning)

**Trạng thái:** Đang thu thập ý kiến

**Động lực:**
- `eda_planner.plan()` sinh plan 1 lần từ schema — chưa có data thực khi plan
- Khi `check_missing` phát hiện 40% missing, plan đã xong → không thể thêm bước xử lý
- Plan hiện tại "mù" với kết quả thực tế, không thể điều chỉnh theo data

**Thiết kế đề xuất — Hướng A: 2-Phase Planning** *(khuyến nghị)*

```
Phase 1: luôn chạy cứng quality checks (không cần LLM plan)
  → check_missing, check_duplicates, basic_stats, check_outliers_iqr

Phase 1 xong → pass kết quả thực cho LLM → re-plan Phase 2
  LLM biết: "40% missing ở col X, outlier ở col Y, correlation cao A-B"
  → Phase 2 plan targeted hơn, không bỏ sót

Phase 2: execute như hiện tại
```

Chỉ thêm **1 LLM call**, không thay đổi `execute_plan()`.

**Hướng B — Trigger-based rules** *(bổ sung, không cần LLM)*
```python
# Sau Phase 1, auto-append step nếu gặp condition rõ ràng
if results["check_missing"]["pct_missing"] > 0.2:
    extra_steps.append({"tool": "plot_missing_heatmap", "params": {}})
if max_correlation > 0.95:
    extra_steps.append({"tool": "plot_heatmap", "params": {"cols": high_corr_cols}})
```
Deterministic, zero LLM call, xử lý case hiển nhiên mà không tốn token.

**Đề xuất kết hợp:** Hướng B cho rule cứng (missing > 20%, correlation > 0.9) + Hướng A cho time-series phase phức tạp hơn.

**Thay đổi code cần làm:**
1. Sửa `eda_agent.run()` — tách thành `_run_phase1()` (quality cứng) + `_run_phase2()` (LLM re-plan)
2. Thêm `PLANNER_PHASE2_USER` trong `planner_prompt.py` — nhận thêm `phase1_results`
3. Thêm `_apply_trigger_rules(results) -> list[step]` — rule-based auto-append

**Đánh giá sơ bộ:**
- Effort trung bình — sửa `eda_agent.py` và thêm 1 prompt variant
- Gain rõ: plan Phase 2 biết data thực → ít bước thừa, không bỏ sót case quan trọng
- Dependency: nên làm sau IDEA-04 (prompt optimization) đã ổn định

---

## IDEA-11 — Per-chart Caption

**Trạng thái:** Đang thu thập ý kiến

**Động lực:**
- `charts[]` là list path PNG thuần, `chart_viewer.py` render ảnh không có label
- User nhìn 10 chart không biết cái nào là gì nếu không đọc toàn bộ insight text
- Insight hiện tại là 1 text blob chung — không map được "đoạn này giải thích chart nào"

**Thiết kế đề xuất — Hướng A: Template caption** *(quick win, zero LLM, làm trước)*

```python
# eda_agent.execute_plan() — sinh caption từ tool name + params
CAPTION_TEMPLATES = {
    "plot_distribution": "Phân phối của cột {col}",
    "plot_time_series":  "Biến động {col} theo thời gian",
    "plot_heatmap":      "Ma trận tương quan giữa các cột",
    "plot_boxplot":      "Boxplot phát hiện outlier — {col}",
    "plot_decomposition":"Phân rã trend/seasonality — {col}",
    "plot_seasonal_pattern": "Pattern theo {by} — {col}",
    "plot_missing_heatmap":  "Bản đồ missing value",
}

# charts[] đổi từ list[str] thành list[dict]:
charts.append({"path": output, "caption": caption})
```

Sửa `chart_viewer.py` — render caption dưới mỗi ảnh:
```python
def render_charts(charts):
    for item in charts:
        st.image(item["path"])
        st.caption(item["caption"])  # 1 dòng thêm
```

Effort: 30 phút, không LLM call.

**Hướng B — Batch LLM caption** *(1 LLM call, caption giàu ngữ nghĩa, làm sau)*

```
Sau execute_plan xong, gửi 1 prompt:
  [{"tool": "plot_time_series", "col": "phu_tai_he_thong_MW", "key_stats": {...}}, ...]
  → "Viết 1 câu caption tiếng Việt cho mỗi biểu đồ dựa trên kết quả thực tế"
  → ["Phụ tải hệ thống dao động 15.000–24.000 MW, đỉnh vào tháng 6–7", ...]
```

Caption dựa trên data thực thay vì template → giàu thông tin hơn nhiều.

**Hướng C — Caption nhúng vào viz_engine** *(clean kiến trúc, làm cuối)*

Mỗi hàm `plot_*` nhận thêm `title=None` → `ax.set_title(title)` ghi lên ảnh PNG. Không cần đổi data structure, chart tự mang caption. Nhưng cần sửa toàn bộ hàm viz.

**Thứ tự thực thi:**
1. Hướng A (template) — làm ngay, zero risk
2. Hướng B (batch LLM) — làm sau khi Hướng A đã chạy, nâng chất lượng caption
3. Hướng C — optional, nếu muốn clean kiến trúc

**Thay đổi code (Hướng A):**
1. Sửa `eda_agent.execute_plan()` — thêm `CAPTION_TEMPLATES`, đổi `charts.append(path)` → `charts.append({"path": ..., "caption": ...})`
2. Sửa `chart_viewer.py` — render `st.caption()` dưới mỗi ảnh
3. Sửa `report_generator.py` — dùng caption khi nhúng chart vào báo cáo HTML

**Đánh giá sơ bộ:**
- Hướng A: effort cực thấp, gain UX ngay lập tức, không dependency
- Hướng B: 1 LLM call, gain chất lượng rõ
- Nên làm sớm — không có dependency, ảnh hưởng demo trực tiếp

---
