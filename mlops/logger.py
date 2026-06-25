"""Execution log từng bước agent thực hiện — dùng cho báo cáo và trang run_history."""

import json
import os
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs", "logs")


class ExecutionLogger:
    def __init__(self, run_id):
        self.run_id = run_id
        self.entries = []

    def log(self, step, decision, result):
        """Thêm 1 dòng log: timestamp + step + decision + result."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "step": step,
            "decision": decision,
            "result": result,
        }
        self.entries.append(entry)
        return entry

    def save(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, f"{self.run_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, ensure_ascii=False, default=str, indent=2)
        return path

    @staticmethod
    def load(run_id):
        path = os.path.join(LOG_DIR, f"{run_id}.json")
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def list_runs():
        os.makedirs(LOG_DIR, exist_ok=True)
        return sorted(f[:-5] for f in os.listdir(LOG_DIR) if f.endswith(".json"))
