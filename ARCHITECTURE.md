# Kiến trúc hệ thống AutoEDA

## Tổng quan

Hệ thống AutoEDA là bản prototype rút gọn của VMLP (Viettel ML Platform), tập trung vào module **Khám phá dữ liệu** với AI agent hỗ trợ. Người dùng tạo bài toán, chọn loại experiment, agent tự động phân tích và trả về insight, biểu đồ, báo cáo bằng tiếng Việt.

**Input:** File CSV/Excel + file mô tả nghiệp vụ (Word/text, optional) + câu hỏi tiếng Việt

**Output:** Biểu đồ thống kê + nhận xét tiếng Việt + gợi ý phân tích tiếp theo + báo cáo EDA (HTML, có hỗ trợ PDF) + baseline ML model (optional)

> Tài liệu này mô tả đúng theo code hiện tại trong repo (không phải bản thiết kế ban đầu). Xem `FLOW.md` cho luồng end-to-end chi tiết.

---

## So sánh với VMLP thật

| Tính năng | VMLP thật | Prototype |
|-----------|-----------|-----------|
| Quản lý Workspace, User | Có | Không làm |
| Lập lịch chạy tự động | Có | Không làm |
| Kết nối DB (Postgres, MySQL) | Có | Không làm |
| JupyterLab tích hợp | Có | Không làm |
| Tạo bài toán | Có | Có (đơn giản) |
| Loại experiment template | Có | 5 template hiển thị trên UI (Khám phá dữ liệu, Xử lý dữ liệu, Huấn luyện, Đánh giá, Suy luận) + Full Pipeline. "Tùy chỉnh" vẫn tồn tại trong code (`router.py`, `run_experiment.py`) nhưng đang **ẩn khỏi UI** |
| AI agent hỗ trợ EDA | Không có | **Đây là phần bổ sung mới** |
| Insight tiếng Việt | Không có | **Đây là phần bổ sung mới** |

---

## Hai entry point độc lập (quan trọng)

Hệ thống có **hai cách chạy agent song song, không liên kết với nhau**:

1. **Streamlit UI** (`ui/`) — gọi agent **trực tiếp trong process** qua `agents.router.route()` + `asyncio.run(agent.run(context))`. Đây là đường chạy thực tế người dùng dùng hàng ngày (`ui/views/run_experiment.py:110-112`). State (problems, files, kết quả run) lưu trong `st.session_state`, không persist giữa các lần restart.
2. **FastAPI backend** (`mlops/api/`) — REST API riêng, cũng gọi đúng `agents.router.route()` nhưng lưu state trong `app.state` (in-memory dict, mất khi restart server). UI **không gọi** API này — hai lớp dùng chung agent layer nhưng là hai cổng vào tách biệt, có thể dùng độc lập (ví dụ tích hợp hệ thống khác qua REST).

---

## Cấu trúc thư mục

```
VDT2026/
├── ui/                              # UI layer — Streamlit
│   ├── app.py                       # Entry point, session state, routing giữa 7 trang
│   ├── views/
│   │   ├── home.py                  # Trang chủ — danh sách bài toán
│   │   ├── create_problem.py        # Tạo bài toán mới
│   │   ├── select_experiment.py     # Chọn loại experiment (5 template hiển thị + Full Pipeline)
│   │   ├── experiment_config.py     # Upload file CSV/Excel, file nghiệp vụ, mô tả/câu hỏi, cấu hình ML
│   │   ├── run_experiment.py        # Chạy experiment + human-in-the-loop (merge, refinement, pipeline stage)
│   │   ├── run_history.py           # Lịch sử các lần chạy + log
│   │   └── report.py                # Xem và download báo cáo HTML/PDF
│   └── components/
│       ├── file_uploader.py         # Upload nhiều file CSV/Excel + file test
│       ├── chat_box.py              # Chat interface tiếng Việt
│       ├── chart_viewer.py          # Hiển thị biểu đồ inline
│       ├── run_log.py               # Hiển thị execution log
│       └── experiment_card.py       # Card hiển thị thông tin bài toán/experiment
│
├── agents/                          # Agent layer — class python thường (không dùng framework agent)
│   ├── base_agent.py                # BaseAgent, ExperimentContext, AgentResult
│   ├── router.py                    # experiment_type (str) → instance agent tương ứng
│   │
│   ├── eda_agent.py                 # Khám phá dữ liệu — orchestrator phức tạp nhất (xem FLOW.md)
│   ├── file_detector.py             # Detect schema, join key, đề xuất merge — dùng bởi eda_agent
│   ├── eda_planner.py                # LLM lập kế hoạch tool calls (Phase 2) — dùng bởi eda_agent
│   ├── hypothesis_generator.py      # LLM sinh 2-3 giả thuyết kiểm chứng từ domain + schema
│   ├── question_generator.py        # LLM sinh 3-5 câu hỏi phân tích từ schema (+ profiling context)
│   ├── insight_generator.py         # LLM diễn giải kết quả EDA + đánh giá hypothesis, tiếng Việt
│   ├── report_generator.py          # Sinh báo cáo HTML/PDF — dùng bởi pipeline_agent / run_experiment
│   │
│   ├── preprocessing_agent.py       # Xử lý dữ liệu — cấu hình do preprocessing_planner quyết định
│   ├── preprocessing_planner.py     # LLM quyết định fill/outlier/encode/scale method theo user_query
│   ├── training_agent.py            # Detect task type, train baseline models, leaderboard
│   ├── evaluation_agent.py          # Load model, predict trên test data, metrics + biểu đồ + nhận xét
│   ├── inference_agent.py           # Load model, predict trên data mới, giải thích kết quả
│   │
│   └── pipeline_agent.py            # Full Pipeline — chạy theo stage: eda → preprocessing → training → evaluation
│
├── tools/                           # Processing layer — pure function, không gọi LLM (trừ ml/model_selector LLM-fallback)
│   ├── schema_analyzer.py           # read_schema, detect_datetime_columns, find_join_candidates, suggest_merge_plan
│   ├── quality_checker.py           # check_missing, check_duplicates, check_outliers_iqr/_rolling, check_type_mismatch
│   ├── stats_engine.py              # basic_stats, correlation/spearman, normality_test, group_stats, time series patterns
│   ├── relationship.py              # mutual_info_scores — mutual information giữa feature và target
│   ├── scorer.py                    # score_trend, score_pearson, score_group_diff — auto p-value/significance
│   ├── profiler.py                  # ydata-profiling (minimal mode) → context bổ sung cho planner/question_generator
│   ├── viz_engine.py                # 14 hàm vẽ biểu đồ matplotlib/seaborn (distribution, heatmap, time series, pairplot, mi scores...)
│   ├── file_merger.py               # resample_to_frequency, merge_files, validate_merge_result, add_holiday_feature
│   └── ml/                          # ML pipeline
│       ├── preprocessor.py          # handle_missing, encode_categorical, scale_features, NumericScaler, time features, train/test split
│       ├── pipeline.py              # PreprocessingPipeline — fit_transform/transform, lưu lại tham số để áp lại lúc evaluation/inference
│       ├── model_selector.py        # detect_task_type, get_baseline_models, get_param_distribution, suggest_models_by_llm
│       ├── trainer.py               # train_and_evaluate (+ optimize), compare_models, save_model/load_model_bundle
│       ├── metrics.py                # compute_supervised_metrics (regression/classification)
│       └── ml_viz.py                 # confusion matrix, feature importance, actual vs predicted, residuals, cluster scatter, model comparison
│
├── llm/                              # LLM backend
│   ├── client.py                     # OpenAI SDK client (call_llm), retry tối đa 3 lần khi 429, log token qua mlops.tracker
│   ├── cache.py                      # Cache output LLM theo hash(prompt+system+model)
│   └── prompts/
│       ├── planner_prompt.py         # Prompt EDA planner (Phase 2 tool calls)
│       ├── insight_prompt.py         # Prompt diễn giải tiếng Việt + đánh giá hypothesis
│       ├── report_prompt.py          # Prompt sinh nội dung báo cáo
│       ├── ml_prompt.py              # Prompt detect task type + giải thích kết quả ML
│       └── preprocessing_prompt.py   # Prompt preprocessing_planner (fill/outlier/encode/scale)
│
├── mlops/                            # MLOps layer
│   ├── tracker.py                    # W&B (wandb) — init_run/log_tokens/log_metrics, chỉ active khi có WANDB_API_KEY
│   ├── logger.py                     # ExecutionLogger — log từng bước (timestamp+step+decision+result) ra outputs/logs/<run_id>.json
│   └── api/
│       ├── main.py                   # FastAPI app, in-memory app.state (problems/experiments/runs/uploaded_files/reports)
│       └── routes/
│           ├── problems.py           # POST/GET /problems
│           ├── experiments.py        # POST /experiments, POST /experiments/{id}/run, GET /experiments/{id}/runs
│           ├── upload.py             # POST /upload?experiment_id=... (multipart file)
│           └── report.py             # GET /report/{job_id}
│
├── data/
│   ├── raw/                          # Dataset gốc (+ raw/uploads cho file qua API)
│   ├── processed/                    # File CSV sau preprocessing + pipeline .pkl + predictions CSV
│   └── domain/                       # File mô tả nghiệp vụ (Word/txt)
│
├── outputs/
│   ├── charts/                       # Biểu đồ EDA PNG
│   ├── ml_charts/                    # Biểu đồ ML PNG
│   ├── models/                       # Model bundle đã train (model + pipeline + metadata, joblib)
│   ├── reports/                      # Báo cáo HTML/PDF
│   └── logs/                         # Execution log JSON theo run_id
│
├── tests/
│   ├── test_schema_analyzer.py
│   ├── test_quality_checker.py
│   ├── test_stats_engine.py
│   ├── test_eda_agent.py
│   └── test_ml_pipeline.py
│
├── docker-compose.yml                # 2 service: ui (Streamlit :8501), api (FastAPI :8000)
├── Dockerfile                        # python:3.11-slim + pango/cairo (cho WeasyPrint)
├── requirements.txt
└── README.md
```

---

## Chi tiết từng module

### 1. UI layer — `ui/`

**`app.py`**
- Entry point Streamlit, set `sys.path` để import `agents`/`tools`/`llm`/`mlops` từ thư mục gốc
- Khởi tạo `st.session_state` (problem hiện tại, experiment type, files, context, kết quả run, pipeline stage...)
- Routing giữa 7 trang qua dict `PAGES`, mỗi trang là 1 module với hàm `render()`

**`views/home.py`** — danh sách bài toán đã tạo, thống kê số bài toán/số lần chạy, nút tạo mới

**`views/create_problem.py`** — form tạo bài toán: tên + mô tả

**`views/select_experiment.py`** — hiển thị 5 template (Khám phá dữ liệu, Xử lý dữ liệu, Huấn luyện, Đánh giá, Suy luận) + Full Pipeline dạng card. "Tùy chỉnh" bị comment-out (xem `select_experiment.py:13-14`) vì 5 template + Full Pipeline đã cover đủ nhu cầu thực tế, nhưng router vẫn hỗ trợ nếu cần mở lại

**`views/experiment_config.py`** — upload file dữ liệu (qua `file_uploader`), file nghiệp vụ optional, mô tả/câu hỏi, và với Full Pipeline còn cho upload file test riêng + chọn task type/target/model

**`views/run_experiment.py`** (file lớn nhất trong UI, ~440 dòng) — orchestrator chính:
- Tóm tắt input + cho phép làm rõ câu hỏi nếu quá ngắn/mơ hồ (`_detect_ambiguity`)
- Với nhiều file: hỏi merge trước khi chạy agent (gọi `file_detector.detect`)
- Gọi agent qua `route()` + `asyncio.run()`, hiển thị summary/insight/chart/log
- Full Pipeline: render theo stage (`pipeline_agent.STAGES`), có nút "Tiếp tục"/"Dừng tại đây — xem báo cáo" sau mỗi stage
- "Góp ý & chạy lại" — gộp kết quả lần trước + feedback người dùng vào `user_query`, reset state để chạy lại
- "Tùy chỉnh" (nếu mở lại trên UI): không qua agent, gọi `call_llm()` trực tiếp với `user_query`

**`views/run_history.py`** — danh sách run từ `st.session_state.runs` + log chi tiết đọc từ `ExecutionLogger.load(run_id)`

**`views/report.py`** — hiển thị/download báo cáo từ `st.session_state.report_path` (HTML render inline, PDF chỉ download)

---

### 2. Agent layer — `agents/`

Agent là class Python thường (không dùng framework agent như LangChain) — mỗi agent extend `BaseAgent` và implement `async def run(context)`.

**`base_agent.py`**

```python
@dataclass
class ExperimentContext:
    problem_name: str = ""
    problem_description: str = ""
    experiment_type: str = ""
    files: dict = field(default_factory=dict)        # filename -> DataFrame
    file_paths: dict = field(default_factory=dict)    # filename -> path trên disk
    domain_context: str = ""
    user_query: str = ""
    extra: dict = field(default_factory=dict)         # output từ agent trước (dùng trong pipeline)

@dataclass
class AgentResult:
    success: bool
    summary: str = ""
    data: dict = field(default_factory=dict)
    charts: list = field(default_factory=list)
    insights: str = ""
    log: list = field(default_factory=list)
    error: str = None

class BaseAgent:
    async def run(self, context: ExperimentContext = None) -> AgentResult: ...
    async def get_status(self) -> str: ...
```

**`router.py`**

```python
def route(experiment_type, context):
    agents = {
        "Khám phá dữ liệu": EDAAgent(context),
        "Xử lý dữ liệu": PreprocessingAgent(context),
        "Huấn luyện mô hình": TrainingAgent(context),
        "Đánh giá mô hình": EvaluationAgent(context),
        "Suy luận mô hình": InferenceAgent(context),
        "Tùy chỉnh": None,
        "Full Pipeline": PipelineAgent(context),
    }
    return agents.get(experiment_type)
```

---

**`eda_agent.py`** — Khám phá dữ liệu (orchestrator phức tạp nhất, ~480 dòng)
- Pipeline 2 phase: **Phase 1** chạy cứng (check_missing/duplicates/type_mismatch/basic_stats) không cần LLM, có `_trigger_rules()` tự sinh thêm step (plot_missing_heatmap nếu >15% missing, plot_violin cho cột lệch nhất, plot_pairplot cho cột tương quan cao) — **Phase 2** dùng LLM (`eda_planner`) lập kế hoạch dựa trên Phase 1 summary + hypothesis + câu hỏi sinh tự động
- Có `TOOL_REGISTRY` map tên tool (LLM sinh ra) → hàm thật trong `tools/`, kèm logic normalize tham số (`_normalize_params`) vì LLM hay đặt tên key khác nhau ("column" vs "col" vs "cols"...)
- Tự động gắn significance score (`_auto_score`, dùng `tools/scorer.py`) vào kết quả trend/correlation/group_stats
- Xem chi tiết toàn bộ flow trong `FLOW.md`

**`file_detector.py`** — đọc schema từng file, tìm join key (`tools/schema_analyzer`), gọi LLM đề xuất merge plan bằng tiếng Việt — dùng bởi `eda_agent`

**`eda_planner.py`** — LLM (MODEL_70B) lập kế hoạch tool calls cho Phase 2, parse JSON từ response, retry 1 lần không cache nếu parse lỗi

**`hypothesis_generator.py`** — LLM (MODEL_8B) sinh 2-3 giả thuyết kiểm chứng được từ domain context + schema (chỉ chạy khi có domain_context thực sự, bỏ qua nếu domain generic/rỗng)

**`question_generator.py`** — LLM (MODEL_8B) sinh 3-5 câu hỏi phân tích từ schema + profiling context, gộp vào `user_query` trước khi đưa cho `eda_planner`

**`insight_generator.py`** — LLM (MODEL_70B) diễn giải kết quả EDA theo domain tiếng Việt; nếu có hypothesis thì thêm section "Kiểm chứng giả thuyết" (XÁC NHẬN / BÁC BỎ / KHÔNG ĐỦ DỮ LIỆU)

**`report_generator.py`** — LLM (MODEL_70B) sinh nội dung báo cáo Markdown → convert HTML, nhúng biểu đồ base64 inline, export HTML (default) hoặc PDF (WeasyPrint) — dùng bởi `pipeline_agent.finalize()`

---

**`preprocessing_agent.py`** — xử lý dữ liệu, cấu hình (fill method, outlier method, skip nào) do `preprocessing_planner` quyết định theo `user_query` (không hardcode hoàn toàn). Dùng `tools/ml/pipeline.PreprocessingPipeline` để fit_transform, lưu CSV đã xử lý + pickle pipeline (để Evaluation/Inference tái sử dụng), LLM mô tả các bước đã làm bằng tiếng Việt

**`preprocessing_planner.py`** — LLM (MODEL_8B) parse `user_query` thành dict config (`fill_method`, `skip_outlier`, `outlier_method`, `skip_encode`, `skip_scale`, `scale_method`); query rỗng → dùng `DEFAULT_PLAN` luôn, không tốn LLM call

**`training_agent.py`** — nếu chưa có `target_col`/`task_type` thì gọi LLM detect (`TASK_DETECTION_USER`); chọn split theo thời gian nếu có cột datetime, ngược lại random split; `get_baseline_models` → `train_and_evaluate` → `compare_models` (leaderboard) → `save_model` (lưu kèm pipeline/task_type/target_col/feature_names/metrics); LLM giải thích kết quả tiếng Việt

**`evaluation_agent.py`** — load model bundle (`load_model_bundle`), áp lại đúng `pipeline.transform()` đã lưu lúc train lên data test mới, tính metrics theo task_type (regression/classification/clustering), vẽ chart tương ứng, LLM nhận xét chất lượng model

**`inference_agent.py`** — load model bundle, áp pipeline.transform lên data mới (không có cột target), predict, lưu CSV kết quả (`outputs`/`data/processed/predictions_*.csv`), nếu file có sẵn target thì tính thêm `bonus_metrics`, LLM giải thích kết quả dự đoán

---

**`pipeline_agent.py`** — Full Pipeline, chạy theo **stage** (`STAGES = ["eda", "preprocessing", "training", "evaluation"]`) qua `run_stage()` để UI có thể dừng/confirm giữa các bước:

```python
class PipelineAgent(BaseAgent):
    async def run_stage(self, stage, context, steps):
        # eda -> context.extra["eda_insights"]
        # preprocessing -> context.files = {"processed": df_processed}, lưu pipeline vào context.extra
        # training -> context.extra["model_path"], context.extra["target_col"]
        # evaluation -> dùng test_df riêng (nếu có) hoặc raw_df gốc, EvaluationAgent tự áp pipeline.transform
        ...

    async def run(self, context=None):
        # chạy hết STAGES, dừng sớm nếu 1 stage fail hoặc context.extra["stop_after"] khớp
        ...

    def finalize(self, context, steps):
        # gộp charts + execution_log của mọi stage đã chạy, gọi report_generator.generate() 1 lần
        ...
```

Output của bước trước tự động làm input bước sau qua `context.extra`/`context.files`. UI gọi `run_stage()` từng stage một, hiển thị kết quả, rồi mới cho phép "Tiếp tục" hoặc "Dừng tại đây" — đúng là human-in-the-loop nhưng implement bằng polling-per-stage, không phải callback/event.

---

### 3. Processing layer — `tools/`

Hàm thuần (input DataFrame → output DataFrame/dict/đường dẫn ảnh), không gọi LLM (trừ `ml/model_selector.suggest_models_by_llm`, hiện không được agent nào gọi). Danh sách đầy đủ: xem cây thư mục ở trên hoặc đọc trực tiếp signature trong từng file — không có doc riêng `TOOLS.md` được đồng bộ, **tin code hơn doc cũ**.

---

### 4. LLM backend — `llm/`

**`client.py`**
- Dùng **OpenAI SDK** (`from openai import OpenAI`), không phải Groq/Llama như bản thiết kế cũ
- `MODEL_70B = MODEL_8B = "gpt-5.4-nano"` — cả hai hằng số hiện trỏ về cùng 1 model, giữ tên biến để dễ đổi model riêng cho planner/insight (70B-tier) vs các tác vụ phụ (8B-tier) sau này nếu cần
- Retry tối đa 3 lần khi `APIStatusError` status_code 429, exponential backoff `2**attempt`; lỗi khác cũng retry với backoff rồi raise nếu hết lượt
- Log token tiêu thụ qua `mlops.tracker.log_tokens()` (best-effort, không raise nếu W&B chưa init)

**`cache.py`** — cache output theo hash(prompt + system + model), TTL 1 giờ, tránh gọi lại khi rerun cùng phân tích/rate limit

---

### 5. MLOps layer — `mlops/`

**`tracker.py`** — W&B, chỉ active khi có `WANDB_API_KEY` trong env; `init_run`, `log_tokens`, `log_metrics`, `finish_run`

**`logger.py`** — `ExecutionLogger`: log từng bước (timestamp + step + decision + result) ra `outputs/logs/<run_id>.json`; static method `load(run_id)` và `list_runs()` đọc lại cho trang `run_history`

**`api/main.py`** — FastAPI app, state lưu in-memory (`app.state.problems/experiments/runs/uploaded_files/reports`), 4 router:
- `POST /problems`, `GET /problems`
- `POST /experiments`, `POST /experiments/{id}/run` (gọi đúng `agents.router.route()`), `GET /experiments/{id}/runs`
- `POST /upload?experiment_id=...` — upload CSV/Excel, lưu DataFrame vào `app.state.uploaded_files`
- `GET /report/{job_id}` — trả file báo cáo nếu experiment đã sinh report

Lưu ý: API này **không được Streamlit UI gọi** — là cổng vào REST độc lập, state mất khi restart vì không có DB.

---

## Constraints tự đặt (prototype)

- Chỉ support tabular data: CSV, Excel
- File nghiệp vụ: Word (.docx) hoặc plain text (.txt)
- Báo cáo xuất ra: HTML (default) hoặc PDF
- Ngôn ngữ hệ thống: tiếng Việt
- LLM: OpenAI API — cache để tránh rate limit
- Deploy: local Docker Compose (2 service: ui + api), không cần cloud
- Bài toán ML: regression, classification, clustering
- Không làm: quản lý workspace, user, lập lịch, kết nối DB ngoài, đồng bộ state giữa UI và API

---

## Tech stack

| Layer | Công nghệ |
|-------|-----------|
| UI | Streamlit |
| Agent | Python thuần (class kế thừa `BaseAgent`, async `run()`) — không dùng LangChain |
| LLM | OpenAI API (`gpt-5.4-nano`) |
| Data processing | Pandas, NumPy |
| EDA | ydata-profiling (minimal mode, hybrid với tool tự viết) |
| ML | Scikit-learn, XGBoost |
| Visualization | Matplotlib, Seaborn |
| Backend API | FastAPI (cổng vào song song, độc lập với UI) |
| MLOps | Weights & Biases (optional), Docker Compose |
| Report | WeasyPrint (PDF), Jinja2 + markdown (HTML) |
