"""Gemini疎通テスト（Vertex AI経由・ADC認証）

ADKに入る前に「ローカルからGeminiが呼べるか」を最小確認する。
"""
import os

# Vertex AI 経由で Gemini を使う設定（ADCで認証）
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = "fieldnotekeeper"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

from google import genai

client = genai.Client()
resp = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="こんにちは。あなたが何のモデルか、一言で日本語で教えてください。",
)
print("=== Geminiの返答 ===")
print(resp.text)
