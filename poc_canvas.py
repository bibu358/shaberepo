"""Phase C PoC（v2）：streamlit-image-coordinates でクリック位置 → PILでマーカー描画。

drawable-canvas が Streamlit 1.58 と非互換だったため、安定版のクリック方式に切替。
画像をクリック→その位置に丸＋番号。元画像はそのまま（オーバーレイ＝事実を変えない）。
実行: ./venv/bin/streamlit run poc_canvas.py
"""
import os

import streamlit as st
from PIL import Image, ImageDraw, ImageFont

try:
    from streamlit_image_coordinates import streamlit_image_coordinates
except ImportError:
    st.error(
        "streamlit-image-coordinates が未インストールです。\n"
        "ターミナルで: ./venv/bin/pip install streamlit-image-coordinates"
    )
    st.stop()


def _label_font(size: int):
    """ラベル用フォント（A,B,C…）。大きめに表示する。"""
    for p in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

st.title("🖍️ 画像注釈PoC（クリックでマーカー）")

up = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg", "webp"])
radius = st.slider("丸の大きさ", 10, 80, 30)

if up:
    # 画像が変わったらマーカーをリセット
    if st.session_state.get("img_name") != up.name:
        st.session_state.img_name = up.name
        st.session_state.markers = []

    img = Image.open(up).convert("RGB")
    disp_w = min(img.width, 700)
    disp = img.resize((disp_w, int(img.height * disp_w / img.width)))
    st.caption(f"{up.name} / 元サイズ {img.size}　画像をクリックすると丸＋番号がつきます")

    # 現在のマーカーを画像に描画（最新クリックは緑で強調）
    annotated = disp.copy()
    draw = ImageDraw.Draw(annotated)
    label_font = _label_font(36)
    n = len(st.session_state.markers)
    for i, (x, y) in enumerate(st.session_state.markers, 1):
        is_last = (i == n)
        color = "lime" if is_last else "red"
        w = 6 if is_last else 4
        r = radius + 8 if is_last else radius
        draw.ellipse([x - r, y - r, x + r, y + r], outline=color, width=w)
        draw.text((x + r + 4, y - r - 18), chr(64 + i), fill=color, font=label_font)  # A,B,C…

    # ★マーク描画済みの画像をクリック対象にする＝クリックとマークが「同じ1枚」に統合
    st.caption("画像をクリックすると、少し後に同じ画像へマークが反映されます")
    coords = streamlit_image_coordinates(annotated, key="annot")
    if coords:
        pt = (int(coords["x"]), int(coords["y"]))
        if pt not in st.session_state.markers:
            st.session_state.markers.append(pt)
            st.rerun()  # 再実行して同じ画像にマークを反映

    # クリックした位置の一覧（どこを指したか分かるように）
    if st.session_state.markers:
        last = st.session_state.markers[-1]
        st.success(f"✅ 最後にクリックした位置：マーカー{len(st.session_state.markers)}（x={last[0]}, y={last[1]}）")
        with st.expander(f"クリックした位置の一覧（{len(st.session_state.markers)}件）", expanded=True):
            for i, (x, y) in enumerate(st.session_state.markers, 1):
                st.write(f"- マーカー{i}：(x={x}, y={y})")

    if st.button("マーカーをクリア"):
        st.session_state.markers = []
        st.rerun()
