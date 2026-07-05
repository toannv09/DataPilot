"""Upload file CSV/Excel (data) và file nghiệp vụ (Word/txt) — tương đương ui/components/file_uploader.py.

Giao diện nâng cấp: dropzone viền đứt tự custom (overlay 1 `ui.upload()` trong suốt lên trên
để vẫn dùng cơ chế upload thật của NiceGUI, chỉ thay giao diện hiển thị) + danh sách file sau
khi upload (icon, tên, dung lượng, số dòng×cột, nút xóa) tự vẽ — không dùng list mặc định
của QUploader.
"""

import io

import pandas as pd
from nicegui import events, run as nicegui_run, ui

from llm.client import MODEL_LITE, call_llm

MAX_FILES = 5
MAX_SIZE_MB = 50
DOMAIN_SUMMARIZE_THRESHOLD = 1500

DROPZONE_CSS = """
.aeda-upload-wrap:hover .aeda-dropzone { border-color: #EE0033 !important; background: #fff8f9 !important; }
.aeda-upload-wrap:hover .aeda-dropzone-icon { color: #EE0033 !important; }
"""


def _fix_longitude(df):
    """Fix bug longitude dạng '1.071.667' -> 107.1667 (xem DATASET.md)."""
    if "longitude" in df.columns and df["longitude"].dtype == object:
        df["longitude"] = df["longitude"].astype(str).str.replace(".", "", 1).astype(float) / 10
    return df


def _read_tabular(name, content_bytes):
    buf = io.BytesIO(content_bytes)
    if name.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(buf)
    else:
        df = pd.read_csv(buf)
    return _fix_longitude(df)


def _format_size(n_bytes):
    if n_bytes < 1024 * 1024:
        return f"{n_bytes / 1024:.0f} KB"
    return f"{n_bytes / 1024 / 1024:.1f} MB"


def _render_dropzone(icon, title, subtitle, badge_text, on_upload, accept, multiple=False):
    """Vùng kéo-thả viền đứt — overlay 1 ui.upload() ẩn (opacity 0) lên trên vùng hiển thị
    custom, để giữ đúng cơ chế upload thật nhưng tự vẽ giao diện theo ý muốn.
    """
    ui.add_css(DROPZONE_CSS)
    with ui.column().classes("aeda-upload-wrap relative w-full gap-0"):
        with ui.column().classes("aeda-dropzone items-center justify-center w-full gap-1").style(
            "border: 1.5px dashed rgba(0,0,0,0.15); border-radius: 9px; padding: 20px 16px; "
            "background: #fafafa; text-align:center; transition: border-color .15s, background .15s;"
        ):
            ui.icon(icon, color="grey-5").classes("aeda-dropzone-icon").style(
                "font-size: 26px; transition: color .15s;"
            )
            ui.label(title).classes("text-sm font-medium text-gray-600")
            ui.label(subtitle).classes("text-xs text-gray-400")
            if badge_text:
                ui.label(badge_text).classes("text-xs text-gray-500 mt-1").style(
                    "background:#F1EFE8; border-radius:4px; padding:2px 8px;"
                )
        upload_el = ui.upload(on_upload=on_upload, multiple=multiple, auto_upload=True).props(
            f'accept="{accept}"'
        ).classes("absolute top-0 left-0 w-full h-full opacity-0 cursor-pointer")

        # Vùng bấm thật của QUploader (nút "+") không phủ hết cả khối -> bấm ở phần lớn diện
        # tích sẽ không mở được file picker (chỉ kéo-thả là ăn vì nó nhận trên toàn vùng).
        # Gắn thêm click handler JS bấm trực tiếp vào <input type=file> ẩn bên trong để đảm
        # bảo bấm bất kỳ đâu trong dropzone đều mở được file picker.
        upload_el.on(
            "click",
            js_handler=f"""() => {{
                const el = getHtmlElement({upload_el.id});
                const input = el.querySelector('input[type=file]');
                if (input) input.click();
            }}""",
        )


def _render_file_row(name, size_bytes, shape, on_remove):
    with ui.row().classes("items-center gap-2 w-full no-wrap").style(
        "background:#F7F7F8; border:0.5px solid rgba(0,0,0,0.09); border-radius:7px; padding:7px 10px;"
    ):
        ui.icon("description", color="#EE0033").style("font-size: 16px;")
        with ui.column().classes("gap-0 flex-grow"):
            ui.label(name).classes("text-sm font-medium")
            meta = _format_size(size_bytes)
            if shape:
                meta += f" · {shape[0]:,} dòng × {shape[1]} cột"
            ui.label(meta).classes("text-xs text-gray-400")
        ui.button(icon="close", on_click=on_remove, color="grey-5").props("flat round dense size=sm")


def render_data_uploader(files, on_change=None):
    """Upload tối đa MAX_FILES file CSV/Excel — mỗi file xong tự thêm vào `files` (dict).

    on_change: callback() gọi lại mỗi khi `files` thay đổi (thêm HOẶC xóa) — để UI khác như
    dropdown cột tự refresh.

    Trả về `rebuild_list` — nếu code gọi nơi khác xoá file trực tiếp khỏi `files` (vd chip xoá
    nhanh ở thanh chat `chat_experiment.py`, nằm ngoài uploader này), gọi lại hàm này để danh
    sách hiển thị bên trong uploader (vd trong dialog) không bị "vẫn thấy file đã xoá" khi mở lại.
    """
    meta = {}  # filename -> {"size": int} — chỉ phục vụ hiển thị, KHÔNG nằm trong `files` công khai
    list_container = ui.column().classes("w-full gap-1 mt-2")

    def rebuild_list():
        list_container.clear()
        with list_container:
            for name, df in files.items():
                def remove(name=name):
                    files.pop(name, None)
                    meta.pop(name, None)
                    rebuild_list()
                    if on_change:
                        on_change()

                _render_file_row(name, meta.get(name, {}).get("size", 0), df.shape, remove)

    async def handle_upload(e: events.UploadEventArguments):
        if len(files) >= MAX_FILES:
            ui.notify(f"Chỉ được upload tối đa {MAX_FILES} file.", color="negative")
            return
        name = e.file.name
        content = await e.file.read()
        df = _read_tabular(name, content)
        files[name] = df
        meta[name] = {"size": len(content)}
        rebuild_list()
        ui.notify(f"Đã upload {name} ({len(df)} dòng × {len(df.columns)} cột)", color="positive")
        if on_change:
            on_change()

    _render_dropzone(
        "upload_file",
        "Kéo thả hoặc bấm để chọn file",
        "Hỗ trợ .csv · .xlsx · .xls",
        f"Tối đa {MAX_FILES} file · {MAX_SIZE_MB}MB/file",
        handle_upload,
        ".csv,.xlsx,.xls",
        multiple=True,
    )
    rebuild_list()
    return rebuild_list


def render_test_uploader(on_change=None):
    """Upload 1 file CSV/Excel làm dữ liệu test (optional). Trả về box {"df": None|DataFrame}."""
    box = {"df": None, "name": None, "size": 0}
    list_container = ui.column().classes("w-full gap-1 mt-2")

    def rebuild_list():
        list_container.clear()
        if box["df"] is not None:
            with list_container:
                def remove():
                    box["df"] = None
                    rebuild_list()
                    if on_change:
                        on_change()

                _render_file_row(box["name"], box["size"], box["df"].shape, remove)

    async def handle_upload(e: events.UploadEventArguments):
        name = e.file.name
        content = await e.file.read()
        box["df"] = _read_tabular(name, content)
        box["name"] = name
        box["size"] = len(content)
        rebuild_list()
        ui.notify(f"Đã upload file test: {name}", color="positive")
        if on_change:
            on_change()

    _render_dropzone(
        "fact_check",
        "Chọn file test (.csv / .xlsx)",
        "Không có thì dùng phần split từ dữ liệu chính",
        None,
        handle_upload,
        ".csv,.xlsx,.xls",
    )
    rebuild_list()
    return box


def render_model_uploader(model_path_box, model_dir, on_change=None):
    """Upload 1 file model .pkl — ghi đè model_path_box["value"] (ưu tiên hơn model chọn sẵn).

    Trả về `rebuild_list` — cùng lý do với `render_data_uploader`/`render_domain_uploader`: nếu
    code ngoài xoá model trực tiếp khỏi `model_path_box`, gọi lại hàm này để đồng bộ hiển thị.
    """
    import os

    list_container = ui.column().classes("w-full gap-1 mt-2")

    def rebuild_list():
        list_container.clear()
        name = model_path_box.get("uploaded_name")
        if name:
            with list_container:
                def remove():
                    model_path_box["uploaded_name"] = None
                    model_path_box["value"] = model_path_box.get("fallback_value")
                    rebuild_list()
                    if on_change:
                        on_change()

                _render_file_row(name, model_path_box.get("uploaded_size", 0), None, remove)

    async def handle_upload(e: events.UploadEventArguments):
        os.makedirs(model_dir, exist_ok=True)
        name = e.file.name
        content = await e.file.read()
        path = os.path.join(model_dir, name)
        with open(path, "wb") as f:
            f.write(content)
        model_path_box["value"] = path
        model_path_box["uploaded_name"] = name
        model_path_box["uploaded_size"] = len(content)
        rebuild_list()
        ui.notify(f"Đã upload model: {name} (ưu tiên hơn model chọn ở trên)", color="positive")
        if on_change:
            on_change()

    _render_dropzone(
        "model_training",
        "Hoặc upload model (.pkl)",
        "Ưu tiên hơn model chọn từ danh sách có sẵn ở trên",
        None,
        handle_upload,
        ".pkl",
    )
    rebuild_list()
    return rebuild_list


def render_domain_uploader(on_change=None, initial_text="", initial_name=None):
    """Upload file nghiệp vụ Word/txt (optional). Trả về box {"text": str, ..., "_refresh": fn}.

    initial_text / initial_name: khôi phục state khi uploader được tạo lại (vd navigate về config
    từ màn xác nhận) — hiển thị lại file row và giữ nguyên text đã summarize trước đó.

    `box["_refresh"]` — gọi lại nếu code ngoài (vd chip xoá nhanh ở thanh chat) xoá file qua
    `box["text"]`/`box["name"]` trực tiếp thay vì qua nút xoá nội bộ ở đây, để danh sách hiển thị
    trong uploader (vd trong dialog) đồng bộ lại — cùng lý do với `render_data_uploader`.

    on_change: gọi lại sau khi upload/tóm tắt hoàn tất — với file dài cần summarize, callback được
    gọi SAU khi await xong (box["text"] đã sẵn sàng), không phải ngay lúc upload bắt đầu.
    """
    box = {"text": initial_text or "", "name": initial_name, "size": 0, "summarizing": False, "_active": True}
    list_container = ui.column().classes("w-full gap-1 mt-2")

    def rebuild_list():
        list_container.clear()
        if box.get("name"):
            with list_container:
                if box.get("summarizing"):
                    with ui.row().classes("items-center gap-2 w-full no-wrap").style(
                        "background:#FFF8F0; border:0.5px solid rgba(245,124,0,0.3); "
                        "border-radius:7px; padding:7px 10px;"
                    ):
                        ui.spinner(size="sm").style("color:#F57C00;")
                        ui.label(f"{box['name']} — đang tóm tắt...").classes("text-sm text-gray-500")
                else:
                    def remove():
                        box["text"] = ""
                        box["name"] = None
                        rebuild_list()
                        if on_change:
                            on_change()

                    _render_file_row(box["name"], box["size"], None, remove)

    box["_refresh"] = rebuild_list

    async def handle_upload(e: events.UploadEventArguments):
        name = e.file.name
        content = await e.file.read()
        if name.lower().endswith(".docx"):
            import docx

            document = docx.Document(io.BytesIO(content))
            raw_text = "\n".join(p.text for p in document.paragraphs)
        else:
            raw_text = content.decode("utf-8")

        if len(raw_text) > DOMAIN_SUMMARIZE_THRESHOLD:
            box["name"] = name
            box["size"] = len(content)
            box["text"] = ""
            box["summarizing"] = True
            rebuild_list()
            ui.notify("File nghiệp vụ dài — đang tóm tắt...", color="info")

            def _summarize(text=raw_text):
                return call_llm(
                    f"Tóm tắt nội dung nghiệp vụ sau — giữ lại tên cột, quy tắc nghiệp vụ, "
                    f"ngưỡng số liệu, đặc điểm quan trọng. Bỏ phần lặp lại/không cần thiết:\n\n{text}",
                    system="Trả về bản tóm tắt dưới 800 từ, tiếng Việt, không dùng markdown.",
                    model=MODEL_LITE,
                )

            result = await nicegui_run.io_bound(_summarize)
            if not box.get("_active"):
                return
            box["text"] = result
            box["summarizing"] = False
            rebuild_list()
            if on_change:
                on_change()
            ui.notify(f"Đã tóm tắt xong: {name}", color="positive")
        else:
            box["text"] = raw_text
            box["name"] = name
            box["size"] = len(content)
            rebuild_list()
            if on_change:
                on_change()
            ui.notify(f"Đã upload file nghiệp vụ: {name}", color="positive")

    _render_dropzone(
        "file_present",
        "Chọn file .docx hoặc .txt",
        "Không có thì agent tự phân tích chung",
        None,
        handle_upload,
        ".docx,.txt",
    )
    rebuild_list()
    return box
