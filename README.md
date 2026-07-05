# DataPilot

**Hệ thống trợ lý AI hỗ trợ khám phá dữ liệu và phát triển mô hình học máy qua giao tiếp tiếng Việt tự nhiên.**

Người dùng không cần biết lập trình — chỉ cần mô tả yêu cầu, hệ thống tự lập kế hoạch phân tích, thực thi từng bước, sinh insight có kèm kiểm định thống kê và xuất báo cáo bằng tiếng Việt.

> Đề tài 107 — VDT 2026 | Nguyễn Vẹn Toàn | Mentor: Vũ Minh Thư (Viettel Solutions)

<!-- TODO: chèn ảnh home.png (màn hình trang chủ) -->

---

## Mục lục

- [Tổng quan](#tổng-quan)
- [Kiến trúc hệ thống](#kiến-trúc-hệ-thống)
- [Module AutoEDA](#module-autoeda)
- [Tính năng](#tính-năng)
- [Kết quả đo thực tế](#kết-quả-đo-thực-tế)
- [Tech stack](#tech-stack)
- [Cấu trúc project](#cấu-trúc-project)
- [Cài đặt và chạy](#cài-đặt-và-chạy)

---

## Tổng quan

Quá trình phân tích dữ liệu và xây dựng mô hình học máy hiện vẫn mang tính thủ công cao, phụ thuộc nhiều vào kinh nghiệm của kỹ sư AI. Người dùng không có nền lập trình gần như không thể tự thực hiện, và mỗi bài toán mới lại phải bắt đầu lại từ đầu.

**DataPilot** giải quyết vấn đề này bằng cách:
- Giao tiếp hoàn toàn bằng tiếng Việt tự nhiên — không cần biết code
- Tự phát hiện schema, chất lượng dữ liệu, đề xuất câu hỏi phân tích
- Tự lập kế hoạch và thực thi từng bước phân tích, có ghi log lại
- Sinh insight kèm kiểm định thống kê (không chỉ nhận xét định tính)
- Cho phép người dùng góp ý để hệ thống tinh chỉnh — không phải hộp đen

---

## Kiến trúc hệ thống

<!-- TODO: chèn Hình 1 — Kiến trúc tổng thể DataPilot (sơ đồ 4 tầng) -->

Hệ thống được tổ chức theo 4 tầng tách biệt:

| Tầng | Thành phần | Vai trò |
|---|---|---|
| **Giao diện** | NiceGUI + chatbot dẫn dắt | 6 loại nghiệp vụ, form config + chatbot |
| **Điều phối** | Router + các agent chuyên biệt | Mỗi agent đảm nhận một nghiệp vụ |
| **Xử lý** | `tools/` (data) tách với `llm/` (LLM) | Thay LLM không ảnh hưởng logic nghiệp vụ |
| **MLOps** | FastAPI + W&B + JSON execution log | Theo dõi token, log từng bước thực thi |

Quy trình chung: người dùng tải file → hệ thống tự phát hiện schema, gợi ý join key nếu nhiều file → agent lập kế hoạch và thực thi từng bước → sinh nhận xét, báo cáo tiếng Việt → người dùng góp ý → hệ thống lập lại kế hoạch trên cùng ngữ cảnh (refinement loop).

---

## Module AutoEDA

Trọng tâm kỹ thuật của đề tài. Thiết kế theo nguyên tắc **"Deterministic trước, LLM sau"**.

<!-- TODO: chèn Hình 2 — Luồng xử lý AutoEDA 2 giai đoạn (Phase 1 → Sinh giả thuyết → Phase 2 → Insight, có vòng refinement) -->

### Phase 1 — Deterministic (luôn chạy, không phụ thuộc LLM)

- Kiểm tra chất lượng dữ liệu: missing values, duplicates, sai kiểu dữ liệu, ngoại lai
- Profiling thống kê toàn bộ cột (min/max/mean/std, phân phối, cardinality)
- Chấm điểm tự động: Kendall's tau (xu hướng), hệ số tương quan + p-value, Kruskal-Wallis (khác biệt nhóm), Mutual Information (quan hệ phi tuyến)
- Trigger rule theo ngưỡng: tự động kích hoạt thêm các bước phân tích khi phát hiện tín hiệu bất thường

### Phase 2 — LLM Planning

- Tự sinh câu hỏi phân tích dựa trên schema và kết quả Phase 1 — giải quyết rào cản "không biết bắt đầu từ đâu" của người dùng không chuyên
- Sinh giả thuyết domain-aware: chỉ đề xuất giả thuyết nằm trong khả năng kiểm chứng của các tool sẵn có
- LLM **chọn tool từ registry đã kiểm chứng** (không tự sinh code tuỳ ý) — giảm rủi ro tạo thao tác sai
- Guard runtime nhiều lớp: bỏ qua tool không phù hợp schema (DatetimeIndex required, cột quá ít giá trị), chặn chart trùng lặp, retry khi tool lỗi
- Kiểm chứng giả thuyết bằng số liệu thực: kết luận **xác nhận / bác bỏ / không đủ bằng chứng** — không chỉ confirm theo kỳ vọng ban đầu

<!-- TODO: chèn ảnh result_1.png (kế hoạch phân tích + Phase 1 metrics tự động) -->

### Refinement loop

Sau mỗi phiên, người dùng có thể góp ý bằng ngôn ngữ tự nhiên. Planner sẽ lập lại kế hoạch trên cùng ngữ cảnh, bổ sung các bước còn thiếu mà không chạy lại từ đầu.

---

## Tính năng

Hệ thống hỗ trợ 6 loại nghiệp vụ, giao tiếp qua form cấu hình hoặc chatbot dẫn dắt:

| Nghiệp vụ | Mô tả | Chatbot |
|---|---|---|
| **Khám phá dữ liệu (AutoEDA)** | Phân tích chất lượng, sinh insight, kiểm chứng giả thuyết | ✅ |
| **Tiền xử lý** | Xử lý missing, outlier, encoding, scaling | ✅ |
| **Huấn luyện mô hình** | Tự chọn và train baseline model phù hợp bài toán | ✅ |
| **Đánh giá mô hình** | Báo cáo metrics, so sánh model | ✅ |
| **Suy luận** | Dự đoán trên dữ liệu mới từ model đã lưu | ✅ |
| **Full pipeline** | Chạy liên tiếp EDA → preprocessing → training → evaluation | Form only |

Tính năng bổ trợ:
- **Xuất mã nguồn**: tái tạo đúng các bước đã thực thi từ execution log
- **Xuất báo cáo**: PDF (WeasyPrint) hoặc HTML (Jinja2) với biểu đồ nhúng trực tiếp
- **Đa lĩnh vực**: kiểm chứng trên điện lực, bán lẻ, nhân sự — không hardcode cho một domain

---

## Kết quả đo thực tế

Đo trên dữ liệu thật, không phải mô phỏng.

### Độ ổn định vận hành (Execution Pass Rate)

Tính từ **114 phiên chạy thật** (26/6–2/7/2026, gộp cả 6 nghiệp vụ, giai đoạn kiến trúc ổn định):

| Chỉ số | Giá trị |
|---|---|
| Tổng bước thực thi | 1.547 |
| Bước thành công | 1.530 |
| **Pass rate cấp độ bước** | **98,9%** |
| Phiên không có lỗi nào | 89/114 (**78,1%**) |

Toàn bộ 17 lỗi có cùng nguyên nhân: LLM planner tham chiếu tên cột dẫn xuất chưa tồn tại trong schema (`day_type`, `is_weekend`, `is_summer`) — đây là failure mode đã xác định, hướng cải tiến tiếp theo.

### Chi phí vận hành (Token Consumption)

Đo trên **20 phiên EDA thật** (cùng bộ dữ liệu phụ tải điện, 3 lượt gọi LLM/phiên):

| Chỉ số | Giá trị |
|---|---|
| 19/20 phiên thông thường | 8.332 – 10.734 token |
| **Trung bình** | **~9.425 token/phiên** |
| 1/20 phiên ngoại lệ | 112.675 token (kế hoạch 18 bước thay vì ~13) |
| Chi phí ước tính (gpt-4o-mini) | ~$0,001 – $0,003/phiên |

Phân phối ổn định qua các lần đo (dao động 9.385–9.464 token), chi phí không phụ thuộc nhiều vào nội dung câu hỏi cụ thể.

### Độ đầy đủ phân tích (EDA Completeness)

Trong checklist 8 hạng mục của một báo cáo EDA đầy đủ, **5/8 mục được đảm bảo cứng bởi kiến trúc** (Phase 1 + trigger rules) — không phụ thuộc LLM có lập kế hoạch đúng hay không. 3 mục còn lại (pattern thời gian, nhận xét, gợi ý bước tiếp theo) phụ thuộc Phase 2.

### Kiểm chứng giả thuyết

<!-- TODO: chèn ảnh result_5.png (kết quả kiểm chứng H1/H2/H3) -->

Trên bộ dữ liệu phụ tải điện Việt Nam (75.841 dòng × 4 cột), agent tự sinh 3 giả thuyết và kiểm chứng bằng số liệu thực:

- **H1** — Phụ tải hệ thống tương quan mạnh với miền Bắc: **Xác nhận** (r = 0,943)
- **H2** — Bắc–Nam đồng pha trong giờ cao điểm: **Chưa đủ bằng chứng** theo đúng khung giờ giả thuyết đặt ra
- **H3** — Bắc–Trung tương quan thuận theo thời gian: **Xác nhận** (r ≈ 0,779)

H2 không được xác nhận mù quáng — đây là minh chứng trực tiếp cho thiết kế kiểm chứng trung thực, không phải LLM chỉ confirm theo kỳ vọng.

---

## Tech stack

| Nhóm | Công nghệ |
|---|---|
| LLM | OpenAI API (gpt-4o-mini) |
| Dữ liệu & profiling | Pandas, NumPy, ydata-profiling, statsmodels |
| Trực quan hoá | Matplotlib, Seaborn |
| Học máy | scikit-learn, XGBoost |
| Giao diện | NiceGUI |
| Backend | FastAPI + Uvicorn |
| MLOps | Weights & Biases (token tracking), JSON execution log |
| Báo cáo | WeasyPrint (PDF), Jinja2 + Markdown (HTML) |
| Deploy | Docker Compose |

---

## Cấu trúc project

```
DataPilot/
├── agents/                  # Agent chuyên biệt cho từng nghiệp vụ
│   ├── base_agent.py        # Base class, ExperimentContext
│   ├── router.py            # Điều phối yêu cầu đến đúng agent
│   ├── eda_agent.py         # AutoEDA: Phase 1 + Phase 2
│   ├── eda_planner.py       # LLM planning cho Phase 2
│   ├── hypothesis_generator.py
│   ├── question_generator.py
│   ├── insight_generator.py
│   ├── preprocessing_agent.py
│   ├── training_agent.py
│   ├── evaluation_agent.py
│   ├── inference_agent.py
│   ├── pipeline_agent.py
│   ├── report_generator.py
│   ├── file_detector.py
│   └── code_export.py
│
├── llm/                     # LLM client + prompt templates
│   ├── client.py
│   ├── cache.py
│   └── prompts/
│
├── tools/                   # Tool registry: viz, profiling, stats, ML
│   ├── viz_engine.py
│   ├── profiler.py
│   ├── quality_checker.py
│   ├── schema_analyzer.py
│   ├── stats_engine.py
│   ├── scorer.py
│   ├── relationship.py
│   ├── file_merger.py
│   └── ml/                  # ML pipeline tools
│
├── mlops/                   # Logger, W&B tracker, FastAPI backend
│   ├── logger.py
│   ├── tracker.py
│   └── api/
│
├── ui_nicegui/              # Giao diện NiceGUI
│   ├── app.py
│   ├── views/               # Các trang: home, config, run, report...
│   └── components/          # Reusable widgets
│
├── tests/
├── data/
│   ├── raw/                 # Đặt file dữ liệu đầu vào tại đây
│   ├── processed/           # Output tiền xử lý
│   └── domain/              # File nghiệp vụ (docx, txt)
├── outputs/
│   ├── charts/
│   ├── logs/
│   ├── models/
│   └── reports/
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## Cài đặt và chạy

### Yêu cầu

- Python 3.10+
- OpenAI API key

### Chạy local

```bash
# 1. Clone repo
git clone https://github.com/toannv09/DataPilot.git
cd DataPilot

# 2. Cài dependencies
pip install -r requirements.txt

# 3. Tạo file .env
cp .env.example .env
# Mở .env, điền OPENAI_API_KEY=sk-...

# 4. Chạy giao diện
python ui_nicegui/app.py
# Mở trình duyệt: http://localhost:8502

# 5. (Tuỳ chọn) Chạy FastAPI backend
uvicorn mlops.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Chạy bằng Docker

```bash
docker compose up
# UI: http://localhost:8502
# API: http://localhost:8000
```

### Chuẩn bị dữ liệu

Đặt file CSV (hoặc Excel) vào `data/raw/`. Hệ thống tự phát hiện schema và kiểu dữ liệu khi upload qua giao diện. Nếu có file nghiệp vụ (mô tả domain, từ điển dữ liệu), đặt vào `data/domain/` — hệ thống sẽ dùng để sinh giả thuyết domain-aware.

---

## Hạn chế

- Mới kiểm chứng trên 3 domain (điện lực, bán lẻ, nhân sự)
- Failure mode chưa có guard: LLM tham chiếu cột dẫn xuất chưa tồn tại (`day_type`, `is_weekend`)
- Đánh giá tính trung thực phân tích mới ở mức định tính trên số ít phiên
- Chưa có phản hồi từ người dùng không chuyên thực tế (đối tượng mục tiêu chính)
- Phụ thuộc OpenAI API — ảnh hưởng độ ổn định khi triển khai thực tế
