"""検証AI（事実ガード）の小検証

元データ（ソース）と整形済み記録（ドラフト）を比較し、
ドラフトが元データと矛盾・逸脱している箇所を検出できるかを確認する。
ドラフトには Phase1 v1 の出力（A-3が「いけた」→「破損」に改変された版）を使う。
→ この事実改変を検知できれば、検証AI（事実ガード）が成立。
"""
import os

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = "fieldnotekeeper"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

from google import genai
from google.genai import types
from pydantic import BaseModel

# 元データ（ソース＝原文の走り書き）
SOURCE = """6/3 樹脂キャップの耐久試験 サンプルA 3個
温度たぶん60℃くらい 湿度は測ってない
5000回開閉でA-1ひび A-2は8000回でヒンジ割れ A-3は1万回いけた
前回ロットより弱い気がする 材料ロット変えたから？要確認
写真撮った あとで貼る
次は温度下げて再試験 あと材料の証明書みる
山田さんにヒンジ形状の件聞く"""

# 整形済み記録（ドラフト＝Phase1 v1の出力。A-3が「破損」に改変されている）
DRAFT = """- 日付・題名：20XX/06/03｜樹脂キャップA ヒンジ開閉耐久試験（高温）
- 目的：樹脂キャップAのヒンジ開閉耐久性を確認する。
- 対象・条件：樹脂キャップA（サンプル3個：A-1, A-2, A-3）、開閉耐久試験機使用、試験温度：約60℃（湿度未測定）。
- 結果要約：全サンプルで10,000回以下の開閉で破損発生。前回ロットと比較し耐久性が低い傾向を示唆。
## 実施内容
- 6月3日に樹脂キャップAのサンプル3個に対し、開閉耐久試験を実施した。
- 試験中、目視にて破損状況を観察し、都度写真撮影を行った。
## 事実
- A-1：5,000回開閉時にヒンジ部にひび割れが発生した。
- A-2：8,000回開閉時にヒンジ部が割れて破損した。
- A-3：10,000回開閉時にヒンジ部が割れて破損した。
- （撮影した破損箇所の写真は後日添付予定。）
## 解釈
- 今回のロットは前回ロットと比較してヒンジ開閉耐久性が低い可能性がある。
- 材料ロットの変更が耐久性低下に影響している可能性が考えられる。
## 次にやること
- 低温条件での開閉耐久再試験を実施する。
- 材料証明書を確認する。
- 山田氏にヒンジ形状をヒアリングする。"""


class Issue(BaseModel):
    type: str          # "事実改変" / "推測の追加" / "欠落"
    source_says: str   # 元データでの記述
    draft_says: str    # ドラフトでの記述
    note: str          # 説明


class VerifyResult(BaseModel):
    verdict: str       # "問題あり" / "問題なし"
    issues: list[Issue]


PROMPT = f"""あなたは記録の検証担当です。「元データ（ソース）」と「整形された記録（ドラフト）」を厳密に比較し、
ドラフトが元データと矛盾・逸脱している箇所をすべて指摘してください。

特に検出すべき点：
- 事実の改変：数値・結果・合否・状態が元データと変わっている（例：耐えた→破損 など正反対の改変は最重要）
- 推測の追加：元データに書かれていない情報が、推測や補完で勝手に足されている
- 欠落：元データにある重要な事実がドラフトから抜けている

元データ（ソース）：
---
{SOURCE}
---

整形された記録（ドラフト）：
---
{DRAFT}
---
"""

client = genai.Client()
resp = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=PROMPT,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=VerifyResult,
    ),
)
res: VerifyResult = resp.parsed

print("=" * 56)
print(f"判定: {res.verdict}")
print("=" * 56)
for i, x in enumerate(res.issues, 1):
    print(f"\n[{i}] {x.type}")
    print(f"  元データ : {x.source_says}")
    print(f"  ドラフト : {x.draft_says}")
    print(f"  説明     : {x.note}")
