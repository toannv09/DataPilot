# Flow end-to-end

> Mô tả đúng theo code hiện tại (`agents/`, `ui/views/run_experiment.py`). Xem `ARCHITECTURE.md` để biết vai trò từng module.

## Tổng quan

```
User vào trang chủ (home.py)
      │
      ▼
Tạo bài toán: tên + mô tả (create_problem.py)
      │
      ▼
Chọn loại experiment (select_experiment.py)
  5 template hiển thị + Full Pipeline
  ("Tùy chỉnh" có trong router.py nhưng bị ẩn khỏi UI)
      │
      ▼
Cấu hình: upload file, file nghiệp vụ, câu hỏi (experiment_config.py)
      │
      ▼
run_experiment.py → agents.router.route(experiment_type, context)
      │
      ├── Khám phá dữ liệu → EDAAgent        (flow chi tiết bên dưới)
      ├── Xử lý dữ liệu    → PreprocessingAgent
      ├── Huấn luyện       → TrainingAgent
      ├── Đánh giá         → EvaluationAgent
      ├── Suy luận         → InferenceAgent
      ├── Tùy chỉnh        → None (route trả None) → UI gọi call_llm() trực tiếp, không qua agent
      └── Full Pipeline    → PipelineAgent (chạy theo stage, xem mục riêng)
      │
      ▼
asyncio.run(agent.run(context)) → AgentResult (summary, insights, charts, log, data)
      │
      ▼
Hiển thị kết quả + lưu run vào ExecutionLogger (outputs/logs/<run_id>.json)
      │
      ▼
(optional) Xem/download báo cáo HTML/PDF — report.py
```

Lưu ý: đây là cách Streamlit UI chạy (gọi agent **trực tiếp trong process**, không qua HTTP). FastAPI backend (`mlops/api/`) làm đúng việc tương tự (`route()` → `agent.run()`) nhưng qua REST, độc lập với UI — hai đường không gọi lẫn nhau.

---

## Flow chi tiết — Khám phá dữ liệu (`EDAAgent.run()`, `agents/eda_agent.py`)

### Bước 1 — Cấu hình experiment

User điền trên `experiment_config.py`: upload file CSV/Excel, file nghiệp vụ Word/txt (optional), nhập câu hỏi.

### Bước 2 — Detect schema và đề xuất merge (nếu >1 file)

```
file_detector.detect(files, file_paths)
  → read_schema() từng file (tên cột, kiểu, sample)
  → find_join_candidates() — cột trùng tên giữa các file
  → suggest_merge_plan() — MergePlan(can_merge, ...)
  → nếu can_merge: gọi LLM (MODEL_8B) sinh suggestion tiếng Việt
```

**Human-in-the-loop** (`run_experiment.py`): hiển thị suggestion, user bấm "Đồng ý gộp" hoặc "Phân tích riêng từng file" → lưu vào `st.session_state.merge_decision`.

### Bước 3 — Chuẩn bị DataFrame (`EDAAgent._prepare_dataframe`)

```
nếu chỉ 1 file → dùng luôn
nếu nhiều file + merge_confirmed=True → file_merger.merge_files(files, merge_plan)
nếu không → dùng file đầu tiên
sau đó: detect_datetime_columns() → set DatetimeIndex + sort_index() nếu tìm thấy cột thời gian
```

### Bước 4 — Phase 1: kiểm tra chất lượng cứng (không cần LLM)

```
_run_phase1(df):
  check_missing, check_duplicates, check_type_mismatch
  + basic_stats (nếu có cột số)

_trigger_rules(phase1_results, df) — tự sinh thêm step không phụ thuộc LLM chọn:
  - total_missing/n_rows > 15%        → plot_missing_heatmap
  - |skewness| > 1.5 của 1 cột số     → plot_violin (chỉ 1 cột lệch nhất)
  - >= 3 cột số                       → plot_pairplot (chọn cột tương quan trung bình cao nhất)
```

### Bước 5 — Profiling + sinh hypothesis/câu hỏi (context bổ sung trước khi plan)

```
profiler.run_profiling(df)            → ydata-profiling minimal mode (sample tối đa 5000 dòng)
profiler.profiling_to_context(...)    → tóm tắt alert/correlation/missing thành text ngắn

hypothesis_generator.generate_hypotheses(schemas, domain_context)
  → chỉ chạy nếu domain_context thực sự (>=30 ký tự, không phải domain generic)
  → LLM (MODEL_8B) sinh 2-3 giả thuyết test được (so sánh nhóm theo cột categorical CÓ SẴN,
    hoặc tương quan 2 cột số có sẵn) — KHÔNG sinh giả thuyết kiểu "top 25%"/chia ngưỡng

question_generator.generate_questions(schemas, user_query, domain_context, has_datetime, profiling_context)
  → LLM (MODEL_8B) sinh 3-5 câu hỏi phân tích, ưu tiên theo profiling alert,
    cấm sinh câu hỏi time series nếu KHÔNG có DatetimeIndex

→ Gộp questions + hypotheses vào user_query gốc thành enriched_query
```

### Bước 6 — Phase 2: LLM lập kế hoạch (`eda_planner.plan`)

```
eda_planner.plan(enriched_query, schemas, domain_context, available_columns,
                  has_datetime_index, phase1_summary)
  → LLM (MODEL_70B) trả JSON {"steps": [{"tool": ..., "params": {...}}], "explanation": "..."}
  → nếu parse JSON lỗi: retry 1 lần không dùng cache, nếu vẫn lỗi → steps rỗng
→ ghép extra_steps (từ trigger_rules) vào ĐẦU plan.steps
```

### Bước 7 — Thực thi plan (`EDAAgent.execute_plan`)

```
với mỗi step:
  normalize tham số LLM sinh ra (_normalize_params) — map "column"/"columns" về đúng tên
    tham số tool (col/cols/col1+col2/target_col/by...)
  skip nếu: tool không tồn tại trong TOOL_REGISTRY,
            tool cần DatetimeIndex mà df không có,
            tool phân tích shape phân phối mà cột có < 5 giá trị duy nhất
  gọi tool, retry tối đa 3 lần nếu lỗi
  nếu là chart tool → append vào charts[] kèm caption (CAPTION_TEMPLATES)
  nếu DataFrame kết quả > 100 dòng → truncate, đánh dấu truncated=True
  _auto_score() — gắn p-value/significance vào kết quả hourly/weekly/monthly_pattern,
    correlation_matrix/spearman (chỉ giữ pair |r|>0.3 và significant), group_stats
  log lại từng step (status: success/error/skipped)
```

**Human-in-the-loop** (mô tả ý tưởng, chưa có UI riêng chặn từng bước — kết quả hiển thị 1 lần sau khi cả Phase 1+2 chạy xong, không pause giữa từng tool call).

### Bước 8 — Sinh insight tiếng Việt

```
insight_generator.generate(results, domain_context, hypotheses=hypotheses)
  → LLM (MODEL_70B), serialize results với truncate dần nếu vượt 200k ký tự
  → nếu có hypotheses: thêm section "Kiểm chứng giả thuyết"
    (✅ XÁC NHẬN / ❌ BÁC BỎ / ⚠️ KHÔNG ĐỦ DỮ LIỆU, giải thích bằng câu văn tiếng Việt tự nhiên,
     không dùng ký hiệu kiểu code)
```

### Bước 9 — Trả kết quả

`AgentResult(success=True, summary=plan_data["explanation"], data={"results", "merge_info"}, charts, insights, log)` — UI hiển thị summary/insight/chart/log, lưu run qua `ExecutionLogger`.

### Bước 10 — Sinh báo cáo (chỉ khi qua Full Pipeline, hoặc user tự bấm "Xem báo cáo")

EDA Agent đơn lẻ **không tự gọi `report_generator`** — chỉ `PipelineAgent.finalize()` gọi báo cáo tổng hợp (xem mục Full Pipeline). Khi chạy EDA đơn lẻ, `st.session_state.report_path` không được set trừ khi flow khác set nó.

---

## Flow — Xử lý dữ liệu (`PreprocessingAgent.run()`)

```
df = file đầu tiên trong context.files
check_missing(df) → quality_summary (tiếng Việt, mô tả số dòng/cột thiếu/cột số/cột phân loại)

preprocessing_planner.plan(user_query, quality_summary)
  → query rỗng: DEFAULT_PLAN (median fill, iqr outlier, standard scale, không skip gì)
  → query có nội dung: LLM (MODEL_8B) parse thành config
    {fill_method, skip_outlier, outlier_method, skip_encode, skip_scale, scale_method}

PreprocessingPipeline().fit_transform(df, target_col, **cfg)
  → fill missing (numeric: mean/median theo cfg; categorical: forward fill + mode)
  → clip outlier theo IQR/zscore (skip nếu target_col, hoặc cột có <5 giá trị duy nhất)
  → encode categorical: LabelEncoder nếu >10 unique, one-hot nếu <=10
  → scale numeric: StandardScaler/MinMaxScaler (không scale target_col)
  → lưu mọi tham số đã học (missing_fill, outlier_bounds, encoders, scaler, feature_columns)
    để gọi lại transform() y nguyên lúc Evaluation/Inference

Lưu output:
  data/processed/processed_<timestamp>.csv   — DataFrame đã xử lý
  data/processed/pipeline_<timestamp>.pkl     — PreprocessingPipeline (joblib)

steps_log (tiếng Việt, mô tả từng thay đổi cụ thể) → LLM (MODEL_8B) viết đoạn mô tả
  ngắn gọn cho người không chuyên kỹ thuật
```

---

## Flow — Huấn luyện mô hình (`TrainingAgent.run()`)

```
df = file đầu tiên trong context.files (thường là output Preprocessing)
target_col/task_type: ưu tiên lấy từ context.extra (UI cho chọn), nếu thiếu và
  task_type != "clustering" → LLM (MODEL_70B, TASK_DETECTION_USER) detect tự động

xử lý numeric: handle_missing(median) cho cột còn NaN
nếu chưa rõ task_type → model_selector.detect_task_type(df_numeric, target_col)

split:
  clustering + đã qua Preprocessing stage → dùng nguyên df (đã scale từ trước)
  clustering + chưa qua Preprocessing     → tự fit NumericScaler riêng (bắt buộc scale cho KMeans/DBSCAN)
  có cột datetime                          → train_test_split_time (80/20 theo thời gian)
  không có datetime                        → train_test_split_random

get_baseline_models(task_type, selected_model, model_params) → train_and_evaluate(..., optimize=...)
  → results theo từng model: {model, metrics}
compare_models(results) → leaderboard (DataFrame, sort theo metric)
get_best_model(results, metric) → model tốt nhất theo DEFAULT_METRIC[task_type]
  (regression: rmse, classification: f1, clustering: silhouette)

charts: plot_model_comparison (nếu >1 model), plot_feature_importance (nếu model hỗ trợ)

save_model(best_model, name, pipeline=context.extra["preprocessing_pipeline"] hoặc clustering_scaler,
           task_type, target_col, feature_names, metric, metrics)
  → outputs/models/<...>.pkl (joblib bundle, để Evaluation/Inference load lại transform đúng)

LLM (MODEL_70B, ML_EXPLANATION_USER) giải thích leaderboard + feature importance bằng tiếng Việt
```

---

## Flow — Đánh giá mô hình (`EvaluationAgent.run()`)

```
load_model_bundle(context.extra["model_path"]) → model, pipeline, task_type, target_col, feature_names
df = file test mới upload

nếu có pipeline đã lưu lúc train:
  X = pipeline.transform(df bỏ cột target)   — áp ĐÚNG fill/outlier/encode/scale đã học lúc train
nếu không có pipeline:
  X = df numeric, fill median thủ công

loại dòng thiếu target (không có nhãn thật thì không đánh giá được dòng đó)

theo task_type:
  regression     → predict, compute_supervised_metrics, plot_actual_vs_predicted + plot_residuals
  classification → predict, compute_supervised_metrics, plot_confusion_matrix
  clustering     → predict labels (nếu model hỗ trợ), silhouette_score (nếu >1 cluster), plot_cluster_scatter

LLM (MODEL_70B, ML_EXPLANATION_USER) nhận xét chất lượng model bằng tiếng Việt
```

---

## Flow — Suy luận mô hình (`InferenceAgent.run()`)

```
load_model_bundle(context.extra["model_path"])
df = file data mới (thường KHÔNG có cột target — đó là cái cần dự đoán)

target_col ưu tiên lấy từ bundle (lúc train), không chỉ dựa vào context.extra
  vì dropdown UI chỉ liệt kê cột có trong file mới, có thể không khớp/không có

nếu có pipeline đã lưu → pipeline.transform(df bỏ target nếu có)
nếu không → fill median thủ công trên cột numeric

predict → df_result["predicted"] = predictions
lưu data/processed/predictions_<timestamp>.csv (giữ predictions cho TẤT CẢ dòng)

nếu file mới CÓ sẵn cột target (vd để so sánh):
  loại dòng thiếu target, tính bonus_metrics + vẽ chart (actual_vs_predicted/confusion_matrix)
  (chỉ để tham khảo, không bắt buộc)

LLM (MODEL_70B) giải thích ý nghĩa 5 dòng dự đoán đầu, theo user_query + domain_context
```

---

## Flow — Full Pipeline (`PipelineAgent`)

`STAGES = ["eda", "preprocessing", "training", "evaluation"]`. Chạy theo 1 trong 2 cách:

**Cách 1 — gọi trực tiếp `agent.run(context)`** (vd qua FastAPI): chạy hết STAGES tuần tự trong `run_stage()`, dừng sớm nếu 1 stage `success=False` hoặc khớp `context.extra["stop_after"]`, rồi `finalize()`.

**Cách 2 — UI (`run_experiment.py._render_pipeline`)**: chạy **từng stage một** theo polling — mỗi lần rerun Streamlit chỉ gọi `run_stage()` cho đúng 1 stage chưa có kết quả, hiển thị kết quả, rồi user bấm "Tiếp tục" (tăng `pipeline_stage_idx`) hoặc "Dừng tại đây — xem báo cáo" (gọi `finalize()` ngay với các stage đã chạy).

```
[EDA Agent] → context.extra["eda_insights"] = result.insights

[Preprocessing Agent] → context.files = {"processed": df_processed}
                         context.extra["raw_df"] = df gốc (giữ lại cho Evaluation)
                         context.extra["preprocessing_pipeline"] = pipeline đã fit

[Training Agent] → context.extra["model_path"], context.extra["target_col"]

[Evaluation Agent] → ưu tiên dùng test_df riêng (context.extra["test_df"], upload ở
                      experiment_config.py); nếu không có thì dùng lại raw_df ban đầu.
                      EvaluationAgent tự gọi pipeline.transform() trên data thô này.

finalize(): gộp charts + execution_log mọi stage đã chạy, gọi report_generator.generate()
            MỘT LẦN duy nhất (dataset_info, eda_results, ml_results gộp training+evaluation metrics)
            → outputs/reports/report_<timestamp>.html (hoặc .pdf nếu output_format="pdf" — hiện
              không có caller nào truyền "pdf", luôn ra HTML mặc định)
```

Nếu user dừng ở stage nào, kết quả đến stage đó vẫn được lưu lại và vẫn sinh được báo cáo tổng hợp (chỉ thiếu phần các stage chưa chạy).

---

## Flow — Tùy chỉnh (ẩn khỏi UI, vẫn chạy được nếu mở lại)

```
router.route("Tùy chỉnh", context) → trả về None (không có agent cố định)
run_experiment.py phát hiện None → gọi trực tiếp call_llm(context.user_query, model=MODEL_70B)
→ hiển thị response, không có chart/log/insight có cấu trúc
```

---

## Refinement — "Góp ý & chạy lại"

Sau khi 1 agent (hoặc cả pipeline) chạy xong và `success=True`, UI hiển thị ô góp ý (`_render_refinement_box`). Nếu user nhập feedback và bấm "Chạy lại":

```
context.user_query = user_query gốc
  + "--- Kết quả lần chạy trước ---" (summary, cắt tối đa 3000 ký tự)
  + "--- Góp ý của người dùng ---" (feedback)
  + yêu cầu LLM điều chỉnh theo góp ý, không lặp lại y nguyên kết quả cũ
→ reset state liên quan (agent_result / pipeline_steps / pipeline_stage_idx / pipeline_result)
→ rerun toàn bộ flow agent/pipeline với context mới
```

---

## Hybrid approach — Tool có sẵn vs LLM tự do

- **Tool có sẵn** (`tools/`) dùng cho mọi bước EDA/ML chuẩn — LLM chỉ chọn tool + tham số, không sinh code thực thi tự do. Toàn bộ pipeline EDA/Preprocessing/Training/Evaluation/Inference đều theo hướng này.
- **LLM trả lời tự do, không qua tool** chỉ xảy ra ở nhánh "Tùy chỉnh" (`call_llm()` trực tiếp với câu hỏi user) — hiện bị ẩn khỏi UI, không phải pattern chính của hệ thống.
