"""画像へのマーカー描画（元画像は保持してレイヤーを重ねる）。

- draw_click_markers：クリック位置に A,B,C… の印（位置確認用）
- draw_ai_marks：AIのマーク計画（circle/arrow/rect＋ラベル）を描画
"""
import os

from PIL import Image, ImageDraw, ImageFont


def _font(size: int):
    for p in [
        "assets/NotoSansJP-Regular.ttf",  # 本番同梱用（あれば優先）
        "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


# ユーザーが選べる色（名前 → 描画色）
PALETTE = {
    "赤": "#FF3B30",
    "青": "#0533FF",
    "黄": "#FFCC00",
    "黒": "#000000",
    "ピンク": "#FE40FF",  # 明るいピンク（ユーザー指定）
}


def draw_user_marks(img: Image.Image, marks: list, scale: float = 1.0) -> Image.Image:
    """ユーザーの印（丸 or 矢印・色付き・A,B,C…ラベル）を描画する。
    marks: [{"x", "y", "tool"("丸"/"矢印"), "color"(hex), ...}]（座標は表示画像基準）
    矢印は左下から右上へ伸び、クリック位置が終点（矢の先）。
    scale: 元解像度の画像に描く場合の倍率（座標・サイズを拡大。Notion保存の解像度維持用）
    """
    out = img.convert("RGB").copy()
    d = ImageDraw.Draw(out)
    f = _font(max(12, int(36 * scale)))
    w = max(3, int(6 * scale))
    for i, m in enumerate(marks, 1):
        x, y = int(m["x"] * scale), int(m["y"] * scale)
        color = m.get("color", "#FF3B30")
        label = chr(64 + i)
        if m.get("tool") == "矢印":
            a = int(45 * scale)
            hl, hw_ = 22 * scale, 10 * scale  # 矢じり（長さ・半幅）。塗り三角形＝先端が尖る
            u = 0.7071  # 45度成分（左下→右上・先端がクリック位置）
            bx, by = x - u * hl, y + u * hl   # 矢じりの付け根中心
            d.line([x - a, y + a, bx, by], fill=color, width=w)
            d.polygon([(x, y),
                       (bx + u * hw_, by + u * hw_),
                       (bx - u * hw_, by - u * hw_)], fill=color)
            d.text((x - a - int(30 * scale), y + a + int(4 * scale)),
                   label, fill=color, font=f)  # ラベルは矢印の根本側
        else:  # 丸
            r = int(40 * scale)
            d.ellipse([x - r, y - r, x + r, y + r], outline=color, width=w)
            d.text((x + r + int(6 * scale), y - r - int(10 * scale)), label, fill=color, font=f)
    return out


def draw_click_markers(img: Image.Image, points: list) -> Image.Image:
    """クリック位置に A,B,C… の印（赤）。位置確認用。"""
    out = img.convert("RGB").copy()
    d = ImageDraw.Draw(out)
    f = _font(36)
    for i, (x, y) in enumerate(points, 1):
        d.ellipse([x - 6, y - 6, x + 6, y + 6], fill="red")
        d.text((x + 10, y - 18), chr(64 + i), fill="red", font=f)
    return out


def draw_ai_marks(img: Image.Image, points: list, marks: list) -> Image.Image:
    """AIのマーク計画（dictのlist）を描画。位置は points[index-1] を使う。"""
    out = img.convert("RGB").copy()
    d = ImageDraw.Draw(out)
    f = _font(28)
    for m in marks:
        idx = int(m.get("index", 0))
        if not (1 <= idx <= len(points)):
            continue
        x, y = points[idx - 1]
        c = m.get("color") or "red"
        s = int(m.get("size") or 40)
        t = m.get("type", "circle")
        if t == "circle":
            d.ellipse([x - s, y - s, x + s, y + s], outline=c, width=5)
        elif t == "rect":
            d.rectangle([x - s, y - s, x + s, y + s], outline=c, width=5)
        elif t == "arrow":
            d.line([x - s * 2, y + s * 2, x, y], fill=c, width=5)  # 左下→クリック点
            d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=c)
        label = m.get("label", "")
        if label:
            d.text((x + s, y - s), label, fill=c, font=f)
    return out
