"""Phase 1 検証(3回目): ユーザー作成Instruction（記録ルール）で整形

v1_readable_recording_principles_instruction.md を system_instruction として与え、
走り書きメモを整形する。原文保持は difflib(参考) と「言い回し保持チェック」で評価。
"""
import os
import difflib

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = "fieldnotekeeper"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

from google import genai
from google.genai import types

# ユーザー作成の記録ルール（Obsidian内）を読み込む
INSTRUCTION_PATH = (
    "/Users/takahashiken/Library/Mobile Documents/iCloud~md~obsidian/Documents/"
    "myBrain/Claude/Projects/2026-devops-ai-agent-hackathon-2026/"
    "Planning/Instruction/v1_readable_recording_principles_instruction.md"
)
with open(INSTRUCTION_PATH, encoding="utf-8") as f:
    INSTRUCTION = f.read()

# 前回と同じメモ（比較のため同条件）
MEMO = """6/3 樹脂キャップの耐久試験 サンプルA 3個
温度たぶん60℃くらい 湿度は測ってない
5000回開閉でA-1ひび A-2は8000回でヒンジ割れ A-3は1万回いけた
前回ロットより弱い気がする 材料ロット変えたから？要確認
写真撮った あとで貼る
次は温度下げて再試験 あと材料の証明書みる
山田さんにヒンジ形状の件聞く"""

TASK = f"""次の走り書きメモを、上記の記録ルールに従って整形した記録にしてください。

走り書きメモ：
---
{MEMO}
---"""

client = genai.Client()
resp = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=TASK,
    config=types.GenerateContentConfig(system_instruction=INSTRUCTION),
)
text = resp.text

print("=" * 56)
print("【整形後の記録（Instruction v1）】")
print("=" * 56)
print(text)

print("\n" + "=" * 56)
print("【原文保持の評価】")
print("=" * 56)
ratio = difflib.SequenceMatcher(None, MEMO, text).ratio()
print(f"原文一致率（difflib・参考値／順序変更で下がる）: {ratio:.0%}")

# 言い回し保持チェック：原文の特徴的な表現が残っているか
key_phrases = [
    "6/3", "たぶん60℃くらい", "測ってない", "ヒンジ割れ",
    "いけた", "弱い気がする", "あとで貼る", "山田さん",
]
print("\n言い回し保持チェック（原文の特徴語が残っているか）:")
kept = 0
for p in key_phrases:
    ok = p in text
    kept += ok
    print(f"  {'✅' if ok else '❌'} {p}")
print(f"  → 保持率: {kept}/{len(key_phrases)} ({kept/len(key_phrases):.0%})")
