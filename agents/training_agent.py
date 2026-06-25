"""Training Agent — detect task type, train baseline models, leaderboard, lưu model tốt nhất."""

import json
import re

from agents.base_agent import AgentResult, BaseAgent
from llm.client import MODEL_70B, call_llm
from llm.prompts.ml_prompt import ML_EXPLANATION_USER, TASK_DETECTION_USER
from tools.ml import ml_viz
from tools.ml.model_selector import detect_task_type, get_baseline_models
from tools.ml.preprocessor import (
    NumericScaler,
    handle_missing,
    train_test_split_random,
    train_test_split_time,
)
from tools.ml.trainer import compare_models, get_best_model, save_model, train_and_evaluate
from tools.schema_analyzer import detect_datetime_columns

DEFAULT_METRIC = {"regression": "rmse", "classification": "f1", "clustering": "silhouette"}


def _extract_json(text):
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


class TrainingAgent(BaseAgent):
    async def run(self, context=None):
        context = context or self.context
        self._status = "running"

        try:
            df = next(iter(context.files.values())).copy()

            target_col = context.extra.get("target_col")
            task_type = context.extra.get("task_type")
            split_ratio = context.extra.get("split_ratio", 0.8)
            selected_model = context.extra.get("selected_model")
            model_params = context.extra.get("model_params")
            optimize = context.extra.get("optimize", False)

            if not target_col and task_type != "clustering":
                detection = self._detect_task(context, df)
                target_col = target_col or detection.get("target_col")
                task_type = task_type or detection.get("task_type")

            dt_cols = detect_datetime_columns(df)
            df_numeric_raw = df.select_dtypes(include="number").copy()
            df_numeric = df_numeric_raw.copy()

            for col in df_numeric.columns:
                if df_numeric[col].isna().any():
                    df_numeric = handle_missing(df_numeric, col, "median")

            if not task_type:
                task_type = detect_task_type(df_numeric, target_col)

            clustering_scaler = None
            used_existing_pipeline = False
            if task_type == "clustering":
                split_method = "clustering"
                if context.extra.get("preprocessing_pipeline") is not None:
                    # Đã qua stage Preprocessing (Full Pipeline) -> df_numeric đã được scale rồi.
                    used_existing_pipeline = True
                    X_train, y_train, X_test, y_test = df_numeric, None, df_numeric, None
                else:
                    # KMeans/DBSCAN dựa trên khoảng cách -> bắt buộc scale, nếu không cột có
                    # magnitude lớn nhất (vd lương) sẽ áp đảo hoàn toàn các cột khác.
                    # Dùng df_numeric_raw (còn NaN) để NumericScaler tự ghi nhận fill_values,
                    # tái dùng đúng lúc Evaluation/Inference transform data mới.
                    clustering_scaler = NumericScaler()
                    df_scaled = clustering_scaler.fit_transform(df_numeric_raw)
                    X_train, y_train, X_test, y_test = df_scaled, None, df_scaled, None
            elif dt_cols:
                split_method = "time"
                X_train, X_test, y_train, y_test = train_test_split_time(df_numeric, target_col, split_ratio)
            else:
                split_method = "random"
                X_train, X_test, y_train, y_test = train_test_split_random(df_numeric, target_col, split_ratio)

            models = get_baseline_models(task_type, selected_model, model_params)
            results = train_and_evaluate(X_train, y_train, X_test, y_test, models, optimize=optimize)
            leaderboard = compare_models(results)

            metric = DEFAULT_METRIC[task_type]
            best_model = get_best_model(results, metric)
            if best_model is None:
                raise ValueError(
                    f"Không có model nào tính được metric '{metric}' (task_type={task_type})."
                )
            best_name = next(name for name, r in results.items() if r["model"] is best_model)

            charts = []
            if len(leaderboard) > 1:
                charts.append(ml_viz.plot_model_comparison(leaderboard, metric))

            if hasattr(best_model, "feature_importances_"):
                charts.append(ml_viz.plot_feature_importance(best_model, list(X_train.columns)))
            elif hasattr(best_model, "coef_") and best_model.coef_.size == len(X_train.columns):
                charts.append(ml_viz.plot_feature_importance(best_model, list(X_train.columns)))

            model_path = save_model(
                best_model,
                best_name,
                pipeline=context.extra.get("preprocessing_pipeline") or clustering_scaler,
                task_type=task_type,
                target_col=target_col,
                feature_names=list(X_train.columns),
                metric=metric,
                metrics=results[best_name]["metrics"],
            )

            explanation = self._explain(results, leaderboard, context)

            self._status = "done"
            return AgentResult(
                success=True,
                summary=explanation,
                data={
                    "task_type": task_type,
                    "target_col": target_col,
                    "leaderboard": leaderboard.to_dict(orient="records"),
                    "best_model": best_name,
                    "model_path": model_path,
                    "metric": metric,
                    "split_method": split_method,
                    "split_ratio": split_ratio,
                    "used_existing_pipeline": used_existing_pipeline,
                },
                charts=charts,
                log=[
                    {"step": name, "status": "success", "metrics": r["metrics"], "params": r["model"].get_params()}
                    for name, r in results.items()
                ],
            )
        except Exception as e:
            self._status = "error"
            return AgentResult(success=False, error=str(e))

    def _detect_task(self, context, df):
        prompt = TASK_DETECTION_USER.format(
            user_query=context.user_query,
            dataset_info=json.dumps({"columns": list(df.columns)}, ensure_ascii=False),
            eda_insights=context.extra.get("eda_insights", ""),
        )
        response = call_llm(prompt, model=MODEL_70B)
        try:
            return _extract_json(response)
        except (json.JSONDecodeError, AttributeError):
            return {"task_type": None, "target_col": None}

    def _explain(self, results, leaderboard, context):
        feature_importance = {}
        for name, r in results.items():
            if hasattr(r["model"], "feature_importances_"):
                feature_importance[name] = r["model"].feature_importances_.tolist()

        prompt = ML_EXPLANATION_USER.format(
            user_query=context.user_query or "(không có yêu cầu cụ thể)",
            model_results=leaderboard.to_json(orient="records", force_ascii=False),
            feature_importance=json.dumps(feature_importance, ensure_ascii=False),
            domain_context=context.domain_context,
        )
        return call_llm(prompt, model=MODEL_70B)

    async def get_status(self):
        return self._status
