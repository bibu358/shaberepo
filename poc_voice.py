"""Phase A PoC：音声 → 文字起こし＋実験フォーマット整形（Gemini音声入力）

音声がちゃんと文字起こしされるか／専門用語・数値の精度／実験記録に整形されるか を確認する。

使い方:
  ./venv/bin/python poc_voice.py <音声ファイルのパス>
  例: ./venv/bin/python poc_voice.py ~/Desktop/memo.m4a
"""
import os
import sys

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = "fieldnotekeeper"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

from google import genai
from google.genai import types
from pydantic import BaseModel

MODEL = "gemini-2.5-flash"

MIME = {
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
    ".aac": "audio/aac", ".ogg": "audio/ogg", ".flac": "audio/flac",
}

PROMPT = """この音声は、設計者が実験・現場作業の内容を口頭で報告したものです（日本語）。
次を行ってください。

- transcript：音声をそのまま文字起こし。フィラー（「えー」「あのー」等）は除いてよいが、
  事実・数値・固有名詞・サンプルID（例 A-3）はそのまま正確に。聞き取れない箇所は [不明] と書く。
- title：記録の題名を1行で（日付＋対象＋試験名など）
- summary：要点を箇条書きで端的に
- details：見出し＋箇条書きで構造化（実施内容 / 事実 / 解釈 / 次にやること など）

最優先（厳守）：事実を変えない・推測で補完しない・聞き取れないものは [不明]。
"""


class VoiceRecord(BaseModel):
    transcript: str   # 文字起こし全文（＝ソース/原文）
    title: str
    summary: str
    details: str


def main(path: str):
    ext = os.path.splitext(path)[1].lower()
    mime = MIME.get(ext)
    if not mime:
        print(f"未対応の拡張子: {ext}（対応: {', '.join(MIME)}）")
        sys.exit(1)

    with open(path, "rb") as f:
        audio = f.read()
    print(f"音声: {path}（{len(audio)/1024:.0f} KB, {mime}）\n整形中…\n")

    client = genai.Client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=audio, mime_type=mime), PROMPT],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VoiceRecord,
        ),
    )
    r = resp.parsed

    def block(title, body):
        print("=" * 56)
        print(title)
        print("=" * 56)
        print(body)
        print()

    block("■ 文字起こし（transcript＝ソース）", r.transcript)
    block("■ 題名", r.title)
    block("■ サマリ", r.summary)
    block("■ 詳細", r.details)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: ./venv/bin/python poc_voice.py <音声ファイルのパス>")
        sys.exit(1)
    main(sys.argv[1])
