"""① 文字起こしAI：音声 → transcript（責務はこれだけ）。

transcript は以後の全工程の唯一のソース（不変）。保存しておけば
テンプレ調整・追加指示の再整形時に音声を再処理しなくてよい。
"""
from google import genai
from google.genai import types

from core.schema import TranscriptOutput

MODEL = "gemini-2.5-flash"

PROMPT = """この音声は、設計者が実験・現場作業の内容を口頭で報告したものです（日本語）。
そのまま文字起こししてください。

- フィラー（「えー」「あのー」等）は除いてよい。事実・数値・固有名詞・サンプルID（例 A-3）は正確にそのまま
- 聞き取れない箇所は [不明] と書く
- 文には適宜句読点を打ち、話題の切れ目で空行を入れて段落に分ける
- 要約・言い換え・補完はしない（文字起こしのみ。内容の追加・削除をしない）
"""


def transcribe(audio_bytes: bytes, mime: str) -> str:
    """音声 → 文字起こし全文（段落分けあり）"""
    client = genai.Client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=audio_bytes, mime_type=mime), PROMPT],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TranscriptOutput,
        ),
    )
    return resp.parsed.transcript
