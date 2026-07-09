"""AI呼び出しのトークン消費と推定コストを集計する。

各Geminiレスポンスの usage_metadata からトークン数を集める（トークン数は正確）。
金額は概算：下の単価は参考値なので、実費は必ず GCP 請求で確認すること。
1回の記録作成では複数のAI（①文字起こし②整形③検証④修正）が走るため、
それらを1回の「AI実行」としてまとめて集計する。

使い方（app.py）：
    usage.reset()          # パイプライン開始時
    ... 各AIが usage.record() を呼ぶ ...
    s = usage.summary()    # 終了時に集計を取得
"""

# gemini-2.5-flash の参考単価（USD / 100万トークン）。2026-07時点の概算・**要確認**。
# 実単価が変わっていたらここを直す（VertexAI料金ページ / 実際の請求で確認）。
# ※音声入力は単価が高めのため、文字起こしの実費はこの概算よりやや高くなることがある。
PRICE = {
    "gemini-2.5-flash": {"in": 0.30, "out": 2.50},
}
USD_JPY = 155.0  # 概算の為替レート

_records = []  # [{"label", "model", "in", "out", "total"}]


def reset():
    """パイプライン開始時に呼ぶ（前回の集計をクリア）"""
    _records.clear()


def record(model: str, resp, label: str = ""):
    """1回のGemini呼び出しのトークンを記録する。usage_metadata が無ければ無視。"""
    um = getattr(resp, "usage_metadata", None)
    if um is None:
        return
    pin = getattr(um, "prompt_token_count", 0) or 0
    pout = getattr(um, "candidates_token_count", 0) or 0
    total = getattr(um, "total_token_count", 0) or (pin + pout)
    _records.append({"label": label, "model": model, "in": pin, "out": pout, "total": total})


def _cost_usd(rec: dict) -> float:
    p = PRICE.get(rec["model"])
    if not p:
        return 0.0
    return rec["in"] / 1e6 * p["in"] + rec["out"] / 1e6 * p["out"]


def summary() -> dict:
    """現在たまっている呼び出しの集計（トークン合計・推定コスト・内訳）を返す。"""
    usd = sum(_cost_usd(r) for r in _records)
    return {
        "calls": len(_records),
        "in": sum(r["in"] for r in _records),
        "out": sum(r["out"] for r in _records),
        "total": sum(r["total"] for r in _records),
        "usd": usd,
        "jpy": usd * USD_JPY,
        "breakdown": [dict(r) for r in _records],
    }


def add(a: dict | None, b: dict | None) -> dict:
    """2つの summary を足す（セッション累計用）。"""
    a = a or {"calls": 0, "in": 0, "out": 0, "total": 0, "usd": 0.0, "jpy": 0.0}
    b = b or {"calls": 0, "in": 0, "out": 0, "total": 0, "usd": 0.0, "jpy": 0.0}
    return {k: a.get(k, 0) + b.get(k, 0)
            for k in ("calls", "in", "out", "total", "usd", "jpy")}
