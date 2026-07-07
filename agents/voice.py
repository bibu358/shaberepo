"""音声整形AI：音声 → 文字起こし＋実験フォーマット整形（Gemini音声入力）。

1回のAPIで「文字起こし(transcript) ＋ 記録整形」を行う。
transcript は Record.sources（原文保持）に充てる。
"""
from google import genai
from google.genai import types

from core.schema import Record, VoiceOutput
from core.prompts import DEFAULT_RULES, DEFAULT_SUMMARY_FORMAT

MODEL = "gemini-2.5-flash"

PROMPT_TMPL = """この音声は、設計者が実験・現場作業の内容を口頭で報告したものです（日本語）。
作業日は {work_date} です。音声に年月日が無ければこの作業日を使い、**勝手に別の年を推測しない**。

{rules}

次を行ってください。
- transcript：音声をそのまま文字起こし。フィラー（「えー」「あのー」等）は除いてよいが、事実・数値・固有名詞・サンプルID（例 A-3）はそのまま正確に。聞き取れない箇所は [不明]
- title：記録の題名を1行で
- {summary_format}
- details：見出し＋箇条書きで構造化（実施内容 / 事実 / 解釈 / 次にやること など）
- did：やったことを1行で（一覧用の短い要約）
- result：結果を1行で（一覧用の短い要約）

※ summary と details は **markdown形式のプレーンテキスト**（見出し ### ・箇条書き -）で書くこと。
　 JSON・辞書・配列のような構造にはしない。1つの読みやすいテキストにする。

最優先（厳守）：事実を変えない・推測で補完しない（特に未発話の日付・数値）・聞き取れないものは [不明]。
"""


def format_from_audio(audio_bytes: bytes, mime: str, work_date=None, rules=None, summary_format=None):
    """音声 → (Record, meta)。transcript を sources に入れる。"""
    prompt = PROMPT_TMPL.format(
        work_date=work_date or "（不明）",
        rules=rules or DEFAULT_RULES,
        summary_format=summary_format or DEFAULT_SUMMARY_FORMAT,
    )
    client = genai.Client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=audio_bytes, mime_type=mime), prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VoiceOutput,
        ),
    )
    out: VoiceOutput = resp.parsed
    rec = Record(
        title=out.title,
        summary=out.summary,
        sources=[out.transcript],  # 文字起こし全文＝原文保持
        details=out.details,
        did=out.did,
        result=out.result,
        work_date=work_date,
    )
    return rec, {"model": MODEL, "prompt": prompt, "raw_output": resp.text}
