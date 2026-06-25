"""Hiển thị biểu đồ PNG inline, hỗ trợ cả dict {"path":..., "caption":...} và string path."""

import streamlit as st


def render_charts(chart_paths, columns=2):
    """Hiển thị danh sách biểu đồ dạng lưới. Mỗi item có thể là str hoặc dict."""
    if not chart_paths:
        return

    cols = st.columns(columns)
    for i, item in enumerate(chart_paths):
        path = item["path"] if isinstance(item, dict) else item
        caption = item.get("caption", "") if isinstance(item, dict) else ""
        with cols[i % columns]:
            st.image(path)
            if caption:
                st.caption(caption)
