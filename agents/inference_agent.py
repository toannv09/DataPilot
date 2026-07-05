"""Inference Agent — load model, predict trên data mới, giải thích kết quả tiếng Việt."""

import os
from datetime import datetime

from agents.base_agent import AgentResult, BaseAgent
from llm.client import MODEL_DEFAULT, call_llm
from tools.ml.metrics import compute_supervised_metrics
from tools.ml.ml_viz import plot_actual_vs_predicted, plot_confusion_matrix
from tools.ml.preprocessor import handle_missing
from tools.ml.trainer import load_model_bundle

PROCESSED_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")

EXPLAIN_PREDICTION_PROMPT = """
Yêu cầu của người dùng: {user_query}

Kết quả dự đoán (5 dòng đầu):
{predictions_sample}

Domain: {domain_context}

Hãy giải thích ngắn gọn bằng tiếng Việt ý nghĩa của các giá trị dự đoán này,
điều chỉnh ngôn ngữ theo yêu cầu của người dùng.
"""


class InferenceAgent(BaseAgent):
    async def run(self, context=None):
        context = context or self.context
        self._status = "running"

        try:
            model_path = context.extra["model_path"]
            bundle = load_model_bundle(model_path)
            model = bundle["model"]
            pipeline = bundle.get("pipeline")
            task_type = bundle.get("task_type")

            df = next(iter(context.files.values())).copy()
            # Ưu tiên target_col đã lưu trong model (lúc train) — dropdown chọn target ở UI
            # chỉ liệt kê cột có trong file MỚI upload, mà data suy luận thường KHÔNG có cột
            # target (đó là cái cần dự đoán), nên không thể dựa vào context.extra một mình.
            target_col = context.extra.get("target_col") or bundle.get("target_col")
            has_target = bool(target_col and target_col in df.columns)

            if pipeline is not None:
                feature_df = df.drop(columns=[target_col]) if has_target else df
                X = pipeline.transform(feature_df)
            else:
                df_numeric = df.select_dtypes(include="number").copy()
                for col in df_numeric.columns:
                    if df_numeric[col].isna().any():
                        df_numeric = handle_missing(df_numeric, col, "median")

                X = df_numeric.drop(columns=[target_col]) if has_target and target_col in df_numeric.columns else df_numeric

            feature_names = bundle.get("feature_names")
            if feature_names:
                X = X[[c for c in feature_names if c in X.columns]]

            predictions = model.predict(X)

            df_result = df.copy()
            df_result["predicted"] = predictions

            os.makedirs(PROCESSED_DIR, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(PROCESSED_DIR, f"predictions_{timestamp}.csv")
            df_result.to_csv(output_path, index=False)

            bonus_metrics = None
            charts = []
            if has_target and task_type in ("regression", "classification"):
                y_true = df[target_col]
                # Bỏ dòng thiếu target khi tính bonus_metrics — không có nhãn thật thì không
                # đánh giá được dòng đó, nhưng vẫn giữ predictions cho TẤT CẢ dòng ở output_path.
                valid_idx = y_true.dropna().index
                if len(valid_idx) > 0:
                    y_true_valid = y_true.loc[valid_idx]
                    pred_valid = predictions[df.index.get_indexer(valid_idx)]
                    bonus_metrics = compute_supervised_metrics(task_type, y_true_valid, pred_valid)
                    if task_type == "regression":
                        charts.append(plot_actual_vs_predicted(y_true_valid, pred_valid))
                    else:
                        charts.append(plot_confusion_matrix(y_true_valid, pred_valid))

            explanation = call_llm(
                EXPLAIN_PREDICTION_PROMPT.format(
                    user_query=context.user_query or "(không có yêu cầu cụ thể)",
                    predictions_sample=df_result.head(5).to_json(orient="records", force_ascii=False),
                    domain_context=context.domain_context,
                ),
                model=MODEL_DEFAULT,
            )

            self._status = "done"
            return AgentResult(
                success=True,
                summary=explanation,
                data={"output_path": output_path, "bonus_metrics": bonus_metrics},
                charts=charts,
            )
        except Exception as e:
            self._status = "error"
            return AgentResult(success=False, error=str(e))

    async def get_status(self):
        return self._status
