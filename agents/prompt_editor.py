"""プロンプト修正AI（S13）：ユーザーの意図 → 編集可能プロンプトへの変更提案。

提案は差分レビューを経て人が適用する（適用し、保存するまで何も変わらない）。
出荷時デフォルト（DEFAULT_TEMPLATES）は変更しない＝適用先は現在の編集値のみ。
"""
from google import genai
from google.genai import types
from pydantic import BaseModel

MODEL = "gemini-2.5-flash"


class PromptEdit(BaseModel):
    """1項目分の変更提案"""
    item: str      # 対象項目キー（title / properties / summary / details / style / caption）
    new_text: str  # その項目の新しい全文
    reason: str    # 変更理由（1行）


class PromptEdits(BaseModel):
    edits: list[PromptEdit]


PROMPT = """あなたは、記録整形AIのプロンプトを整備する担当です。
ユーザーの意図を、編集可能なプロンプト項目への変更として反映してください。

ルール：
- 変更するのは、意図の反映に必要な項目だけ（変更しない項目は返さない）
- 各項目は全文を返す。意図に関係しない部分は、**改行・箇条書き・インデントの書式も含めて**
  元の文を一字一句そのまま保つ（複数行の文章を1行に潰さない。変更箇所以外は改行位置も元のまま）
- 固定ルール（下記・変更不可）と矛盾する指示は書かない
- item は次のキーのいずれか：{keys}
- reason は変更理由を1行で

編集可能な項目の現在値：
{current}

固定ルール（参考・変更不可）：
---
{fixed}
---

ユーザーの意図：
{intent}
"""


def propose_prompt_edits(current: dict, intent: str, fixed_text: str, labels: dict) -> list:
    """変更提案のリストを返す（変更が無い・不正なitemは除外）"""
    cur = "\n\n".join(f"### {k}（{labels.get(k, k)}）\n{v}" for k, v in current.items())
    prompt = PROMPT.format(keys=", ".join(current.keys()), current=cur,
                           fixed=fixed_text, intent=intent.strip())
    client = genai.Client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=PromptEdits,
        ),
    )
    edits = resp.parsed.edits if resp.parsed else []
    return [e for e in edits
            if e.item in current and e.new_text.strip() and e.new_text != current[e.item]]
