"""Phase 1 検証(2回目): 抽象指示 vs 具体手順 の比較

同じ走り書きメモを2つの方針のプロンプトで整形し、結果を並べて比較する。
- 方針A：抽象指示（原則・ゴールを与える）
- 方針B：具体手順（ステップを与える）
要件：まとめ／When-Who-Where統一／Fact-解釈-ネクストアクション区別／箇条書き／原文保持＋最小補足
"""
import os
import difflib

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = "fieldnotekeeper"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

from google import genai

# 前回と同じメモ（比較のため同条件）
MEMO = """6/3 樹脂キャップの耐久試験 サンプルA 3個
温度たぶん60℃くらい 湿度は測ってない
5000回開閉でA-1ひび A-2は8000回でヒンジ割れ A-3は1万回いけた
前回ロットより弱い気がする 材料ロット変えたから？要確認
写真撮った あとで貼る
次は温度下げて再試験 あと材料の証明書みる
山田さんにヒンジ形状の件聞く"""

# 方針A：抽象指示（原則ベース）
PROMPT_A = """あなたは実験・現場作業の記録を整える編集者です。
走り書きメモを、後から読みやすく二次活用できる記録に整えてください。

# 目的
書いた人の言葉を尊重しつつ、後から読む人が短時間で把握できる記録にする。

# 原則
1. 構成：見出しで構造化し、冒頭に「まとめ」を置く
2. メタ情報：When（いつ）/ Who（誰が）/ Where（どこで）を統一フォーマットで明示する（不明なら「未記載」）
3. 区別：Fact（事実）/ 解釈（推測・所感）/ ネクストアクション（行動案）を明確に分ける
4. 形式：本文は箇条書き
5. 原文尊重：元の表現・用語・言い回しをできる限りそのまま使う。言い換え・要約・脚色はしない。意味が通る文として情報が不足する場合のみ、元の表現に沿って最小限の補足をしてよい"""

# 方針B：具体手順（手続きベース）
PROMPT_B = """あなたは実験・現場作業の記録を整える編集者です。次の手順に従って走り書きメモを記録に変換してください。

# 手順
Step1. メタ情報を抽出する。無ければ「未記載」とする：
  - When（日時） / Who（担当者） / Where（場所）
Step2. メモの各文を、内容で3つに仕分ける：
  - Fact（観測・実施した事実）
  - 解釈（推測・所感。「〜な気がする」等）
  - ネクストアクション（今後やること・確認事項）
Step3. 各文を箇条書きにする。元の表現・用語・言い回しをそのまま使う。言い換え・要約はしない。意味が通る文として情報が不足する場合のみ、元の表現に沿って最小限補う
Step4. 冒頭に2〜3行の「まとめ」を書く（何の記録で、要点は何か）
Step5. 次の見出し構成（マークダウン）で出力する：
  ## まとめ
  ## 基本情報（When / Who / Where）
  ## Fact（事実）
  ## 解釈
  ## ネクストアクション"""

MEMO_BLOCK = f"\n\n走り書きメモ：\n---\n{MEMO}\n---\n"

client = genai.Client()


def run(name, instruction):
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=instruction + MEMO_BLOCK,
    )
    text = resp.text
    print("\n" + "=" * 56)
    print(f"  {name}")
    print("=" * 56)
    print(text)
    ratio = difflib.SequenceMatcher(None, MEMO, text).ratio()
    print(f"\n[原文一致率(参考): {ratio:.0%}]")


run("方針A：抽象指示（原則ベース）", PROMPT_A)
run("方針B：具体手順（手続きベース）", PROMPT_B)
