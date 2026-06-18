"""Phase 1: 最大リスク検証 ― 原文保持の品質＋欠落の質問

走り書きメモを Gemini で整形し、
(1) 自分の文がどれだけ原文保持されるか
(2) 不足・曖昧な点を質問として挙げられるか
を確認する。FieldNoteKeeper の核心が技術的に成立するかの見極め。
"""
import os
import difflib

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = "fieldnotekeeper"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

from google import genai
from google.genai import types
from pydantic import BaseModel


# --- 出力の型（整形本文＋質問リスト）---
class Record(BaseModel):
    formatted: str            # 整形後の記録（原文をなるべく保持）
    questions: list[str]      # 不足・曖昧な点の質問


# --- 検証用の走り書き（実務に近い実験メモ）---
MEMO = """6/3 樹脂キャップの耐久試験 サンプルA 3個
温度たぶん60℃くらい 湿度は測ってない
5000回開閉でA-1ひび A-2は8000回でヒンジ割れ A-3は1万回いけた
前回ロットより弱い気がする 材料ロット変えたから？要確認
写真撮った あとで貼る
次は温度下げて再試験 あと材料の証明書みる
山田さんにヒンジ形状の件聞く"""

PROMPT = f"""あなたは実験記録の整形担当です。以下の走り書きメモを、後から読みやすい記録に整えてください。

厳守ルール：
- 元の文章・数値・表現を「なるべくそのまま」使う。言い換え・要約をしない
- 勝手に情報を追加・推測で補完しない（書かれていないことは記録本文に書かない）
- 人が短時間で把握できる構成にする（冒頭に概要、その後に詳細）
- 不足/曖昧な情報は questions に質問として挙げる（本文には推測を入れない）

走り書きメモ：
---
{MEMO}
---
"""

client = genai.Client()
resp = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=PROMPT,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=Record,
    ),
)
rec: Record = resp.parsed

print("=" * 50)
print("【整形後の記録】")
print("=" * 50)
print(rec.formatted)

print("\n" + "=" * 50)
print("【AIからの質問（不足・曖昧な点）】")
print("=" * 50)
for i, q in enumerate(rec.questions, 1):
    print(f"{i}. {q}")

print("\n" + "=" * 50)
print("【原文保持の目安】")
print("=" * 50)
ratio = difflib.SequenceMatcher(None, MEMO, rec.formatted).ratio()
print(f"原文との文字一致率（参考値）: {ratio:.0%}")
print("※構成・見出しを足すと一致率は下がる。本質は『自分の文がそのまま残っているか』を目視で確認")
