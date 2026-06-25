"""Tiền xử lý dữ liệu cho ML: missing value, encode, scale, time features, train/test split."""

import pandas as pd
from sklearn.preprocessing import LabelEncoder, MinMaxScaler, StandardScaler

ONEHOT_CARDINALITY_THRESHOLD = 10


def handle_missing(df, col, strategy):
    """strategy: 'median', 'mean', 'drop', 'forward_fill'."""
    df = df.copy()

    if strategy == "median":
        df[col] = df[col].fillna(df[col].median())
    elif strategy == "mean":
        df[col] = df[col].fillna(df[col].mean())
    elif strategy == "drop":
        df = df.dropna(subset=[col])
    elif strategy == "forward_fill":
        df[col] = df[col].ffill()
    else:
        raise ValueError(f"strategy không hợp lệ: {strategy}")

    return df


def encode_categorical(df, col, method=None):
    """method: 'label' hoặc 'onehot'. Nếu None, tự chọn theo cardinality."""
    df = df.copy()
    n_unique = df[col].nunique()

    if method is None:
        method = "label" if n_unique > ONEHOT_CARDINALITY_THRESHOLD else "onehot"

    if method == "label":
        encoder = LabelEncoder()
        df[col] = encoder.fit_transform(df[col].astype(str))
    elif method == "onehot":
        dummies = pd.get_dummies(df[col], prefix=col)
        df = pd.concat([df.drop(columns=[col]), dummies], axis=1)
    else:
        raise ValueError(f"method không hợp lệ: {method}")

    return df


def scale_features(df, cols, method="standard"):
    """method: 'standard' hoặc 'minmax'. Trả về (DataFrame, scaler)."""
    df = df.copy()

    if method == "standard":
        scaler = StandardScaler()
    elif method == "minmax":
        scaler = MinMaxScaler()
    else:
        raise ValueError(f"method không hợp lệ: {method}")

    df[cols] = scaler.fit_transform(df[cols])
    return df, scaler


class NumericScaler:
    """Scale cột số cho clustering — KMeans/DBSCAN dựa trên khoảng cách, nếu không scale thì
    cột có magnitude lớn nhất (vd lương hàng chục triệu) sẽ áp đảo hoàn toàn các cột khác.

    Có .transform(df) để dùng thay PreprocessingPipeline khi Training clustering đứng riêng
    (không qua stage Preprocessing) — Evaluation/Inference áp lại đúng scale đã học lúc fit.
    """

    def __init__(self):
        self.scaler = None
        self.columns = []
        self.fill_values = {}

    def fit_transform(self, df):
        df_numeric = df.select_dtypes(include="number").copy()
        for col in df_numeric.columns:
            if df_numeric[col].isna().any():
                fill_value = df_numeric[col].median()
                self.fill_values[col] = fill_value
                df_numeric[col] = df_numeric[col].fillna(fill_value)

        self.columns = df_numeric.columns.tolist()
        self.scaler = StandardScaler()
        scaled = self.scaler.fit_transform(df_numeric)
        return pd.DataFrame(scaled, columns=self.columns, index=df_numeric.index)

    def transform(self, df):
        df_numeric = pd.DataFrame(index=df.index)
        for col in self.columns:
            df_numeric[col] = df[col] if col in df.columns else 0

        for col, fill_value in self.fill_values.items():
            if df_numeric[col].isna().any():
                df_numeric[col] = df_numeric[col].fillna(fill_value)

        scaled = self.scaler.transform(df_numeric)
        return pd.DataFrame(scaled, columns=self.columns, index=df_numeric.index)


def create_time_features(df, col):
    """Thêm cột: hour, day_of_week, month, is_weekend, is_holiday."""
    df = df.copy()
    dt = pd.to_datetime(df[col])

    df["hour"] = dt.dt.hour
    df["day_of_week"] = dt.dt.dayofweek
    df["month"] = dt.dt.month
    df["is_weekend"] = (dt.dt.dayofweek >= 5).astype(int)

    if "is_holiday" not in df.columns:
        df["is_holiday"] = 0

    return df


def train_test_split_time(df, target, ratio=0.8):
    """Split theo thời gian (không random): `ratio` đầu tiên làm train."""
    split_idx = int(len(df) * ratio)
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]

    X_train = train_df.drop(columns=[target])
    y_train = train_df[target]
    X_test = test_df.drop(columns=[target])
    y_test = test_df[target]

    return X_train, X_test, y_train, y_test


def train_test_split_random(df, target, ratio=0.8):
    """Split random cho dữ liệu không phải time series.

    Tự stratify theo target nếu target ít giá trị duy nhất (classification-like) —
    đảm bảo tỷ lệ class trong train/test giống nhau, quan trọng với target mất cân bằng.
    """
    from sklearn.model_selection import train_test_split

    X = df.drop(columns=[target])
    y = df[target]

    stratify = y if y.nunique() <= 10 else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, train_size=ratio, random_state=42, stratify=stratify
    )

    return X_train, X_test, y_train, y_test
