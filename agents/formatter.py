"""整形AI：箇条書きメモ → サマリ＋詳細（ソースは原文をそのまま使う）
検証で問題が出たら refine_record で修正する。
"""
from google import genai
from google.genai import types

from core.schema import Record, FormatterOutput

MODEL = "gemini-2.5-flash"

_RULES = """最優先（厳守）：
- 事実を変えない（数値・結果・合否・状態を改変しない）
- 推測で補完しない（書いていないことは書かない。不明なことは不明のまま）
- 元の表現・用語・言い回しをできる限りそのまま使う（言い換え・脚色をしない）"""

_SUMMARY_FORMAT = """summary は以下の構成で、各項目の中身を「インデントした箇条書き」で端的に書く
（敬語なし・である調/体言止め。文章でつなげず、要点を箇条書きで並べる）：
- 日付・題名：（1行で）
- 背景・目的・やったこと：
    - 箇条書き
- 結果要約：
    - 箇条書き
- 考察・ネクストアクション：
    - 箇条書き

サマリは要点を端的に。詳しい内容は details 側に書く。事実は変えないが、自然な要約・整理はしてよい。"""

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


def format_record(memo_lines: list[str], work_date=None, author=None):
    """戻り値: (Record, meta)  meta = {model, prompt, raw_output}"""
    memo = "\n".join(memo_lines)
    prompt = PROMPT_TMPL.format(rules=_RULES, summary_format=_SUMMARY_FORMAT, memo=memo)
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
