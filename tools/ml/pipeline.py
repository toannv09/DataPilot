"""PreprocessingPipeline — ghi lại các bước xử lý lúc fit để áp lại y nguyên lúc Inference/Evaluation."""

import pandas as pd
from sklearn.preprocessing import LabelEncoder, MinMaxScaler, StandardScaler

ONEHOT_CARDINALITY_THRESHOLD = 10
MIN_UNIQUE_FOR_OUTLIER_CLIP = 5


class PreprocessingPipeline:
    """Fit trên data train, transform lại data mới với đúng tham số đã học."""

    def __init__(self):
        self.missing_fill = {}
        self.outlier_bounds = {}
        self.encoders = {}
        self.scaler = None
        self.scaled_cols = []
        self.feature_columns = []

    def fit_transform(self, df, target_col=None, fill_method="median", skip_outlier=False,
                       outlier_method="iqr", skip_encode=False, skip_scale=False,
                       scale_method="standard"):
        """target_col (nếu có): giữ nguyên thang đo gốc — không outlier-clip, không scale,
        vì cột này sẽ làm nhãn huấn luyện ML; scale/clip nó làm RMSE/MAE vô nghĩa và phá vỡ
        việc diễn giải kết quả dự đoán.

        fill_method/skip_outlier/outlier_method/skip_encode/skip_scale/scale_method:
        cấu hình do preprocessing_planner quyết định theo user_query.
        """
        df = df.copy()

        for col in df.columns:
            if df[col].isna().any():
                if pd.api.types.is_numeric_dtype(df[col]):
                    fill_value = df[col].mean() if fill_method == "mean" else df[col].median()
                else:
                    df[col] = df[col].ffill()
                    fill_value = df[col].mode().iloc[0] if not df[col].mode().empty else ""
                    df[col] = df[col].fillna(fill_value)
                self.missing_fill[col] = fill_value
                df[col] = df[col].fillna(fill_value)

        if not skip_outlier:
            for col in df.select_dtypes(include="number").columns:
                if col == target_col:
                    continue
                series = df[col]
                # Cột nhị phân/ít giá trị (vd cờ 0/1) — IQR/zscore có thể vô nghĩa, clip sẽ xóa mất nhãn thật.
                if series.nunique(dropna=True) < MIN_UNIQUE_FOR_OUTLIER_CLIP:
                    continue
                if outlier_method == "zscore":
                    mean, std = series.mean(), series.std()
                    if std == 0:
                        continue
                    lower, upper = mean - 3 * std, mean + 3 * std
                else:
                    q1, q3 = series.quantile(0.25), series.quantile(0.75)
                    iqr = q3 - q1
                    if iqr == 0:
                        continue
                    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                if ((series < lower) | (series > upper)).any():
                    self.outlier_bounds[col] = (lower, upper)
                    df[col] = series.clip(lower, upper)

        if not skip_encode:
            for col in df.select_dtypes(include="object").columns.tolist():
                n_unique = df[col].nunique()
                if n_unique > ONEHOT_CARDINALITY_THRESHOLD:
                    encoder = LabelEncoder()
                    df[col] = encoder.fit_transform(df[col].astype(str))
                    self.encoders[col] = {"method": "label", "encoder": encoder}
                else:
                    categories = sorted(df[col].astype(str).unique().tolist())
                    dummies = pd.get_dummies(df[col].astype(str), prefix=col)
                    df = pd.concat([df.drop(columns=[col]), dummies], axis=1)
                    self.encoders[col] = {"method": "onehot", "categories": categories}

        if not skip_scale:
            numeric_cols = [c for c in df.select_dtypes(include="number").columns if c != target_col]
            if numeric_cols:
                self.scaler = MinMaxScaler() if scale_method == "minmax" else StandardScaler()
                df[numeric_cols] = self.scaler.fit_transform(df[numeric_cols])
                self.scaled_cols = numeric_cols

        self.feature_columns = df.columns.tolist()
        return df

    def transform(self, df):
        df = df.copy()

        for col, fill_value in self.missing_fill.items():
            if col in df.columns:
                if not pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = df[col].ffill()
                df[col] = df[col].fillna(fill_value)

        for col, (lower, upper) in self.outlier_bounds.items():
            if col in df.columns:
                df[col] = df[col].clip(lower, upper)

        for col, info in self.encoders.items():
            if col not in df.columns:
                continue
            if info["method"] == "label":
                encoder = info["encoder"]
                known = set(encoder.classes_)
                values = df[col].astype(str)
                mapped = values.where(values.isin(known), encoder.classes_[0])
                df[col] = encoder.transform(mapped)
            else:
                dummies = pd.get_dummies(df[col].astype(str), prefix=col)
                for category in info["categories"]:
                    dummy_col = f"{col}_{category}"
                    if dummy_col not in dummies.columns:
                        dummies[dummy_col] = 0
                expected_cols = [f"{col}_{c}" for c in info["categories"]]
                dummies = dummies[expected_cols]
                df = pd.concat([df.drop(columns=[col]), dummies], axis=1)

        if self.scaler is not None and self.scaled_cols:
            for col in self.scaled_cols:
                if col not in df.columns:
                    df[col] = 0
            df[self.scaled_cols] = self.scaler.transform(df[self.scaled_cols])

        for col in self.feature_columns:
            if col not in df.columns:
                df[col] = 0

        return df[self.feature_columns]
