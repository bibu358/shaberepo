"""画像注釈AI：クリック位置（A,B,C…）＋説明 → 各位置のマーク種類/ラベル/色を判断。

位置はユーザーのクリック座標を使う（AIに位置は当てさせない＝精度問題を回避）。
"""
from google import genai
from google.genai import types

from core.schema import MarkSpec, MarkPlan, ImagePlacements

MODEL = "gemini-2.5-flash"

PROMPT = """ユーザーが画像をクリックした位置（A, B, C…）に注釈マークをつけます。
クリック位置：
{points}

ユーザーの説明（音声の文字起こし）：
{instruction}

各位置（A, B, C…）について、つけるマークを返してください（位置は指定済みなので返さない）：
- index: 位置の番号（A=1, B=2, C=3 …）
- type: circle / arrow / rect
- label: 短いラベル（例 A:ヒビ）
- color: red / blue / lime など
- size: circleの半径の目安（40程度）
説明に該当が無い位置は label を空にしてよい。

また、この画像全体が何を示すかを "description" に1行で返してください（例：排水口まわりの状態）。
最優先：事実を変えない・推測で補完しない。
"""


def plan_marks(image_bytes: bytes, mime: str, points: list, instruction: str) -> MarkPlan:
    """MarkPlan（marks＋description）を返す。位置は points をそのまま使う。"""
    pts = "\n".join(f"{chr(64 + i)}: (x={x}, y={y})" for i, (x, y) in enumerate(points, 1))
    client = genai.Client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime),
            PROMPT.format(points=pts, instruction=instruction),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=MarkPlan
        ),
    )
    return resp.parsed


PLACE_PROMPT = """記録本文の中で、各画像が最も関連する行を1つ選び、その行の後ろに画像を配置します。
**本文は変更しません（位置だけ選ぶ）。**

各画像について返す：
- n: 画像番号
- after_line: その画像を挿入する「本文の行」を**本文からそのまま**抜き出す（最も関連する1行）。適切な行が無ければ空文字

画像：
{infos}

記録本文：
---
{details}
---
"""


def place_images(details: str, image_infos: list) -> list:
    """各画像を details のどの行の後に置くかを返す（位置のみ・本文は変えない）。
    image_infos: [{"n": 1, "description": "..."}...]
    """
    infos = "\n".join(f"画像{d['n']}: {d['description']}" for d in image_infos)
    client = genai.Client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=PLACE_PROMPT.format(infos=infos, details=details),
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=ImagePlacements
        ),
    )
    return resp.parsed.items
