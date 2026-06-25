"""Feature relationship analysis — Mutual Information, tương quan phi tuyến."""

from sklearn.feature_selection import mutual_info_classif, mutual_info_regression

from tools.schema_analyzer import detect_datetime_columns


def mutual_info_scores(df, target_col):
    """MI score giữa mỗi feature và target. Bắt được quan hệ non-linear.

    Tự phát hiện regression (target liên tục) vs classification (target rời rạc).
    Trả về dict {col: score} sắp xếp từ cao đến thấp.
    """
    dt_cols = detect_datetime_columns(df)
    drop_cols = [target_col] + dt_cols

    X = (
        df.drop(columns=drop_cols, errors="ignore")
        .select_dtypes(include="number")
        .dropna()
    )
    y = df[target_col].loc[X.index].dropna()
    X = X.loc[y.index]

    if X.empty or len(y) < 10:
        return {}

    is_continuous = y.nunique() > 20
    fn = mutual_info_regression if is_continuous else mutual_info_classif
    scores = fn(X, y, random_state=42)
    result = dict(zip(X.columns, map(float, scores)))
    return dict(sorted(result.items(), key=lambda x: -x[1]))
