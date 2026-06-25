# Roadmap

**Deadline:** Báo cáo giữa tháng 7. Còn ~3 tuần làm + 1 tuần hoàn thiện.

**Nguyên tắc:** Pipeline chạy được trước → cải thiện sau. Không làm hoàn hảo từ đầu.

---

## Tuần 1 (9–15/6) — Pipeline cơ bản chạy được

**Mục tiêu:** Demo được flow tạo bài toán → chọn EDA → upload → kết quả. Chưa cần thông minh.

- [ ] Setup môi trường, Docker Compose chạy được
- [ ] UI cơ bản: trang chủ + tạo bài toán + chọn 6 template + upload file
- [ ] `schema_analyzer` + `file_merger` — đọc và merge dataset điện lực (hardcode join key trước)
- [ ] `quality_checker` + `stats_engine` — EDA cơ bản chạy được
- [ ] `viz_engine` — 4 loại biểu đồ: distribution, heatmap, time series, boxplot
- [ ] `eda_agent` — orchestration cứng, gọi tool theo thứ tự cố định
- [ ] `insight_generator` — LLM diễn giải kết quả tiếng Việt
- [ ] `router.py` — route đúng agent theo loại experiment chọn
- [ ] `ml/preprocessor` + `ml/trainer` — train được LinearRegression
- [ ] `run_history.py` — hiển thị log lần chạy
- [ ] **Demo end-to-end chạy được trên dataset điện lực**

---

## Tuần 2 (16–22/6) — Agent thông minh hơn + 4 template còn lại

- [ ] `file_detector` — detect join key tự động, không hardcode
- [ ] `eda_planner` — LLM lập kế hoạch EDA theo câu hỏi (thay orchestration cứng)
- [ ] Time series tools: `time_series_decompose`, `hourly_pattern`, `weekly_pattern`
- [ ] Human-in-the-loop: confirm merge plan + confirm bước quan trọng
- [ ] `preprocessing_agent` — xử lý dữ liệu cơ bản
- [ ] `training_agent` — train + leaderboard
- [ ] `evaluation_agent` — metrics + biểu đồ đánh giá
- [ ] `inference_agent` — load model + predict
- [ ] `pipeline_agent` — full pipeline nếu 4 agent trên đã chạy được
- [ ] `llm/cache` — cache output tránh rate limit

---

## Tuần 3 (23–29/6) — Hoàn thiện + Đo metrics

- [ ] `report_generator` — sinh báo cáo PDF/HTML đầy đủ
- [ ] Nhật ký thực thi trong báo cáo
- [ ] Script đo Planning Success Rate, Execution Pass Rate
- [ ] Log Token Consumption, Retry Count vào W&B
- [ ] Test reusability trên ít nhất 2 dataset khác ngoài điện lực
- [ ] UI polish — loading state, tiếng Việt đồng nhất, download báo cáo

---

## Tuần 4 (30/6–5/7) — Báo cáo và trình bày

- [ ] Viết báo cáo kỹ thuật (đầu ra 4)
- [ ] Làm slide — mentor có buổi review chung
- [ ] Chuẩn bị demo script, test không crash
- [ ] Liệt kê hạn chế trong slide

---

## Nếu thiếu thời gian — bỏ theo thứ tự này

1. Prompt robustness test
2. `inference_agent` — suy luận model
3. `evaluation_agent` — đánh giá model
4. Test trên dataset ngoài điện lực

**Không được bỏ:** EDA + insight tiếng Việt + biểu đồ + baseline ML + 6 template UI + demo chạy được