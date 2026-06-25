# AutoEDA — Tự động khám phá dữ liệu và phát triển mô hình học máy

## Mô tả

Prototype rút gọn của **VMLP (Viettel ML Platform)** với AI agent bổ sung vào module Khám phá dữ liệu. Người dùng tạo bài toán, chọn loại experiment, agent tự động phân tích và trả về insight tiếng Việt.

Đây là đề tài **107 — VDT 2026**, tập trung vào AutoEDA trong bộ 4 module (AutoEDA, Feature Engineering, AutoML, XAI).

## Input / Output

| | Mô tả |
|---|---|
| **Input** | File CSV/Excel (tối đa 5 file) + file nghiệp vụ Word/txt (optional) + câu hỏi tiếng Việt |
| **Output** | Biểu đồ thống kê + nhận xét tiếng Việt + gợi ý bước tiếp + báo cáo EDA PDF/HTML + baseline ML (optional) |

## Tài liệu

| File | Dùng khi nào |
|------|-------------|
| `README.md` | Đọc đầu tiên, tổng quan project |
| `REQUIREMENTS.md` | Không biết cần làm gì, check scope và đầu ra |
| `ARCHITECTURE.md` | Thiết kế cấu trúc thư mục, viết code mới |
| `FLOW.md` | Implement agent, không biết bước nào gọi gì |
| `TOOLS.md` | Viết tool library, tra function signature |
| `PROMPTS.md` | Viết prompt cho từng agent |
| `DATASET.md` | Làm việc với dataset điện lực |
| `METRICS.md` | Viết eval script, đầu ra số 3 |
| `ROADMAP.md` | Không biết làm gì tiếp theo, check checklist |

## 6 loại experiment template

| Template | Agent | Mức độ |
|----------|-------|--------|
| Khám phá dữ liệu | `eda_agent` | Làm kỹ — core của project |
| Xử lý dữ liệu | `preprocessing_agent` | Cơ bản |
| Huấn luyện mô hình | `training_agent` | Cơ bản |
| Đánh giá mô hình | `evaluation_agent` | Cơ bản |
| Suy luận mô hình | `inference_agent` | Cơ bản |
| Tùy chỉnh | Không có agent | User tự nhập |
| Full Pipeline | `pipeline_agent` | Gọi tuần tự EDA→Xử lý→Train→Đánh giá |

## Tech stack

| Layer | Công nghệ |
|-------|-----------|
| UI | Streamlit |
| Agent | LangChain |
| LLM | Groq API — Llama 3.3 70B / 3.1 8B |
| Data processing | Pandas, NumPy |
| EDA | ydata-profiling |
| ML | Scikit-learn, XGBoost |
| Visualization | Matplotlib, Seaborn |
| Backend API | FastAPI |
| MLOps | Weights & Biases, Docker Compose |
| Report | WeasyPrint (PDF), Jinja2 (HTML) |

## Chạy project

```bash
docker-compose up --build
# Mở http://localhost:8501
```