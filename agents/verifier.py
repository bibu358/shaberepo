"""検証AI（事実ガード）：整形結果がソース（原文）と矛盾しないか検証"""
from google import genai
from google.genai import types

from core.schema import VerifyResult

MODEL = "gemini-2.5-flash"

PROMPT_TMPL = """あなたは記録の検証担当です。整形された記録（ドラフト）を元データ（ソース）と比較し、
次の3種類の問題を指摘してください。

- 事実の改変：数値・結果・合否・明確な状態が元データと【変わっている】（例「いけた→破損」「5000回→500回」。最重要）
- 推測の追加：元データに【無かった新しい情報】が、推測・補完で足されている
- 欠落：元データにある重要な事実がドラフトから抜けている

【事実の改変としない＝許容（指摘しない）】
- 推量・所感の言い換え：例「弱い気がする」→「弱い可能性」「低い傾向」（推量の強弱はニュアンス差）
- 修飾語のニュアンス差：例「たぶん60℃」→「約60℃」（数値60℃が保たれていればOK）
- 要約・整理・項目立てによる表現の変化
→ 事実の改変は、数値・合否・結果・明確な状態が【別の値・別の意味に変わった】場合に限る。

出力ルール：
- type は「事実の改変」「推測の追加」「欠落」のいずれか（この表記のまま）
- source_says / draft_says は該当箇所を短く抜き出す
- note は一言で端的に（30字以内。冗長な説明は不要）
- 問題が無ければ verdict="問題なし"、issues=[]。あれば verdict は端的に（例「事実改変あり」）

元データ（ソース）：
---
{sources}
---

整形された記録（ドラフト）：
---
{draft}
---
"""


def verify(sources: list[str], summary: str, details: str):
    """戻り値: (VerifyResult, meta)  meta = {model, prompt, raw_output}"""
    client = genai.Client()
    src = "\n".join(sources)
    draft = f"## サマリ\n{summary}\n\n## 詳細\n{details}"
    prompt = PROMPT_TMPL.format(sources=src, draft=draft)
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VerifyResult,
        ),
    )
    return resp.parsed, {"model": MODEL, "prompt": prompt, "raw_output": resp.text}
