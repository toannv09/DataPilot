"""ydata-profiling hybrid — chạy nhanh (minimal=True) và trích xuất findings cốt lõi.

Chỉ extract các thông tin hữu ích cho EDA pipeline:
- Variable stats (mean, std, missing, type)
- Alerts (warnings từ profiling)
- Top correlations (|r| >= threshold)

Không sinh HTML report — chỉ dùng như một nguồn context bổ sung.
"""

import warnings

TOP_CORR_THRESHOLD = 0.65
KEEP_STATS = {"mean", "std", "min", "max", "p_missing", "n_missing", "type"}


def run_profiling(df, sample_size=5000):
    """Chạy ydata-profiling minimal và trả về dict findings cốt lõi.

    Nếu thư viện không có hoặc lỗi → trả về {} (không làm crash pipeline).
    """
    try:
        from ydata_profiling import ProfileReport
    except ImportError:
        return {}

    try:
        # Sample lớn để tránh timeout
        sample_df = df.sample(min(sample_size, len(df)), random_state=42) if len(df) > sample_size else df

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            profile = ProfileReport(
                sample_df,
                minimal=True,
                progress_bar=False,
                correlations={"pearson": {"calculate": True}, "spearman": {"calculate": False},
                              "kendall": {"calculate": False}, "phi_k": {"calculate": False},
                              "cramers": {"calculate": False}},
            )
            desc = profile.get_description()

        variables = {}
        for col, stats in desc.variables.items():
            filtered = {k: v for k, v in stats.items() if k in KEEP_STATS}
            variables[col] = filtered

        alerts = []
        for alert in desc.alerts:
            alert_type = getattr(alert, "alert_type", None)
            alerts.append({
                "col": alert.column_name if hasattr(alert, "column_name") else str(alert),
                "type": alert_type.name if hasattr(alert_type, "name") else str(alert_type or alert),
            })

        top_corr = []
        try:
            pearson = desc.correlations.get("pearson")
            if pearson is not None:
                cols = list(pearson.columns)
                for i, c1 in enumerate(cols):
                    for c2 in cols[i + 1:]:
                        val = pearson.loc[c2, c1] if c2 in pearson.index else pearson.loc[c1, c2]
                        if abs(val) >= TOP_CORR_THRESHOLD:
                            top_corr.append({"col1": c1, "col2": c2, "r": round(float(val), 3)})
        except Exception:
            pass

        return {
            "n_rows": desc.table.get("n", len(df)),
            "n_cols": desc.table.get("n_var", len(df.columns)),
            "variables": variables,
            "alerts": alerts,
            "top_correlations": top_corr,
        }

    except Exception:
        return {}


def profiling_to_context(profiling_result):
    """Chuyển profiling result thành chuỗi ngắn để bổ sung context cho planner/question_generator."""
    if not profiling_result:
        return ""

    lines = []
    alerts = profiling_result.get("alerts", [])
    if alerts:
        alert_strs = [f"{a['col']} ({a['type']})" for a in alerts[:5]]
        lines.append(f"Cảnh báo profiling: {', '.join(alert_strs)}")

    top_corr = profiling_result.get("top_correlations", [])
    if top_corr:
        corr_strs = [f"{c['col1']}↔{c['col2']} r={c['r']}" for c in top_corr[:5]]
        lines.append(f"Tương quan mạnh: {', '.join(corr_strs)}")

    high_missing = [
        f"{col} ({round(s.get('p_missing', 0) * 100, 1)}%)"
        for col, s in profiling_result.get("variables", {}).items()
        if isinstance(s, dict) and s.get("p_missing", 0) > 0.05
    ]
    if high_missing:
        lines.append(f"Cột thiếu nhiều (>5%): {', '.join(high_missing[:5])}")

    return "\n".join(lines)
