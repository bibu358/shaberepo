"""実験の生データ（プロンプト・出力など）を runs/ にJSONで保存する"""
import json
import os
from datetime import datetime

RUNS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "runs")


def save_run(data: dict) -> str:
    """data に timestamp を付けて runs/YYYYMMDD-HHMMSS.json に保存し、パスを返す"""
    os.makedirs(RUNS_DIR, exist_ok=True)
    now = datetime.now()
    payload = {"timestamp": now.isoformat(timespec="seconds"), **data}
    path = os.path.join(RUNS_DIR, now.strftime("%Y%m%d-%H%M%S") + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path
