"""PoC：ユーザーのクリック位置 ＋ 指示 → AIがマーク種類/ラベルを判断 → プログラムが描画。

位置はユーザーのクリック座標を使う（AIに位置は当てさせない＝精度問題を回避）。
AIの役割：各クリック番号に「どんなマーク（種類・ラベル・色）」をつけるか判断。
実行: ./venv/bin/streamlit run poc_ai_layer.py
"""
import io
import os

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = "fieldnotekeeper"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont

try:
    from streamlit_image_coordinates import streamlit_image_coordinates
except ImportError:
    st.error("未インストール: ./venv/bin/pip install streamlit-image-coordinates")
    st.stop()

MODEL = "gemini-2.5-flash"


def _jp_font(size: int):
    """日本語フォントを返す（無ければデフォルト）。本番は Noto を同梱予定。"""
    candidates = [
        "assets/NotoSansJP-Regular.ttf",  # 本番同梱用（あれば優先）
        "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


class MarkSpec(BaseModel):
    index: int          # クリック番号（1始まり）。位置はこの番号のクリック座標を使う
    type: str           # circle / arrow / rect
    label: str = ""
    color: str = "red"
    size: int = 40


class MarkPlan(BaseModel):
    marks: list[MarkSpec]


PROMPT = """ユーザーが画像をクリックした位置（番号付き）に、注釈マークをつけます。
クリック位置：
{points}

ユーザー指示：{instruction}

各位置（A, B, C…）について、つけるマークを返してください（位置は指定済みなので返さない）：
- index: 位置の番号（A=1, B=2, C=3 …）
- type: circle / arrow / rect
- label: 短いラベル（例 ①ヒビ）
- color: red / blue / lime など
- size: circleの半径の目安（40程度）
"""

st.title("🧪 AIレイヤーPoC（クリック位置＋指示 → AIがマーク判断）")
up = st.file_uploader("画像", type=["png", "jpg", "jpeg", "webp"])

if up:
    if st.session_state.get("img") != up.name:
        st.session_state.img = up.name
        st.session_state.pts = []

    img = Image.open(up).convert("RGB")
    disp_w = min(img.width, 700)
    disp = img.resize((disp_w, int(img.height * disp_w / img.width)))

    # クリック済みの番号を描いた画像をクリック対象に（1枚に統合）
    base = disp.copy()
    bd = ImageDraw.Draw(base)
    bfont = _jp_font(32)
    for i, (x, y) in enumerate(st.session_state.pts, 1):
        bd.ellipse([x - 6, y - 6, x + 6, y + 6], fill="orange")
        bd.text((x + 10, y - 16), chr(64 + i), fill="orange", font=bfont)  # A,B,C…

    st.caption("画像をクリックして位置を指定（番号がつく）。その後、指示を書いてAIに判断させます")
    coords = streamlit_image_coordinates(base, key="c")
    if coords:
        pt = (int(coords["x"]), int(coords["y"]))
        if pt not in st.session_state.pts:
            st.session_state.pts.append(pt)
            st.rerun()

    st.write("クリック位置:", [f"{chr(64 + i)}: {p}" for i, p in enumerate(st.session_state.pts, 1)])
    if st.button("クリックをクリア"):
        st.session_state.pts = []
        st.rerun()

    instruction = st.text_area(
        "指示（クリック番号で説明）",
        placeholder="例：Aにヒビが入った（赤い丸）、Bはヒンジが割れた（矢印で示して）",
    )

    if st.session_state.pts and instruction and st.button("AIにマーク判断させて描画", type="primary"):
        points = "\n".join(f"{chr(64 + i)}: (x={x}, y={y})" for i, (x, y) in enumerate(st.session_state.pts, 1))
        buf = io.BytesIO()
        disp.save(buf, format="PNG")
        with st.spinner("AIが判断中…"):
            client = genai.Client()
            resp = client.models.generate_content(
                model=MODEL,
                contents=[
                    types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png"),
                    PROMPT.format(points=points, instruction=instruction),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", response_schema=MarkPlan
                ),
            )
            plan = resp.parsed

        st.write("AIの判断（JSON）:", [m.model_dump() for m in plan.marks])

        out = disp.copy()
        draw = ImageDraw.Draw(out)
        font = _jp_font(22)
        for m in plan.marks:
            if not (1 <= m.index <= len(st.session_state.pts)):
                continue
            x, y = st.session_state.pts[m.index - 1]  # 位置はクリック座標を使う
            c = m.color or "red"
            s = m.size or 40
            if m.type == "circle":
                draw.ellipse([x - s, y - s, x + s, y + s], outline=c, width=5)
            elif m.type == "rect":
                draw.rectangle([x - s, y - s, x + s, y + s], outline=c, width=5)
            elif m.type == "arrow":
                draw.line([x - s * 2, y + s * 2, x, y], fill=c, width=5)  # 左下→クリック点
                draw.ellipse([x - 7, y - 7, x + 7, y + 7], fill=c)
            if m.label:
                draw.text((x + s, y - s), m.label, fill=c, font=font)

        st.image(out, caption="AI判断でマークした画像（位置＝クリック座標）")
