"""Upload file CSV/Excel (data) và file nghiệp vụ (Word/txt)."""

import pandas as pd
import streamlit as st

MAX_FILES = 5


def _fix_longitude(df):
    """Fix bug longitude dạng '1.071.667' -> 107.1667 (xem DATASET.md)."""
    if "longitude" in df.columns and df["longitude"].dtype == object:
        df["longitude"] = df["longitude"].astype(str).str.replace(".", "", 1).astype(float) / 10
    return df


def render_data_uploader():
    """Upload tối đa 5 file CSV/Excel, trả về dict[filename] = DataFrame."""
    files = st.file_uploader(
        "Upload file dữ liệu (CSV/Excel, tối đa 5 file)",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
    )

    if not files:
        return {}

    if len(files) > MAX_FILES:
        st.error(f"Chỉ được upload tối đa {MAX_FILES} file. Đã chọn {len(files)} file.")
        files = files[:MAX_FILES]

    dataframes = {}
    for f in files:
        if f.name.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(f)
        else:
            df = pd.read_csv(f)
        df = _fix_longitude(df)
        dataframes[f.name] = df

    return dataframes


def render_test_uploader():
    """Upload 1 file CSV/Excel làm dữ liệu test cho bước đánh giá (optional), trả về DataFrame hoặc None."""
    f = st.file_uploader(
        "Upload file test để đánh giá (CSV/Excel, không bắt buộc — nếu để trống sẽ dùng lại dữ liệu huấn luyện)",
        type=["csv", "xlsx", "xls"],
    )

    if f is None:
        return None

    if f.name.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(f)
    else:
        df = pd.read_csv(f)
    return _fix_longitude(df)


def render_domain_uploader():
    """Upload file nghiệp vụ Word/txt (optional), trả về nội dung text."""
    f = st.file_uploader("Upload file nghiệp vụ (Word/txt, không bắt buộc)", type=["docx", "txt"])

    if f is None:
        return ""

    if f.name.lower().endswith(".docx"):
        import docx
        document = docx.Document(f)
        return "\n".join(p.text for p in document.paragraphs)

    return f.read().decode("utf-8")
