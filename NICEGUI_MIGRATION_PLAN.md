# Kế hoạch chuyển UI: Streamlit → NiceGUI

> Lập trước khi bắt đầu đổi UI, để không bỏ sót tính năng đã build và biết rõ thứ tự làm.
> Backend (`agents/`, `tools/`, `llm/`, `mlops/`) **không đổi gì** — chỉ đổi tầng `ui/`.

## Mục tiêu

- Giao diện đẹp/dễ config hơn Streamlit, đổi màu theo brand Viettel (xem `COLOR_GUIDE.md`).
- Có chatbot dạng định hướng (nút bấm gọi hàm có sẵn) qua `ui.chat_message`.
- Giữ nguyên 100% hành vi/tính năng hiện tại — không tính năng nào bị rớt khi port.

## Khác biệt mô hình quan trọng (đọc trước khi viết code)

Streamlit: rerun toàn bộ script mỗi lần tương tác, state nằm trong `st.session_state`.
NiceGUI: build UI 1 lần, **event-driven** — handler tự cập nhật từng phần tử qua reference
(`label.set_text(...)`), không có khái niệm rerun lại từ đầu. Đây là điểm dễ gây bug nhất khi
port (quên cập nhật UI sau khi đổi state, vì không còn "rerun tự vẽ lại hết" như Streamlit).

State tương đương: `st.session_state` → `app.storage.user` (per-browser-session) hoặc biến Python
giữ trong closure của page function (NiceGUI mỗi `@ui.page` tạo 1 scope riêng per client).

## Inventory UI hiện tại

### Trang (`ui/views/`)

| File | Vai trò |
|---|---|
| `home.py` | Danh sách bài toán, nút tạo mới |
| `create_problem.py` | Form tạo bài toán (tên + mô tả) |
| `select_experiment.py` | 5 card template + Full Pipeline |
| `experiment_config.py` | Upload file, domain context, cấu hình ML (task type/target/split/model/optimize) |
| `run_experiment.py` | **Phức tạp nhất** — chat-like flow: confirm input, merge file, chạy agent/pipeline theo stage, refinement box, toast, code-export expander, chart-insight linking |
| `run_history.py` | Danh sách run + log |
| `report.py` | Xem/tải báo cáo HTML/PDF |

### Component (`ui/components/`)

| File | Vai trò |
|---|---|
| `file_uploader.py` | Upload file data/domain/test |
| `chat_box.py` | Chat interface tiếng Việt |
| `chart_viewer.py` | Hiển thị list chart (`{"path","caption"}`) |
| `run_log.py` | Bảng log thực thi |
| `experiment_card.py` | Card chọn template |

### Logic state quan trọng cần port đúng (trong `run_experiment.py`)

- `_split_charts_by_source` / `_render_insight_with_charts` — chèn ảnh theo thẻ `[[chart:ID]]`
  ngay dưới câu insight liên quan, chart "trigger" tách riêng khối "Tổng quan dữ liệu".
- `_render_code_export` — expander "Xem code đã chạy" cho EDA/Preprocessing/Training.
- `_render_stage_refinement_box` / `_render_refinement_box` — góp ý chạy lại đúng 1 stage
  (Full Pipeline) hoặc cả agent (experiment đơn).
- `st.toast` khi refine 1 stage xong — cần map sang `ui.notify`.
- `_render_pipeline` — chạy Full Pipeline theo stage, dừng/tiếp tục giữa các bước.

## Bảng map widget Streamlit → NiceGUI

| Streamlit | NiceGUI tương đương | Lưu ý |
|---|---|---|
| `st.button` | `ui.button` | gắn `on_click=handler` thay vì `if st.button(...):` |
| `st.text_input` / `st.text_area` | `ui.input` / `ui.textarea` | đọc giá trị qua `.value`, không qua return của widget |
| `st.selectbox` | `ui.select` | |
| `st.slider` | `ui.slider` | |
| `st.checkbox` | `ui.checkbox` | |
| `st.file_uploader` | `ui.upload` | callback `on_upload`, khác cách lấy bytes |
| `st.dataframe` | `ui.table` hoặc `ui.aggrid` | `ui.aggrid` mạnh hơn cho bảng lớn |
| `st.image` | `ui.image` | |
| `st.code` | `ui.code` | |
| `st.expander` | `ui.expansion` | |
| `st.toast` | `ui.notify` | |
| `st.spinner` | `ui.spinner` (kèm `await` vì async) | |
| `st.columns` | `ui.row()` / `with ui.row():` | |
| `st.container(border=True)` | `with ui.card():` | |
| `st.session_state` | `app.storage.user` / closure variable | xem mục state phía trên |
| `st.rerun()` | **không cần** | event-driven tự update đúng phần tử |
| `asyncio.run(agent.run(context))` | `await agent.run(context)` trực tiếp | bỏ được hack hiện tại |

## Thứ tự migrate (từ dễ đến khó)

1. `home.py`, `create_problem.py` — đơn giản, ít state.
2. `select_experiment.py`, `experiment_card.py` — card + navigation.
3. `experiment_config.py`, `file_uploader.py` — form + upload.
4. `run_history.py`, `report.py` — đọc/hiển thị dữ liệu có sẵn.
5. `run_experiment.py` + `chart_viewer.py`, `run_log.py`, `chat_box.py` — làm cuối, vì nặng nhất
   và chứa toàn bộ logic stage/refinement/code-export/chart-linking.

Trong lúc làm bước 5, giữ Streamlit (`ui/`) chạy được song song (port `8501`) để so sánh hành vi
trực tiếp — chỉ đổi `docker-compose.yml`/entrypoint sang NiceGUI khi đã verify xong bước 5.

## Checklist verify sau khi port xong (đừng bỏ sót)

- [ ] Upload file CSV/Excel nhiều file → đề xuất merge → chọn merge/không merge
- [ ] Màn xác nhận input trước khi chạy (mọi loại experiment, kể cả Full Pipeline)
- [ ] EDA: chart "Tổng quan dữ liệu" tách riêng, chart trong insight đúng vị trí câu liên quan
- [ ] EDA/Preprocessing/Training: expander "Xem code đã chạy" + nút tải `.py`
- [ ] Full Pipeline: chạy theo stage, "Tiếp tục"/"Dừng tại đây", góp ý refine đúng 1 stage
      (không reset stage khác), toast hiện khi refine xong
- [ ] Preprocessing re-run không bị double-process (bug đã fix ở `pipeline_agent.py`)
- [ ] Run history đọc đúng log theo `run_id`
- [ ] Report HTML/PDF xem + download

## Rollback

Đã `git init` + commit baseline trước khi đổi (xem lịch sử git) — nếu NiceGUI gặp vấn đề giữa
chừng, checkout lại commit này để có Streamlit chạy được ngay, không cần viết lại từ đầu.
