"""Chạy experiment — chat interface, hiển thị insight/biểu đồ, human-in-the-loop."""

import asyncio
import os
from datetime import datetime

import pandas as pd
import streamlit as st

from agents import report_generator
from agents.code_export import eda_log_to_code, preprocessing_config_to_code, training_log_to_code
from agents.pipeline_agent import STAGES, PipelineAgent
from agents.router import route
from components.chart_viewer import render_charts
from components.run_log import render_log
from llm.client import MODEL_70B, call_llm
from mlops.logger import ExecutionLogger

_AMBIGUOUS_QUERIES = {"phân tích", "xem", "check", "thử", "xem thử", "phân tích dữ liệu", ""}
EXPERIMENT_TYPE_TO_CODE_KIND = {
    "Khám phá dữ liệu": "eda",
    "Xử lý dữ liệu": "preprocessing",
    "Huấn luyện mô hình": "training",
}


def _detect_ambiguity(user_query):
    q = (user_query or "").strip().lower()
    return len(q) < 15 or q in _AMBIGUOUS_QUERIES


def _render_input_summary(context):
    """Hiển thị tóm tắt input, cho phép user làm rõ nếu query chưa rõ ràng."""
    st.subheader("Xác nhận trước khi chạy")

    file_summary = ", ".join(
        f"**{k}** ({len(v):,} dòng × {len(v.columns)} cột)"
        for k, v in context.files.items()
    )
    domain_note = "Từ file nghiệp vụ đã upload" if context.domain_context else "Dùng phân tích chung (không có file nghiệp vụ)"

    st.info(
        f"**Loại experiment:** {context.experiment_type}  \n"
        f"**File dữ liệu:** {file_summary}  \n"
        f"**Yêu cầu:** {context.user_query or '_(không có)_'}  \n"
        f"**Domain:** {domain_note}"
    )

    st.caption("Xem trước dữ liệu (5 dòng đầu):")
    for name, df in context.files.items():
        st.caption(f"**{name}**")
        st.dataframe(df.head(5))

    if _detect_ambiguity(context.user_query):
        st.warning("Yêu cầu chưa rõ ràng. Bạn có thể làm rõ thêm để kết quả tốt hơn:")
        q1 = st.text_input("Bạn muốn tập trung vào cột nào? (để trống = phân tích tất cả)", key="clarify_col")
        q2 = st.text_input("Muốn phân tích gì? (phân phối / tương quan / xu hướng thời gian / ...)", key="clarify_focus")
        extra = " ".join(filter(None, [q1.strip(), q2.strip()]))
        if extra:
            context.user_query = f"{context.user_query or ''} {extra}".strip()
            st.session_state.context = context


MAX_FEEDBACK_CONTEXT_CHARS = 3000


def _render_refinement_box(context, prev_text, reset_keys):
    """Góp ý + chạy lại — kết hợp kết quả lần trước với góp ý mới vào user_query rồi re-run.

    reset_keys: tên các session_state key cần xóa để trigger chạy lại agent/pipeline.
    """
    st.subheader("Chưa hài lòng với kết quả?")
    feedback = st.text_area(
        "Góp ý hoặc yêu cầu chạy lại theo hướng khác (để trống nếu không cần chạy lại)",
        key="refinement_feedback",
    )
    if st.button("Chạy lại với góp ý này", key="refinement_run"):
        if not feedback.strip():
            st.warning("Hãy nhập góp ý trước khi chạy lại.")
        else:
            combined_prev = (prev_text or "")[:MAX_FEEDBACK_CONTEXT_CHARS]
            context.user_query = (
                f"{context.user_query or ''}\n\n"
                f"--- Kết quả lần chạy trước ---\n{combined_prev}\n\n"
                f"--- Góp ý của người dùng cho lần chạy này ---\n{feedback.strip()}\n"
                "Hãy điều chỉnh phân tích theo góp ý này, đừng lặp lại y nguyên kết quả cũ."
            ).strip()
            st.session_state.context = context
            for key in reset_keys:
                if key == "pipeline_steps":
                    st.session_state[key] = {}
                elif key == "pipeline_stage_idx":
                    st.session_state[key] = 0
                else:
                    st.session_state[key] = None
            st.rerun()


def _render_stage_refinement_box(context, stage, prev_text, steps):
    """Góp ý riêng cho stage đang xem trong Full Pipeline — chỉ xóa + chạy lại ĐÚNG stage này.

    Các stage khác (trước/sau) giữ nguyên trong `steps` — context.extra/context.files của
    các stage trước đó không bị động tới, nên chỉ tốn lại đúng phần việc của stage này.
    """
    st.subheader(f"Chưa hài lòng với bước {STAGE_LABELS[stage]}?")
    feedback = st.text_area(
        "Góp ý cho riêng bước này (để trống nếu không cần chạy lại)",
        key=f"stage_feedback_{stage}",
    )
    if st.button("Chạy lại bước này với góp ý", key=f"stage_refine_{stage}"):
        if not feedback.strip():
            st.warning("Hãy nhập góp ý trước khi chạy lại.")
        else:
            combined_prev = (prev_text or "")[:MAX_FEEDBACK_CONTEXT_CHARS]
            context.user_query = (
                f"{context.user_query or ''}\n\n"
                f"--- Kết quả bước {STAGE_LABELS[stage]} lần trước ---\n{combined_prev}\n\n"
                f"--- Góp ý của người dùng cho bước này ---\n{feedback.strip()}\n"
                "Hãy điều chỉnh theo góp ý này, đừng lặp lại y nguyên kết quả cũ."
            ).strip()
            st.session_state.context = context
            st.session_state[f"stage_just_refined_{stage}"] = True
            del steps[stage]
            st.rerun()


def _combine_pipeline_text(result):
    """Gộp summary của từng stage Full Pipeline thành 1 đoạn text cho refinement box."""
    parts = []
    for stage, r in result.data.get("steps", {}).items():
        if r.summary:
            parts.append(f"[{STAGE_LABELS.get(stage, stage)}] {r.summary}")
    return "\n".join(parts)


STAGE_LABELS = {
    "eda": "Khám phá dữ liệu (EDA)",
    "preprocessing": "Xử lý dữ liệu",
    "training": "Huấn luyện mô hình",
    "evaluation": "Đánh giá mô hình",
}


def _run_agent(context):
    agent = route(context.experiment_type, context)
    return asyncio.run(agent.run(context))


def _save_run(context, result):
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger = ExecutionLogger(run_id)
    for entry in result.log:
        logger.log(entry.get("step"), entry, entry.get("status"))
    logger.save()

    st.session_state.runs.append({
        "run_id": run_id,
        "problem": context.problem_name,
        "experiment_type": context.experiment_type,
        "status": "success" if result.success else "error",
        "summary": result.summary,
    })
    return run_id


def _reset_pipeline_state():
    st.session_state.pipeline_steps = {}
    st.session_state.pipeline_stage_idx = 0
    st.session_state.pipeline_result = None
    st.session_state.agent_result = None
    st.session_state.detection = None
    st.session_state.merge_decision = None
    st.session_state.input_confirmed = False


def _split_charts_by_source(charts):
    """Tách chart 'trigger' (tổng quan, không cần khớp insight) khỏi chart 'planner'
    (có thể được insight gắn thẻ [[chart:ID]]). Chart của agent khác (training/evaluation/...)
    không có field "source" -> rơi hết vào nhóm planner, render fallback như cũ."""
    trigger = [c for c in (charts or []) if isinstance(c, dict) and c.get("source") == "trigger"]
    planner = [c for c in (charts or []) if not (isinstance(c, dict) and c.get("source") == "trigger")]
    return trigger, planner


def _render_insight_with_charts(insight_text, planner_charts):
    """Render insight, chèn ảnh ngay sau thẻ [[chart:ID]] nếu LLM có gắn; chart 'planner' nào
    không được gắn thẻ thì vẫn hiện ở cuối (fallback) để không bị mất."""
    from agents.insight_generator import split_insight_by_charts

    segments, used_ids = split_insight_by_charts(insight_text, planner_charts)
    for seg in segments:
        if seg["type"] == "text":
            st.markdown(seg["content"])
        else:
            chart = seg["chart"]
            st.image(chart["path"])
            if chart.get("caption"):
                st.caption(chart["caption"])

    leftover = [c for c in planner_charts if c.get("id") is not None and c["id"] not in used_ids]
    if leftover:
        st.caption("Biểu đồ khác:")
        render_charts(leftover)


def _render_code_export(kind, result, context):
    """Expander 'Xem code đã chạy' — sinh từ log/config thật (không qua LLM), kèm nút tải .py.

    kind: "eda" | "preprocessing" | "training" — loại nào chưa hỗ trợ thì không hiện gì (return sớm).
    """
    code_str = None
    if kind == "eda":
        code_str = eda_log_to_code(result.log)
    elif kind == "preprocessing":
        cfg = result.data.get("config") if result.data else None
        steps = result.data.get("steps") if result.data else None
        code_str = preprocessing_config_to_code(cfg, target_col=context.extra.get("target_col"), steps=steps)
    elif kind == "training":
        code_str = training_log_to_code(result.data, result.log, target_col=context.extra.get("target_col"))

    if not code_str:
        return

    with st.expander("Xem code đã chạy"):
        st.code(code_str, language="python")
        st.download_button(
            "Tải code (.py)", code_str, file_name=f"{kind}_code.py", key=f"download_code_{kind}_{id(result)}"
        )


def _render_step_result(result, stage=None, context=None):
    if result.summary:
        st.markdown(result.summary)

    trigger_charts, planner_charts = _split_charts_by_source(result.charts)
    if trigger_charts:
        st.caption("Tổng quan dữ liệu:")
        render_charts(trigger_charts)

    if result.insights:
        st.markdown("**Insight:**")
        has_linkable = any(c.get("id") is not None for c in planner_charts)
        if has_linkable:
            _render_insight_with_charts(result.insights, planner_charts)
        else:
            st.markdown(result.insights)
            if planner_charts:
                render_charts(planner_charts)
    elif planner_charts:
        render_charts(planner_charts)

    if stage == "preprocessing" and result.success:
        processed_path = result.data.get("processed_path")
        if processed_path and os.path.exists(processed_path):
            st.caption("Dữ liệu sau khi xử lý (5 dòng đầu):")
            st.dataframe(pd.read_csv(processed_path).head(5))
    render_log(result.log)

    if result.success and stage in ("eda", "preprocessing", "training") and context is not None:
        _render_code_export(stage, result, context)


def _render_nav_buttons():
    col1, col2 = st.columns(2)
    if col1.button("Xem lịch sử chạy"):
        st.session_state.page = "run_history"
        st.rerun()
    if col2.button("Quay lại"):
        _reset_pipeline_state()
        st.session_state.context = None
        st.session_state.page = "select_experiment"
        st.rerun()


def _render_final_report(result, context):
    st.subheader("Kết quả tổng hợp")

    if result.charts:
        st.markdown("**Tất cả biểu đồ**")
        render_charts(result.charts)

    render_log(result.log)

    preprocessing_step = result.data.get("steps", {}).get("preprocessing")
    if preprocessing_step and preprocessing_step.success:
        processed_path = preprocessing_step.data.get("processed_path")
        if processed_path and os.path.exists(processed_path):
            with open(processed_path, "rb") as f:
                st.download_button(
                    "Tải dữ liệu đã xử lý (CSV)", f.read(), file_name=os.path.basename(processed_path)
                )

    training_step = result.data.get("steps", {}).get("training")
    if training_step and training_step.success:
        model_path = training_step.data.get("model_path")
        if model_path and os.path.exists(model_path):
            with open(model_path, "rb") as f:
                st.download_button(
                    "Tải model về", f.read(), file_name=os.path.basename(model_path)
                )

    report_path = result.data.get("report_path")
    if report_path:
        st.session_state.report_path = report_path
        if st.button("Xem báo cáo"):
            st.session_state.page = "report"
            st.rerun()

    if result.success:
        _render_refinement_box(
            context,
            _combine_pipeline_text(result),
            reset_keys=["pipeline_steps", "pipeline_stage_idx", "pipeline_result"],
        )


def _render_pipeline(context):
    agent = PipelineAgent(context)
    steps = st.session_state.pipeline_steps
    stage_idx = st.session_state.pipeline_stage_idx

    for stage in STAGES[:stage_idx]:
        result = steps.get(stage)
        if result:
            st.subheader(STAGE_LABELS[stage])
            _render_step_result(result, stage, context)

    if st.session_state.pipeline_result is not None:
        _render_final_report(st.session_state.pipeline_result, context)
        _render_nav_buttons()
        return

    if stage_idx >= len(STAGES):
        with st.spinner("Đang tổng hợp báo cáo..."):
            final = agent.finalize(context, steps)
        st.session_state.pipeline_result = final
        _save_run(context, final)
        st.rerun()
        return

    stage = STAGES[stage_idx]

    if stage not in steps:
        with st.spinner(f"Đang chạy: {STAGE_LABELS[stage]}..."):
            asyncio.run(agent.run_stage(stage, context, steps))
        st.rerun()
        return

    result = steps[stage]
    if st.session_state.pop(f"stage_just_refined_{stage}", False):
        # Toast nổi góc màn hình — báo đã chạy lại xong, không phụ thuộc vị trí cuộn trang
        # (khác với việc chỉ đổi nội dung result, dễ bị user lướt qua không để ý).
        st.toast(f"Đã chạy lại bước **{STAGE_LABELS[stage]}** với góp ý mới.", icon="✅")
    st.subheader(STAGE_LABELS[stage])
    _render_step_result(result, stage, context)

    if not result.success:
        st.error(f"Lỗi ở bước {STAGE_LABELS[stage]}: {result.error}")
        with st.spinner("Đang tổng hợp báo cáo..."):
            final = agent.finalize(context, steps)
        st.session_state.pipeline_result = final
        _save_run(context, final)
        st.rerun()
        return

    stage_prev_text = "\n\n".join(filter(None, [result.summary, result.insights]))
    _render_stage_refinement_box(context, stage, stage_prev_text, steps)

    col1, col2 = st.columns(2)
    if col1.button("Tiếp tục", key=f"continue_{stage}"):
        st.session_state.pipeline_stage_idx += 1
        st.rerun()
    if col2.button("Dừng tại đây — xem báo cáo", key=f"stop_{stage}"):
        with st.spinner("Đang tổng hợp báo cáo..."):
            final = agent.finalize(context, steps)
        st.session_state.pipeline_result = final
        _save_run(context, final)
        st.rerun()


def render():
    st.title("Chạy experiment")

    context = st.session_state.context
    if context is None:
        st.warning("Vui lòng cấu hình experiment trước.")
        if st.button("Quay lại"):
            st.session_state.page = "experiment_config"
            st.rerun()
        return

    st.caption(f"Bài toán: **{context.problem_name}** — Experiment: **{context.experiment_type}**")

    # Tùy chỉnh — không có agent, gọi LLM trực tiếp với câu hỏi của user
    if context.experiment_type == "Tùy chỉnh":
        if not st.session_state.get("input_confirmed"):
            _render_input_summary(context)
            col1, col2 = st.columns(2)
            if col1.button("Xác nhận & Chạy", type="primary"):
                st.session_state.input_confirmed = True
                st.rerun()
            if col2.button("Chỉnh lại cấu hình"):
                _reset_pipeline_state()
                st.session_state.page = "experiment_config"
                st.rerun()
            return

        if st.session_state.agent_result is None:
            with st.spinner("Đang xử lý..."):
                response = call_llm(context.user_query, model=MODEL_70B)
            st.session_state.agent_result = response
        st.markdown(st.session_state.agent_result)
        if st.button("Quay lại"):
            _reset_pipeline_state()
            st.session_state.page = "select_experiment"
            st.rerun()
        return

    # Khám phá dữ liệu / Full Pipeline + nhiều file -> hỏi merge trước (FLOW bước 2-3)
    if context.experiment_type in ("Khám phá dữ liệu", "Full Pipeline") and len(context.files) > 1:
        if st.session_state.detection is None:
            from agents.file_detector import detect
            with st.spinner("Đang phân tích schema các file..."):
                st.session_state.detection = detect(context.files, context.file_paths)

        detection = st.session_state.detection
        merge_plan = detection["merge_plan"]

        if merge_plan.can_merge and st.session_state.merge_decision is None:
            st.subheader("Đề xuất kết hợp file")
            if detection.get("suggestion"):
                st.markdown(detection["suggestion"])
            st.write(merge_plan.reason)

            col1, col2 = st.columns(2)
            if col1.button("Đồng ý kết hợp"):
                st.session_state.merge_decision = "merge"
                context.extra["merge_confirmed"] = True
                st.rerun()
            if col2.button("Phân tích riêng từng file"):
                st.session_state.merge_decision = "separate"
                context.extra["merge_confirmed"] = False
                st.rerun()
            return

    # Input summary + confirm trước khi chạy — áp dụng cho mọi experiment (kể cả Full Pipeline,
    # đây là loại tốn kém nhất nên càng cần xác nhận sớm trước khi chạy bất kỳ stage nào).
    if not st.session_state.get("input_confirmed"):
        _render_input_summary(context)
        col1, col2 = st.columns(2)
        if col1.button("Xác nhận & Chạy", type="primary"):
            st.session_state.input_confirmed = True
            st.rerun()
        if col2.button("Chỉnh lại cấu hình"):
            _reset_pipeline_state()
            st.session_state.page = "experiment_config"
            st.rerun()
        return

    # Full Pipeline — chạy theo stage, dừng/confirm giữa các bước (human-in-the-loop)
    if context.experiment_type == "Full Pipeline":
        _render_pipeline(context)
        return

    # Chạy agent
    if st.session_state.agent_result is None:
        with st.spinner("Agent đang xử lý..."):
            result = _run_agent(context)
        st.session_state.agent_result = result
        _save_run(context, result)

        if result.success and context.experiment_type == "Khám phá dữ liệu":
            try:
                report_path = report_generator.generate(
                    dataset_info={
                        "files": list(context.files.keys()),
                        "problem_name": context.problem_name,
                        "experiment_type": context.experiment_type,
                    },
                    eda_results=result.data.get("results", {}),
                    ml_results=None,
                    execution_log=result.log,
                    charts=result.charts,
                )
                result.data["report_path"] = report_path
            except Exception as e:
                st.session_state.agent_result.log.append({"step": "report_generator", "status": "error", "error": str(e)})

    result = st.session_state.agent_result

    if not result.success:
        st.error(f"Lỗi: {result.error}")
    else:
        if result.summary:
            st.subheader("Tóm tắt")
            st.markdown(result.summary)

        trigger_charts, planner_charts = _split_charts_by_source(result.charts)
        if trigger_charts:
            st.subheader("Tổng quan dữ liệu")
            render_charts(trigger_charts)

        if result.insights:
            st.subheader("Insight")
            has_linkable = any(c.get("id") is not None for c in planner_charts)
            if has_linkable:
                _render_insight_with_charts(result.insights, planner_charts)
            else:
                st.markdown(result.insights)
                if planner_charts:
                    render_charts(planner_charts)
        elif planner_charts:
            st.subheader("Biểu đồ")
            render_charts(planner_charts)

        if result.data and result.data.get("bonus_metrics"):
            st.subheader("Metrics bổ sung (tính từ cột target có sẵn)")
            st.json(result.data["bonus_metrics"])

        render_log(result.log)

        code_kind = EXPERIMENT_TYPE_TO_CODE_KIND.get(context.experiment_type)
        if code_kind:
            _render_code_export(code_kind, result, context)

        processed_path = result.data.get("processed_path") if context.experiment_type == "Xử lý dữ liệu" else None
        if processed_path and os.path.exists(processed_path):
            st.caption("Dữ liệu sau khi xử lý (5 dòng đầu):")
            st.dataframe(pd.read_csv(processed_path).head(5))
            with open(processed_path, "rb") as f:
                st.download_button(
                    "Tải dữ liệu đã xử lý (CSV)", f.read(), file_name=os.path.basename(processed_path)
                )

        model_path = result.data.get("model_path") if context.experiment_type == "Huấn luyện mô hình" else None
        if model_path and os.path.exists(model_path):
            with open(model_path, "rb") as f:
                st.download_button(
                    "Tải model về", f.read(), file_name=os.path.basename(model_path)
                )

        output_path = result.data.get("output_path") if context.experiment_type == "Suy luận mô hình" else None
        if output_path and os.path.exists(output_path):
            with open(output_path, "rb") as f:
                st.download_button(
                    "Tải kết quả dự đoán (CSV)", f.read(), file_name=os.path.basename(output_path)
                )

        report_path = result.data.get("report_path") if result.data else None
        if report_path:
            st.session_state.report_path = report_path
            if st.button("Xem báo cáo"):
                st.session_state.page = "report"
                st.rerun()

        prev_text = "\n\n".join(filter(None, [result.summary, result.insights]))
        _render_refinement_box(context, prev_text, reset_keys=["agent_result"])

    col1, col2 = st.columns(2)
    if col1.button("Xem lịch sử chạy"):
        st.session_state.page = "run_history"
        st.rerun()
    if col2.button("Quay lại"):
        st.session_state.agent_result = None
        st.session_state.detection = None
        st.session_state.merge_decision = None
        st.session_state.input_confirmed = False
        st.session_state.page = "select_experiment"
        st.rerun()
