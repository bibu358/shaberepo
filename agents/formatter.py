"""整形AI：箇条書きメモ → サマリ＋詳細（ソースは原文をそのまま使う）
検証で問題が出たら refine_record で修正する。
"""
from google import genai
from google.genai import types

from core.schema import Record, FormatterOutput
from core.prompts import DEFAULT_RULES, DEFAULT_SUMMARY_FORMAT

MODEL = "gemini-2.5-flash"

PROMPT_TMPL = """あなたは実験・現場メモの整形担当です。箇条書きの走り書きメモから、後から読みやすい記録を作ります。

{rules}

出力：
- title：記録の題名を1行で（例：日付＋対象＋試験名）
- {summary_format}
- details：見出し＋箇条書きで構造化した本文。内容に応じて「実施内容 / 事実 / 解釈 / 次にやること」などに分ける
- did：やったことを1行で（一覧用の短い要約）
- result：結果を1行で（一覧用の短い要約）

メモ：
---
{memo}
---
"""

REFINE_TMPL = """前回の整形結果に「事実の改変」が見つかりました。指摘された箇所だけを、元データ（ソース）に忠実に直してください。

【最重要】指摘された箇所【以外】は一切変更しないこと。
- サマリ・詳細の他の文、見出し、構成、言い回し、箇条書きの並びはそのまま維持する
- 直すのは指摘された事実部分だけ。新たな要約・追記・整え直しはしない

元データ（ソース）：
---
{sources}
---

前回の整形結果（これをベースに、指摘箇所だけ直す）：
[サマリ]
{summary}
[詳細]
{details}

直すべき事実の改変（この箇所だけ修正）：
{issues}
"""


def _gen(prompt: str):
    """parsed結果と生出力テキストを返す"""
    client = genai.Client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FormatterOutput,
        ),
    )
    return resp.parsed, resp.text


def format_record(memo_lines: list[str], work_date=None, author=None, rules=None, summary_format=None):
    """戻り値: (Record, meta)  meta = {model, prompt, raw_output}
    rules / summary_format を渡すとそれを使う（UIで調整した値）。無ければデフォルト。
    """
    memo = "\n".join(memo_lines)
    prompt = PROMPT_TMPL.format(
        rules=rules or DEFAULT_RULES,
        summary_format=summary_format or DEFAULT_SUMMARY_FORMAT,
        memo=memo,
    )
    out, raw = _gen(prompt)
    rec = Record(
        title=out.title, summary=out.summary, sources=memo_lines, details=out.details,
        did=out.did, result=out.result, work_date=work_date, author=author,
    )
    return rec, {"model": MODEL, "prompt": prompt, "raw_output": raw}


def refine_record(memo_lines: list[str], rec: Record, issues):
    """事実改変の指摘箇所だけを直す（他は変えない）。戻り値: (Record, meta)"""
    issues_text = "\n".join(
        f"- 元:「{i.source_says}」→ ドラフト:「{i.draft_says}」（{i.note}）"
        for i in issues
    )
    prompt = REFINE_TMPL.format(
        sources="\n".join(memo_lines),
        summary=rec.summary,
        details=rec.details,
        issues=issues_text,
    )
    out, raw = _gen(prompt)
    rec2 = Record(
        title=out.title, summary=out.summary, sources=memo_lines, details=out.details,
        did=out.did, result=out.result, work_date=rec.work_date, author=rec.author,
    )
    return rec2, {"model": MODEL, "prompt": prompt, "raw_output": raw}
