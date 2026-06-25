"""W&B experiment tracking — chỉ active khi có WANDB_API_KEY."""

import os

import wandb

_run = None


def is_active():
    return bool(os.environ.get("WANDB_API_KEY"))


def init_run(experiment_type, dataset_info):
    """Bắt đầu 1 run W&B mới cho experiment."""
    global _run
    if not is_active():
        return None

    _run = wandb.init(
        project="autoeda",
        config={"experiment_type": experiment_type, "dataset_info": dataset_info},
        reinit=True,
    )
    return _run


def log_tokens(tokens_used, model):
    """Log token tiêu thụ mỗi lần gọi LLM."""
    if not is_active() or _run is None:
        return
    wandb.log({"tokens_per_call": tokens_used, "model": model})


def log_metrics(metrics):
    """Log metrics chung (planning success, retry count, ml metrics, ...)."""
    if not is_active() or _run is None:
        return
    wandb.log(metrics)


def finish_run():
    global _run
    if _run is not None:
        wandb.finish()
        _run = None
