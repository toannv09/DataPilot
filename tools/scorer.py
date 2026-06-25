"""Tính p-value / significance cho các kết quả thống kê EDA."""

import pandas as pd


def score_trend(series):
    """Kendall tau trend test. p_value < 0.05 → xu hướng có ý nghĩa thống kê."""
    try:
        from scipy.stats import kendalltau

        clean = pd.Series(series).dropna()
        if len(clean) < 4:
            return None
        tau, p = kendalltau(range(len(clean)), clean.values)
        return {
            "test": "kendall-tau",
            "tau": round(float(tau), 3),
            "p_value": round(float(p), 4),
            "significant": bool(p < 0.05),
            "direction": "tăng" if tau > 0 else "giảm",
            "interpretation": (
                f"Xu hướng {('tăng' if tau > 0 else 'giảm')} có ý nghĩa thống kê (p={p:.4f})"
                if p < 0.05
                else f"Không có xu hướng rõ ràng (p={p:.4f})"
            ),
        }
    except Exception:
        return None


def score_pearson(r, n):
    """P-value cho hệ số tương quan Pearson."""
    try:
        from scipy import stats as sp_stats

        if n < 3 or abs(r) >= 1.0:
            return None
        t = r * ((n - 2) ** 0.5) / ((1 - r**2) ** 0.5)
        p = float(2 * (1 - sp_stats.t.cdf(abs(t), df=n - 2)))
        return {
            "r": round(float(r), 3),
            "p_value": round(p, 4),
            "significant": bool(p < 0.05),
        }
    except Exception:
        return None


def score_group_diff(df, col, by):
    """Kruskal-Wallis test — kiểm tra khác biệt phân phối giữa các nhóm (không giả định chuẩn)."""
    try:
        from scipy import stats as sp_stats

        groups = [g[col].dropna().values for _, g in df.groupby(by) if len(g[col].dropna()) >= 2]
        if len(groups) < 2:
            return None
        stat, p = sp_stats.kruskal(*groups)
        return {
            "test": "kruskal-wallis",
            "statistic": round(float(stat), 3),
            "p_value": round(float(p), 4),
            "significant": bool(p < 0.05),
            "interpretation": (
                f"Có sự khác biệt có ý nghĩa thống kê giữa các nhóm {by} (p={p:.4f})"
                if p < 0.05
                else f"Không có sự khác biệt có ý nghĩa thống kê (p={p:.4f})"
            ),
        }
    except Exception:
        return None
