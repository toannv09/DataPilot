# DataPilot

Hệ thống trợ lý AI hỗ trợ khám phá dữ liệu và phát triển mô hình học máy qua giao tiếp tiếng Việt tự nhiên. Người dùng không cần biết lập trình — chỉ cần mô tả yêu cầu, hệ thống tự lập kế hoạch và thực thi phân tích.

<!-- TODO: chèn ảnh home.png (màn hình trang chủ) -->

---

## Tính năng

<!-- TODO: chèn Hình 1 — Kiến trúc tổng thể 4 tầng (UI → Agent → Tools/LLM → MLOps) -->

Hệ thống hỗ trợ 6 loại nghiệp vụ:

| Nghiệp vụ | Mô tả |
|---|---|
| **Khám phá dữ liệu (AutoEDA)** | Tự động phân tích chất lượng, sinh insight, kiểm chứng giả thuyết |
| **Tiền xử lý** | Xử lý missing, outlier, encoding, scaling theo kế hoạch LLM |
| **Huấn luyện mô hình** | Tự chọn và huấn luyện baseline model phù hợp bài toán |
| **Đánh giá mô hình** | Báo cáo metrics, so sánh model |
| **Suy luận** | Dự đoán trên dữ liệu mới từ model đã lưu |
| **Full pipeline** | Chạy liên tiếp từ EDA đến inference |

Giao tiếp qua form cấu hình hoặc **chatbot dẫn dắt** (5/6 nghiệp vụ).

---

## Thiết kế AutoEDA: Deterministic trước, LLM sau

Module trọng tâm của đề tài. Hai giai đoạn tách biệt:

<!-- TODO: chèn Hình 2 — Luồng xử lý AutoEDA 2 giai đoạn (Phase 1 → Sinh giả thuyết → Phase 2 → Insight, có vòng refinement) -->

**Phase 1 — Deterministic:** chạy cứng, không phụ thuộc LLM
- Kiểm tra chất lượng dữ liệu (missing, duplicate, sai kiểu, outlier)
- Profiling thống kê toàn bộ cột
- Chấm điểm tự động: Kendall's tau, p-value, Mutual Information, Kruskal-Wallis

**Phase 2 — LLM planning:** LLM chọn tool từ registry đã kiểm chứng (không tự sinh code)
- Sinh giả thuyết domain-aware → kiểm chứng bằng số liệu thực (xác nhận / bác bỏ / không đủ bằng chứng)
- Guard runtime nhiều lớp: bỏ qua tool không phù hợp schema, chặn chart trùng, retry khi lỗi
- Refinement: người dùng góp ý → planner chạy lại trên cùng ngữ cảnh

<!-- TODO: chèn ảnh report_figures/result_1.png (kế hoạch phân tích + chỉ số Phase 1) -->
<!-- TODO: chèn ảnh report_figures/result_5.png (kết quả kiểm chứng giả thuyết H1/H2/H3) -->

---

## Kết quả đo thực tế

Tính từ 114 phiên chạy thật (26/6–2/7/2026, gộp 6 nghiệp vụ):

- **Execution Pass Rate:** 98,9% (1.530/1.547 bước thành công)
- **Session không lỗi:** 78,1% (89/114 phiên)
- **Token trung bình:** ~9.425 token/phiên EDA (~$0,001–$0,003 với gpt-4o-mini)
- **EDA Completeness:** 5/8 hạng mục đảm bảo cứng bởi kiến trúc

---

## Tech stack

- **LLM:** OpenAI API
- **Data:** Pandas, NumPy, ydata-profiling, statsmodels
- **Viz:** Matplotlib, Seaborn
- **ML:** scikit-learn, XGBoost
- **UI:** NiceGUI
- **Backend:** FastAPI
- **MLOps:** Weights & Biases (token tracking), JSON execution log
- **Report:** WeasyPrint (PDF), Jinja2 (HTML)
- **Deploy:** Docker Compose

---

## Cấu trúc project

```
datapilot/
├── agents/          # Agent chuyên biệt cho từng nghiệp vụ
│   ├── eda_agent.py
│   ├── eda_planner.py
│   ├── hypothesis_generator.py
│   ├── insight_generator.py
│   ├── preprocessing_agent.py
│   ├── training_agent.py
│   └── ...
├── llm/             # LLM client + prompt templates
├── tools/           # Tool registry: viz, profiling, stats, ML
├── mlops/           # Logger, W&B tracker, FastAPI backend
├── ui_nicegui/      # Giao diện NiceGUI + chatbot
├── tests/
├── docker-compose.yml
└── requirements.txt
```

---

## Chạy local

**Yêu cầu:** Python 3.10+, OpenAI API key

```bash
# 1. Cài dependencies
pip install -r requirements.txt

# 2. Tạo file .env
echo "OPENAI_API_KEY=sk-..." > .env

# 3. Chạy UI
python ui_nicegui/app.py
# Mở http://localhost:8502

# 4. (Tuỳ chọn) Chạy backend API
uvicorn mlops.api.main:app --port 8000 --reload
```

**Chạy bằng Docker:**

```bash
docker compose up
```

---

## Demo

<!-- TODO: chèn ảnh report_figures/result_3.png (insight tiếng Việt kèm số liệu) -->
<!-- TODO: chèn ảnh report_figures/result_4.jpg (biểu đồ tự sinh: phụ tải theo thời gian) -->

---

## Đề tài

VDT 2026 — Đề tài 107  
Sinh viên: Nguyễn Vẹn Toàn  
Mentor: Vũ Minh Thư — Viettel Solutions
