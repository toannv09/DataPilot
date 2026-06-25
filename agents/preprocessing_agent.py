"""Preprocessing Agent — xử lý dữ liệu: missing, outlier, encode, scale.

Cấu hình (fill method, outlier method, có skip bước nào không) do preprocessing_planner
quyết định dựa theo user_query — không còn hardcoded hoàn toàn như trước.
"""

import os
from datetime import datetime

import joblib
import pandas as pd

from agents.base_agent import AgentResult, BaseAgent
from agents.preprocessing_planner import plan as preprocessing_plan
from llm.client import MODEL_8B, call_llm
from tools.ml.pipeline import MIN_UNIQUE_FOR_OUTLIER_CLIP, PreprocessingPipeline
from tools.quality_checker import check_missing

PROCESSED_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")

DESCRIBE_STEPS_PROMPT = """
Các bước xử lý dữ liệu đã thực hiện:
{steps}

Hãy viết đoạn mô tả ngắn gọn bằng tiếng Việt giải thích các bước xử lý này cho người không chuyên kỹ thuật.
"""


def _outlier_bounds(series, method):
    """Tính bound outlier theo method, dùng để mô tả log khớp với PreprocessingPipeline."""
    if method == "zscore":
        mean, std = series.mean(), series.std()
        if std == 0:
            return None
        return mean - 3 * std, mean + 3 * std
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return None
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


class PreprocessingAgent(BaseAgent):
    async def run(self, context=None):
        context = context or self.context
        self._status = "running"

        try:
            df = next(iter(context.files.values())).copy()
            steps_log = []
            target_col = context.extra.get("target_col")

            missing = check_missing(df)
            quality_summary = (
                f"Tổng số dòng: {len(df)}. Cột thiếu dữ liệu: {missing['cols_with_missing']}. "
                f"Cột số: {list(df.select_dtypes(include='number').columns)}. "
                f"Cột phân loại: {list(df.select_dtypes(include='object').columns)}."
            )
            cfg = preprocessing_plan(context.user_query, quality_summary)

            for col in missing["cols_with_missing"]:
                if pd.api.types.is_numeric_dtype(df[col]):
                    steps_log.append(f"Điền giá trị thiếu ở cột '{col}' bằng {cfg['fill_method']}.")
                else:
                    steps_log.append(f"Điền giá trị thiếu ở cột '{col}' bằng forward fill.")

            if cfg["skip_outlier"]:
                steps_log.append("Bỏ qua xử lý outlier theo yêu cầu của người dùng.")
            else:
                for col in df.select_dtypes(include="number").columns:
                    if col == target_col:
                        continue
                    if df[col].nunique(dropna=True) < MIN_UNIQUE_FOR_OUTLIER_CLIP:
                        continue
                    bounds = _outlier_bounds(df[col].dropna(), cfg["outlier_method"])
                    if bounds is None:
                        continue
                    lower, upper = bounds
                    n_outliers = int(((df[col] < lower) | (df[col] > upper)).sum())
                    if n_outliers > 0:
                        steps_log.append(
                            f"Giới hạn {n_outliers} giá trị bất thường ở cột '{col}' "
                            f"về khoảng [{lower:.2f}, {upper:.2f}] (phương pháp {cfg['outlier_method']})."
                        )

            if cfg["skip_encode"]:
                steps_log.append("Giữ nguyên cột phân loại dạng chữ theo yêu cầu (không mã hóa).")
            else:
                for col in df.select_dtypes(include="object").columns.tolist():
                    steps_log.append(f"Mã hóa cột phân loại '{col}'.")

            numeric_cols = [c for c in df.select_dtypes(include="number").columns if c != target_col]
            if cfg["skip_scale"]:
                steps_log.append("Giữ nguyên thang đo gốc của các cột số theo yêu cầu (không chuẩn hóa).")
            elif numeric_cols:
                steps_log.append(f"Chuẩn hóa các cột số ({cfg['scale_method']}): {', '.join(numeric_cols)}.")
            if target_col and not cfg["skip_scale"]:
                steps_log.append(f"Giữ nguyên thang đo gốc của cột target '{target_col}' (không chuẩn hóa).")

            pipeline = PreprocessingPipeline()
            df_processed = pipeline.fit_transform(
                df,
                target_col=target_col,
                fill_method=cfg["fill_method"],
                skip_outlier=cfg["skip_outlier"],
                outlier_method=cfg["outlier_method"],
                skip_encode=cfg["skip_encode"],
                skip_scale=cfg["skip_scale"],
                scale_method=cfg["scale_method"],
            )

            os.makedirs(PROCESSED_DIR, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            output_path = os.path.join(PROCESSED_DIR, f"processed_{timestamp}.csv")
            df_processed.to_csv(output_path, index=False)

            pipeline_path = os.path.join(PROCESSED_DIR, f"pipeline_{timestamp}.pkl")
            joblib.dump(pipeline, pipeline_path)

            if steps_log:
                description = call_llm(
                    DESCRIBE_STEPS_PROMPT.format(steps="\n".join(steps_log)), model=MODEL_8B
                )
            else:
                description = "Dữ liệu không cần xử lý thêm — không có giá trị thiếu hoặc cột phân loại."

            self._status = "done"
            return AgentResult(
                success=True,
                summary=description,
                data={
                    "processed_path": output_path,
                    "pipeline_path": pipeline_path,
                    "steps": steps_log,
                    "config": cfg,
                },
                log=[{"step": s, "status": "success"} for s in steps_log],
            )
        except Exception as e:
            self._status = "error"
            return AgentResult(success=False, error=str(e))

    async def get_status(self):
        return self._status
