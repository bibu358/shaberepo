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


# ---- ③ 検証AI（マルチモーダル版・2026-07-02再設計）----

PROMPT_V2 = """あなたは記録の監査者です。整形された記録がソースに忠実かを検証します。

【判定の物差し（すべての判断はこれ1つで行う）】
「ソースを読んだ人」と「この記録を読んだ人」が、事実について異なる認識を持つか？
- 持つ → 指摘する
- 持たない（言い回し・構成・要約の違いにすぎない）→ 指摘しない

【指摘の3分類（軸＝ソースの情報が 変わった／足された／欠けた）】
- 事実の改変（変わった）：ソースの情報が別の内容になっている。数値・単位・固有名詞・合否・状態・
  帰属（誰が言った/やったか）の変化のほか、確度の変化（話者の推測が断定になっている等）や、
  意味を変える言い換え・用語の置き換えを含む
- 推測の追加（足された）：ソースに無い情報・用語が加えられ、読者の認識に影響しうる。
  事実として書かれているかどうかは問わない
  （「〜と推測される」と明示された整理、「◯◯からの説明」内の伝聞は対象外）
- 欠落（欠けた）：ソースにある事実のうち、読者の判断や行動に影響しうるものが記録に無い

【ソース＝以下のすべて。これらに基づく記載は問題にしない】
- 文字起こし（下記）
- 画像（画像1, 画像2…・マーク位置を含む）
- 作業日：{work_date}（ユーザーがUIで指定した値）
- ユーザーの追加指示（下記）
- 補足テキスト（下記）

【自己チェック】
各指摘を出す前に自問する：「この差異を放置すると、読者の理解や判断が変わるか？」
— No なら、その指摘は出力しない。

【出力ルール】
- type は「事実の改変」「推測の追加」「欠落」のいずれか（この表記のまま）
- section は指摘箇所のセクション名（例：プロパティ／サマリ／背景・目的／やったこと／結果／考察／結論・判断／ネクストアクション／キャプション）
- source_says / draft_says は該当箇所を短く抜き出す。note は一言（30字以内）
- 問題が無ければ verdict="問題なし"、issues=[]

ユーザーの追加指示：
---
{extra}
---

補足テキスト：
---
{ref}
---

文字起こし（ソース）：
---
{sources}
---

整形された記録（ドラフト）：
---
{draft}
---
"""


def verify_record(transcript: str, draft_text: str, images: list = None,
                  work_date=None, extra_instruction: str = "", ref_text: str = ""):
    """新フロー用：transcript＋画像＋作業日＋追加指示＋補足テキスト vs 構造化記録。戻り値: VerifyResult"""
    prompt = PROMPT_V2.format(
        sources=transcript, draft=draft_text,
        work_date=work_date or "（未指定）",
        extra=extra_instruction.strip() or "（なし）",
        ref=(ref_text or "").strip() or "（なし）",
    )
    contents = [prompt]
    for im in images or []:
        contents.append(f"画像{im['n']}（ファイル名: {im['filename']}）")
        contents.append(types.Part.from_bytes(data=im["bytes"], mime_type=im.get("mime", "image/png")))
    client = genai.Client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VerifyResult,
        ),
    )
    return resp.parsed
