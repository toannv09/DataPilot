# Flow EDA Agent — chi tiết

> Mô tả chính xác cách `EDAAgent` (Khám phá dữ liệu) hoạt động ở thời điểm hiện tại.
> `FLOW.md` đã lỗi thời cho phần EDA — file này thay thế phần đó.

## Tổng quan 1 hình

```
UI: experiment_config (upload file, domain, query)
        │
        ▼
UI: run_experiment — Xác nhận trước khi chạy
        │  - Preview 5 dòng đầu mỗi file
        │  - Detect ambiguity trong query → hỏi làm rõ nếu cần
        │  - (nếu >1 file) đề xuất merge plan, chờ confirm
        ▼
EDAAgent.run(context)
        │
        ├─[1]─ detect()                     → schema, join key, merge plan
        ├─[2]─ _prepare_dataframe()          → merge (nếu đồng ý) + set DatetimeIndex
        │
        ├─[3]─ Phase 1 (KHÔNG cần LLM, luôn chạy, deterministic)
        │       check_missing, check_duplicates, check_type_mismatch, basic_stats
        │       → _trigger_rules(): tự thêm bước theo ngưỡng (không qua LLM)
        │
        ├─[4]─ ydata-profiling hybrid (deterministic)
        │       → alerts + top correlation + missing cao → context cho bước 6
        │
        ├─[5]─ Hypothesis Generation (LLM, CHỈ khi có domain thật)
        │       → 2-3 giả thuyết test được bằng tool sẵn có
        │
        ├─[6]─ Self-Generating Questions (LLM, luôn chạy)
        │       → 3-5 câu hỏi phân tích, ưu tiên theo profiling + domain
        │
        ├─[7]─ Phase 2 Planning (LLM — eda_planner)
        │       Input: query gốc + questions + hypotheses + phase1_summary
        │              + available_columns + has_datetime_index
        │       Output: {"steps": [...], "explanation": "..."}
        │
        ├─[8]─ execute_plan() — chạy từng step
        │       → 3 guard runtime (không phụ thuộc LLM tuân thủ):
        │          - DATETIME_REQUIRED_TOOLS: skip nếu không có DatetimeIndex
        │          - DISTRIBUTION_SHAPE_TOOLS: skip nếu cột < 5 giá trị duy nhất
        │          - tool không tồn tại: skip + log
        │       → _normalize_params(): sửa tên param sai LLM hay generate
        │       → _auto_score(): gắn p-value/significance sau mỗi tool thống kê
        │       → charts.append({"path":..., "caption":...})
        │
        ├─[9]─ insight_generator.generate()  (LLM)
        │       → Tổng quan, Vấn đề dữ liệu, Insight chính (chọn lọc, lời thường dẫn trước),
        │         Bước tiếp theo, + Kiểm chứng giả thuyết (nếu có hypotheses)
        │
        ▼
AgentResult(summary, data, charts, insights, log)
        │
        ▼
UI: hiển thị + refinement box ("góp ý → chạy lại, gộp kết quả lần trước + góp ý mới")
```

---

## Chi tiết từng bước

### Bước 0 — UI: Xác nhận trước khi chạy (`run_experiment.py`)

- `_render_input_summary()`: hiện loại experiment, file (số dòng/cột), query, domain, **preview 5 dòng đầu mỗi file**.
- `_detect_ambiguity(user_query)`: query rỗng/<15 ký tự/chỉ có từ generic ("phân tích", "xem"...) → hiện 2 câu hỏi làm rõ (cột nào, phân tích gì).
- Nếu >1 file: `file_detector.detect()` chạy trước, đề xuất merge plan bằng tiếng Việt (LLM), user bấm "Đồng ý kết hợp" hoặc "Phân tích riêng từng file".
- Chỉ sau khi bấm "Xác nhận & Chạy" mới gọi `EDAAgent.run()`.

### Bước 1 — `detect()`

Gọi `file_detector.detect(files, file_paths)`:
- Đọc schema từng file (tên cột, dtype, n_rows, sample).
- `find_join_candidates()`: tìm cột trùng tên hoặc cột thời gian có thể join.
- `suggest_merge_plan()`: LLM diễn giải merge plan bằng tiếng Việt (chỉ gọi LLM nếu có >1 file và có join candidate).

### Bước 2 — `_prepare_dataframe()`

- 1 file → dùng trực tiếp.
- >1 file + đã confirm merge → `file_merger.merge_files()`.
- `detect_datetime_columns(df)`: tìm cột ngày giờ — **chỉ xét cột KHÔNG phải dạng số** (tránh false positive như `overtime_hours` chứa substring "time" nhưng là số giờ làm thêm, không phải ngày giờ).
- Nếu tìm được cột datetime → `set_index().sort_index()`.

### Bước 3 — Phase 1 (`_run_phase1`)

Chạy cứng, KHÔNG qua LLM — luôn thực thi 4 tool: `check_missing`, `check_duplicates`, `check_type_mismatch`, `basic_stats` (tất cả cột số).

`_trigger_rules(phase1_results, df)` — tự thêm step theo ngưỡng, không cần LLM quyết định:
| Điều kiện | Step tự thêm |
|---|---|
| Tổng % missing > 15% | `plot_missing_heatmap` |
| Có cột `\|skewness\| > 1.5` | `plot_violin` (cột lệch nhất) |
| ≥ 3 cột số | `plot_pairplot` (top 5 cột có \|corr\| trung bình cao nhất — chọn bằng `_select_pairplot_cols`) |

→ Đảm bảo **mọi lần chạy đều có ít nhất 1 phân tích multivariate thật**, không phụ thuộc LLM có chọn `plot_pairplot` hay không.

### Bước 4 — ydata-profiling hybrid (`tools/profiler.py`)

- `run_profiling(df)`: chạy `ProfileReport(minimal=True)`, sample tối đa 5000 dòng. Trích: alerts (missing/zeros/unique...), top correlation Pearson (|r|≥0.65), thống kê biến.
- `profiling_to_context()`: rút gọn thành vài dòng text.
- Dùng làm context bổ sung cho Self-Generating Questions (bước 6) — **không hiển thị trực tiếp cho user**, chỉ ảnh hưởng gián tiếp qua câu hỏi tự sinh.
- Lỗi (thiếu thư viện, dataset lạ) → trả `{}`, không làm crash pipeline.

### Bước 5 — Hypothesis Generation (`agents/hypothesis_generator.py`)

- **Chỉ chạy khi có domain context thật** (không chạy với `DOMAIN_GENERIC` hoặc domain rỗng/<30 ký tự) — tránh sinh giả thuyết vô căn cứ.
- Sinh 2-3 giả thuyết, **bị constrain chỉ theo 2 dạng test được bằng tool sẵn có**:
  1. So sánh 1 cột số giữa các nhóm của 1 cột categorical có sẵn (`group_stats`)
  2. Tương quan giữa 2 cột số có sẵn (`correlation_matrix`/`spearman_correlation`)
- Cấm sinh giả thuyết dạng "X > trung bình của X" (cần bin động theo ngưỡng — không có tool hỗ trợ).
- Giả thuyết được gộp vào `enriched_query` **trước khi** planner chạy, để planner biết cần test gì.

### Bước 6 — Self-Generating Questions (`agents/question_generator.py`)

- Luôn chạy (không cần domain). Sinh 3-5 câu hỏi phân tích từ schema + profiling context + domain.
- Nếu **không có DatetimeIndex**: bị cấm sinh câu hỏi liên quan thời gian (tránh planner bị kéo theo sinh `plot_time_series` sai).
- Câu hỏi được gộp vào `enriched_query`.

### Bước 7 — Phase 2 Planning (`agents/eda_planner.py` + `llm/prompts/planner_prompt.py`)

LLM (MODEL_70B) nhận: `enriched_query` (gốc + questions + hypotheses), schema, **danh sách cột thật trong df** (whitelist — chống bịa tên cột), thông tin có/không DatetimeIndex, `phase1_summary` (để không lặp lại bước Phase 1 đã chạy).

Output: `{"steps": [{"tool": ..., "params": ...}], "explanation": "..."}`. Có few-shot example + negative instruction (cấm tên param sai, cấm gọi tool không tồn tại).

### Bước 8 — `execute_plan()`

Với mỗi step trong plan (Phase 2 + trigger steps từ Phase 1):

1. Lọc bỏ param thừa LLM hay thêm (`df`, `dataset`, `data`).
2. `_normalize_params()`: sửa tên param sai (vd `column` → `col`, `columns` → `cols`) theo nhóm tool.
3. **3 guard chạy trước khi gọi tool** (chặn cứng, không phụ thuộc LLM tuân thủ prompt):
   - Tool không tồn tại trong `TOOL_REGISTRY` → skip.
   - Tool trong `DATETIME_REQUIRED_TOOLS` mà df không có `DatetimeIndex` → skip.
   - Tool trong `DISTRIBUTION_SHAPE_TOOLS` mà cột có `nunique() < 5` → skip (tránh phân tích phân phối trên cột nhị phân/cờ).
4. Gọi tool, retry tối đa 3 lần nếu lỗi.
5. Nếu là chart tool → lưu `{"path":..., "caption":...}` (caption sinh từ `CAPTION_TEMPLATES` theo tên tool + params).
6. `_auto_score()`: tự gắn p-value/significance vào kết quả của tool thống kê:
   - `hourly/weekly/monthly_pattern` → Kendall tau trend test
   - `correlation_matrix`/`spearman_correlation` → Pearson p-value, dedupe cặp đối xứng, sort theo |r|, giữ top 3 mạnh nhất
   - `group_stats` → Kruskal-Wallis test

### Bước 9 — `insight_generator.generate()` (`llm/prompts/insight_prompt.py`)

LLM (MODEL_70B) diễn giải `results` (Phase 1 + Phase 2 đã merge) thành tiếng Việt tự nhiên, theo cấu trúc:
1. Tổng quan (lời thường, số liệu trong ngoặc)
2. Vấn đề dữ liệu
3. Insight chính (tối đa 4, chọn lọc — không liệt kê hết; mỗi insight: diễn giải → vì sao → hành động)
4. Bước tiếp theo
5. **Kiểm chứng giả thuyết** (nếu có hypotheses) — mỗi giả thuyết: XÁC NHẬN / BÁC BỎ / KHÔNG ĐỦ DỮ LIỆU + giải thích tại sao bằng lời thường

Domain context: dùng domain thật nếu có, fallback `DOMAIN_GENERIC` nếu không (không hardcode điện lực).

Quy tắc bắt buộc: viết hoàn toàn tiếng Việt tự nhiên, không giữ `tên_biến=giá_trị` kiểu code, không liệt kê hết mọi tương quan (chỉ 1-2 quan hệ mạnh nhất kèm giải thích cơ chế).

### Bước 10 — Hiển thị kết quả + Refinement loop

- `render_charts()`: hiện ảnh + caption.
- `_render_refinement_box()`: user góp ý → gộp `summary + insights` lần trước + góp ý mới vào `user_query` → `EDAAgent.run()` lại từ đầu (qua hết bước 1-9), không cần confirm lại.

---

## Bảng tool có sẵn (`TOOL_REGISTRY`)

| Nhóm | Tool |
|---|---|
| Chất lượng dữ liệu | `check_missing`, `check_duplicates`, `check_outliers_iqr`, `check_outliers_rolling`*, `check_type_mismatch` |
| Univariate | `basic_stats`, `skewness_kurtosis`, `normality_test`, `plot_distribution`, `plot_violin`, `plot_boxplot` |
| Bivariate | `correlation_matrix` (Pearson), `spearman_correlation`, `plot_scatter`, `plot_boxplot_by`, `group_stats`, `lag_correlation`* |
| Multivariate | `plot_heatmap`, `plot_pairplot` |
| Feature relationship | `mutual_info_scores`, `plot_mi_scores` (cần `target_col`) |
| Time series* | `time_series_decompose`, `hourly_pattern`, `weekly_pattern`, `monthly_pattern`, `plot_time_series`, `plot_seasonal_pattern`, `plot_decomposition` |
| Khác | `plot_missing_heatmap` |

*Yêu cầu `DatetimeIndex` — tự bị skip nếu dataset không có.

---

## Module/lớp — vai trò, vấn đề giải quyết, lợi ích

### Tầng Orchestration

**`EDAAgent`** (`agents/eda_agent.py`)
- **Làm gì:** Lớp điều phối trung tâm — gọi đúng thứ tự tất cả module khác, gộp kết quả Phase 1 + Phase 2, quản lý guard runtime (`_normalize_params`, `DATETIME_REQUIRED_TOOLS`, `DISTRIBUTION_SHAPE_TOOLS`), tự gắn caption (`_make_caption`) và significance score (`_auto_score`) sau mỗi tool.
- **Vấn đề giải quyết:** Nếu để LLM tự quyết định toàn bộ luồng (kể cả việc nào chắc chắn nên làm), hệ thống vừa chậm vừa dễ sai do phụ thuộc hoàn toàn vào 1 lần sinh JSON của LLM. `EDAAgent` tách rõ "việc gì luôn đúng, làm cứng" (Phase 1) khỏi "việc gì cần suy luận, để LLM" (Phase 2).
- **Lợi ích:** Một nơi duy nhất kiểm soát toàn bộ pipeline → dễ thêm guard mới, dễ debug khi có lỗi (log ghi rõ step nào skip/lỗi và tại sao), không phải sửa nhiều module rải rác khi cần chặn 1 lỗi LLM.

### Tầng Input/Detection

**`file_detector`** (`agents/file_detector.py`)
- **Làm gì:** Đọc schema từng file upload, gọi `schema_analyzer` tìm cột chung/cột thời gian giữa các file, LLM diễn giải merge plan bằng tiếng Việt dễ hiểu.
- **Vấn đề giải quyết:** User không phải dân kỹ thuật thường không biết 2 file có ghép được không, ghép theo cột nào, có cần resample không.
- **Lợi ích:** Tự động phát hiện + giải thích bằng lời thường trước khi hỏi user xác nhận — đúng tinh thần human-in-the-loop, không âm thầm tự quyết.

**`schema_analyzer`** (`tools/schema_analyzer.py`)
- **Làm gì:** `detect_datetime_columns()` (chỉ xét cột không phải dạng số — tránh false positive), `detect_time_frequency()`, `find_join_candidates()`, `suggest_merge_plan()`.
- **Vấn đề giải quyết:** Đây là nơi từng có bug nghiêm trọng nhất trong cả session (cột `overtime_hours` bị nhận nhầm là cột thời gian do chứa substring "time", phá hỏng toàn bộ df bằng cách biến nó thành index rồi xóa mất cột). Sau khi thêm điều kiện loại trừ cột số, lớp này là nền tảng đáng tin cậy cho mọi quyết định liên quan thời gian trong toàn hệ thống.
- **Lợi ích:** Một điểm kiểm tra duy nhất cho "đây có phải cột thời gian không" — sửa 1 lần, mọi module dùng lại (`EDAAgent`, `training_agent`, `file_detector`) đều được lợi.

**`file_merger`** (`tools/file_merger.py`)
- **Làm gì:** Thực thi merge plan đã được user đồng ý — resample nếu tần suất khác nhau, join theo đúng cột.
- **Vấn đề giải quyết:** Tách riêng "đề xuất" (file_detector) khỏi "thực thi" (file_merger) — đề xuất có thể bị từ chối, thực thi chỉ chạy khi đã chắc chắn.
- **Lợi ích:** An toàn — không merge nhầm khi user chưa đồng ý.

### Tầng Pre-planning (chạy trước khi LLM lập kế hoạch)

**`profiler`** (`tools/profiler.py`)
- **Làm gì:** Bọc `ydata-profiling` (chạy `minimal=True`, sample tối đa 5000 dòng) — trích alerts, top correlation, cột thiếu nhiều, rút gọn thành vài dòng text.
- **Vấn đề giải quyết:** `ydata-profiling` quét toàn bộ dataset không bỏ sót cột nào (điều LLM dễ bỏ sót khi tự lập kế hoạch), nhưng output gốc quá lớn (500KB-2MB) không thể nhét vào prompt LLM.
- **Lợi ích:** Kết hợp được độ phủ đầy đủ của profiling tự động (deterministic, không bao giờ crash do LLM sinh sai param) với chi phí token thấp — chỉ truyền phần đã rút gọn cho Self-Generating Questions.

**`hypothesis_generator`** (`agents/hypothesis_generator.py`)
- **Làm gì:** Sinh 2-3 giả thuyết có thể kiểm chứng, CHỈ khi có domain context thật, bị constrain chỉ theo 2 dạng test được bằng tool sẵn có.
- **Vấn đề giải quyết:** Một bản EDA "chạy hết tool rồi tổng hợp" trông khác hẳn một bản EDA "có giả thuyết khoa học rõ ràng rồi đi kiểm chứng" — module này tạo cấu trúc khoa học cho output. Việc constrain theo khả năng tool giải quyết đúng bug đã gặp: giả thuyết generic thường đòi hỏi phân tích không tool nào làm được (vd chia nhóm theo ngưỡng động), khiến phần kiểm chứng luôn ra "KHÔNG ĐỦ DỮ LIỆU".
- **Lợi ích:** Báo cáo có chiều sâu hơn hẳn — không chỉ "đây là gì" mà còn "giả thuyết X đúng/sai, vì sao".

**`question_generator`** (`agents/question_generator.py`)
- **Làm gì:** Sinh 3-5 câu hỏi phân tích từ schema + profiling context, luôn chạy (không cần domain).
- **Vấn đề giải quyết:** Giải quyết đúng điểm yếu phổ biến nhất của EDA tự động — user không biết nên hỏi gì, nhập query kiểu "phân tích dữ liệu này" thì LLM không có gì để bám, ra kế hoạch generic/lệch trọng tâm.
- **Lợi ích:** Đo được rõ ràng qua test thực tế — cùng 1 dataset, plan tập trung đúng trọng tâm hơn hẳn khi có câu hỏi tự sinh dẫn đường so với khi không có.

### Tầng Planning

**`eda_planner`** (`agents/eda_planner.py` + `llm/prompts/planner_prompt.py`)
- **Làm gì:** LLM (MODEL_70B) nhận toàn bộ context đã chuẩn bị (query enriched, schema, whitelist cột, datetime info, phase1_summary) → sinh danh sách tool call cụ thể.
- **Vấn đề giải quyết:** Đây từng là nguồn gốc của cả 1 lớp bug (tên param sai, bịa tên cột không tồn tại, số bước không kiểm soát) trước khi tối ưu prompt — few-shot example + whitelist cột + ràng buộc số bước + negative instruction giải quyết phần lớn.
- **Lợi ích:** Linh hoạt hơn orchestration cứng (mỗi dataset/câu hỏi có plan riêng, không phải luôn chạy y nguyên 1 chuỗi tool cố định) mà vẫn kiểm soát được bằng prompt + guard ở tầng Execution.

### Tầng Execution / Tool

**`quality_checker`** (`tools/quality_checker.py`)
- **Làm gì:** `check_missing`, `check_duplicates`, `check_outliers_iqr`, `check_outliers_rolling`, `check_type_mismatch`.
- **Vấn đề giải quyết:** Mọi EDA đều cần biết "dữ liệu có sạch không" trước khi tin vào bất kỳ phân tích sâu hơn nào.
- **Lợi ích:** Là 4 tool chạy cứng ở Phase 1 — nền tảng deterministic cho toàn bộ pipeline, không phụ thuộc LLM.

**`stats_engine`** (`tools/stats_engine.py`)
- **Làm gì:** Thống kê mô tả (`basic_stats`, `skewness_kurtosis`), tương quan (Pearson, Spearman), kiểm định phân phối chuẩn (`normality_test`), thống kê theo nhóm (`group_stats`), và toàn bộ nhóm time series (`time_series_decompose`, `hourly/weekly/monthly_pattern`, `lag_correlation`).
- **Vấn đề giải quyết:** Cung cấp đủ độ sâu cho cả 3 tầng Univariate/Bivariate/Multivariate — ban đầu chỉ có Pearson correlation (bỏ sót quan hệ non-linear, nhạy outlier), giờ có thêm Spearman + group comparison.
- **Lợi ích:** Tách hoàn toàn tính toán khỏi việc vẽ biểu đồ (`viz_engine` gọi lại các hàm ở đây) — không trùng lặp logic.

**`viz_engine`** (`tools/viz_engine.py`)
- **Làm gì:** Toàn bộ hàm `plot_*` — sinh PNG, trả về path.
- **Vấn đề giải quyết:** Biểu đồ là cách nhanh nhất để người không biết kỹ thuật hiểu dữ liệu — số liệu thô khó cảm nhận quy mô/pattern bằng hình ảnh.
- **Lợi ích:** Đa dạng đủ cho từng mục đích (distribution, violin, boxplot, boxplot_by nhóm, scatter, heatmap, pairplot, decomposition, seasonal pattern) — không phải chỉ có 1-2 loại chart dùng cho mọi trường hợp.

**`relationship`** (`tools/relationship.py`)
- **Làm gì:** `mutual_info_scores()` — đo quan hệ phi tuyến giữa feature và target bằng Mutual Information (sklearn), không giả định tuyến tính như Pearson.
- **Vấn đề giải quyết:** Pearson correlation bỏ sót quan hệ dạng U/non-linear (vd nhiệt độ vs phụ tải: cả nóng lẫn lạnh đều làm tăng tải, Pearson gần 0 dù quan hệ thực tế rất mạnh).
- **Lợi ích:** Trả lời trực tiếp câu hỏi "feature nào quan trọng nhất với target" — verify bằng ground truth thực nghiệm cho kết quả đúng (feature có quan hệ thật được xếp hạng cao nhất).

**`scorer`** (`tools/scorer.py`)
- **Làm gì:** `score_trend` (Kendall tau), `score_pearson` (p-value tương quan), `score_group_diff` (Kruskal-Wallis) — gắn ý nghĩa thống kê vào kết quả tool khác.
- **Vấn đề giải quyết:** Không có p-value, insight chỉ có thể nói "có vẻ khác nhau" — không phân biệt được khác biệt thật với nhiễu ngẫu nhiên.
- **Lợi ích:** Insight có cơ sở thống kê thật — và quan trọng là báo cáo trung thực cả khi KHÔNG có ý nghĩa thống kê (đã verify: Kruskal-Wallis p=0.66 được báo đúng là "không khác biệt", không bị thiên vị về phía kết quả "đẹp").

### Tầng Output

**`insight_generator`** (`agents/insight_generator.py` + `llm/prompts/insight_prompt.py`)
- **Làm gì:** LLM diễn giải toàn bộ `results` thành tiếng Việt tự nhiên, theo domain (hoặc `DOMAIN_GENERIC` nếu không có), kèm section kiểm chứng giả thuyết nếu có.
- **Vấn đề giải quyết:** Đây là nơi trực tiếp quyết định EDA có "dùng được cho người không biết code" hay không — ban đầu insight đầy số liệu khô (`std=77453.92, p25=17314.0`) không khác gì đọc thẳng JSON kết quả tool.
- **Lợi ích:** Sau khi sửa prompt (lời thường dẫn trước, số liệu minh chứng trong ngoặc, cấm ký hiệu kiểu code, chỉ chọn 1-2 quan hệ mạnh nhất để giải thích sâu thay vì liệt kê hết) — output đọc như người thật giải thích, không như báo cáo thống kê.

---

## Ưu điểm tổng thể của module EDA

1. **Không phụ thuộc hoàn toàn vào 1 lần LLM gọi đúng.** Phase 1 + trigger rules + 3 guard runtime đảm bảo pipeline luôn có tối thiểu 1 bộ phân tích đáng tin cậy (chất lượng dữ liệu, multivariate overview) dù LLM ở Phase 2 có sinh plan tệ thế nào.
2. **Tổng quát hóa được mọi domain**, không hardcode riêng cho 1 ngành — đã verify bằng 2 dataset hoàn toàn khác nhau (retail, HR) ngoài dataset điện lực gốc, tìm và fix được nhiều bug chỉ lộ ra khi đổi domain.
3. **Có cơ sở thống kê, không chỉ là LLM "đoán".** Mọi insight quan trọng đều có thể truy ngược về 1 con số/kiểm định cụ thể trong `results`, không phải LLM tự bịa nhận xét.
4. **Đọc được bởi người không biết kỹ thuật** — đúng mục tiêu no-code/low-code của đề tài, không phải báo cáo thống kê đòi hỏi nền tảng chuyên môn để hiểu.
5. **Dễ mở rộng có kiểm soát.** Thêm tool mới chỉ cần đăng ký vào `TOOL_REGISTRY` + khai báo trong prompt — không phải sửa logic orchestration; thêm guard mới chỉ cần thêm 1 set + 1 check trong `execute_plan()`.

---

## Nguyên tắc thiết kế

1. **Deterministic trước, LLM sau.** Mọi việc có thể làm chắc chắn (quality check, trigger rule, profiling, guard) đều chạy không qua LLM. LLM chỉ dùng cho việc cần suy luận ngữ nghĩa (lập plan, sinh câu hỏi/giả thuyết, viết insight).
2. **Không tin LLM tuân thủ 100% prompt.** Mọi ràng buộc quan trọng (DatetimeIndex, cardinality cột, tên tool/param hợp lệ) đều có **guard runtime** kiểm tra lại, không chỉ dựa vào hướng dẫn trong prompt.
3. **Giả thuyết/câu hỏi phải khớp khả năng tool.** Hypothesis Generation bị constrain chỉ sinh điều test được bằng tool sẵn có — tránh sinh ra thứ không bao giờ kiểm chứng được.
4. **Số liệu là minh chứng, không phải nội dung chính.** Insight viết theo lời thường tự nhiên trước, số liệu hỗ trợ trong ngoặc — phục vụ người dùng no-code/low-code.

## Hạn chế đã biết

- LLM planner không tuân thủ 100% — vd Hypothesis test đạt ~2/3 trong thực nghiệm, không đảm bảo mọi giả thuyết đều được kiểm chứng đủ.
- Mỗi lần chạy EDA tốn tối thiểu 4 LLM call (questions, hypotheses, planner, insight) — latency/cost cao hơn flow tối giản.
- `mutual_info_scores`/`plot_mi_scores` hiếm khi được planner tự chọn dù query rất rõ về target — do LLM thường ưu tiên `group_stats`/`correlation_matrix` quen thuộc hơn.
