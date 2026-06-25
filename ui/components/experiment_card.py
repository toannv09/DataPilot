"""Card hiển thị thông tin experiment/bài toán."""

import streamlit as st


def render_card(title, description, button_label="Chọn", key=None):
    """Hiển thị 1 card với tiêu đề, mô tả và nút bấm. Trả về True nếu nút được bấm."""
    with st.container(border=True):
        st.subheader(title)
        st.write(description)
        return st.button(button_label, key=key)
