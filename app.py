"""しゃべれぽAI Streamlit UI（音声＋画像 → 構造化記録 → Notion）

フロー（2026-07-02 AIフロー再設計）：
  ① 文字起こしAI：音声 → transcript（保存。修正時は音声を再処理しない）
  ② 整形AI（マルチモーダル）：transcript＋画像＋参考情報＋プロンプト設定 → 構造化記録＋キャプション＋配置
  ③ 検証AI（マルチモーダル）：transcript＋画像＋作業日＋追加指示＋参考情報 vs 記録
  ④ 修正AI：事実の改変を自動修復 → 再検証（最大2周）／ユーザー指示は revise（指示以外変えない）

UI：サイドバーで画面切替（記録作成／プロンプト設定）。
記録作成は2列（左＝ユーザーによるインプット、右＝AIによる出力）。列ごとに独立スクロール・1画面収まり。
AI処理は「2段階実行」：ボタン押下→全ウィジェットをdisabledで再描画→処理実行（誤操作による中断を防ぐ）。
整形完了後も入力はロック（見出しグレー）し、編集ボタンで解除。AIの進捗は右列（検証結果の箱）に表示。
実行: ./venv/bin/streamlit run app.py
"""
import difflib
import io
import os
import re
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()  # .env から NOTION_TOKEN / NOTION_DATABASE_ID / DRIVE_* を読む
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = "fieldnotekeeper"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw, ImageFont

from agents.transcribe import transcribe
from agents.composer import (compose_record, refine_structured, revise_structured,
                             FIXED_DISPLAY)
from agents.prompt_editor import propose_prompt_edits
from agents.verifier import verify_record
from core.render import render_structured
from core.diff import diff_section_lines
from core.prompts import (load_prompts, save_prompts, DEFAULT_TEMPLATES,
                          TEMPLATE_LABELS, TEMPLATE_HELP)
from core.draw import draw_user_marks, PALETTE
from core.runlog import save_run
from core import usage
from tools.notion_tools import save_structured

try:
    from streamlit_image_coordinates import streamlit_image_coordinates
    HAS_COORDS = True
except ImportError:
    HAS_COORDS = False


# ---- 画像ヘルパー ----

def _fit(img: Image.Image, max_w: int = 520, max_h: int = 520) -> Image.Image:
    """上限内に縮小（拡大はしない）"""
    scale = min(max_w / img.width, max_h / img.height, 1.0)
    return img.resize((int(img.width * scale), int(img.height * scale)))


def _preview_img(img: Image.Image, max_h: int = 150) -> Image.Image:
    """プレビュー用の縦幅制限"""
    scale = min(max_h / img.height, 1.0)
    return img.resize((int(img.width * scale), int(img.height * scale)))


def _thumb_sel(f, selected: bool) -> Image.Image:
    """サムネ（選択中は赤枠）"""
    im = Image.open(f).convert("RGB")
    w = 88
    im = im.resize((w, int(im.height * w / im.width)))
    if selected:
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, im.width - 1, im.height - 1], outline="red", width=5)
    return im


def _scroll_left_to_bottom():
    """左列を最下部へスクロール（作成開始・完了時のメッセージが画面外で気づけない問題の対策）。
    Streamlitに標準機能が無いため、iframe内スクリプトから親ページのDOMを操作する。
    """
    seq = st.session_state["scroll_seq"] = st.session_state.get("scroll_seq", 0) + 1
    components.html(f"""<script>
    (function() {{  // seq={seq}: 毎回コードを変えてiframe再生成→スクリプトを再実行させる
      const wrap = window.parent.document.querySelector('.st-key-col_left');
      if (!wrap) return;
      function bottom(tries) {{
        let el = null;  // overflowY: auto/scroll の要素だけが対象（visibleな文章要素を誤って拾わない）
        for (const c of [wrap, ...wrap.querySelectorAll('div')]) {{
          const o = window.parent.getComputedStyle(c).overflowY;
          if ((o === 'auto' || o === 'scroll') && c.scrollHeight > c.clientHeight + 4) {{ el = c; break; }}
        }}
        if (el) el.scrollTop = el.scrollHeight;
        if (tries > 0) setTimeout(() => bottom(tries - 1), 250);  // 画像等の遅延レイアウトに追従
      }}
      bottom(4);
    }})();
    </script>""", height=0)


def _marks_of(name: str) -> list:
    """ファイル名キーで印を保持（並び替え・再アップロードでも消えない）"""
    return st.session_state.setdefault("marks_by_name", {}).setdefault(name, [])


# ---- 印つけツールバー（形・色・↩︎戻る を1本に統合。クリック選択）----
_CELL = 44   # セル1辺
_GAP = 8     # セル間隔
_SEP = 24    # グループ間の空き
_BG = "#262730"  # ダークテーマの背景色に合わせる
TOOL_LIST = ["丸", "矢印"]
_TB_ITEMS = ([("tool", t) for t in TOOL_LIST] + [None]
             + [("color", c) for c in PALETTE] + [None]
             + [("undo", None)])


_PAGE_BG = "#0E1117"  # アプリ全体の背景色（グループ間はこの色＝別の箱に見せる）


def _undo_font(size: int = 32):
    """undo記号（↩）を持つフォント。無ければ None（手描きの左矢印にフォールバック）"""
    for p in ["/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
              "/System/Library/Fonts/Apple Symbols.ttf"]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return None


def _toolbar_layout():
    """ツールバーの各セルの (x0, x1, (kind, value))・グループ範囲・全体幅を返す"""
    cells, groups, x = [], [], 0
    gstart = None
    for it in _TB_ITEMS:
        if it is None:
            if gstart is not None:
                groups.append((gstart, x - _GAP))
                gstart = None
            x += _SEP
            continue
        if gstart is None:
            gstart = x
        cells.append((x, x + _CELL, it))
        x += _CELL + _GAP
    if gstart is not None:
        groups.append((gstart, x - _GAP))
    return cells, groups, x - _GAP


def _toolbar_img(sel_tool: str, sel_color: str, undo_enabled: bool) -> Image.Image:
    """［丸｜矢印］［色×5］［↶戻す］の3つの箱に分かれたツールバー画像"""
    cells, groups, width = _toolbar_layout()
    img = Image.new("RGB", (width, _CELL), _PAGE_BG)
    d = ImageDraw.Draw(img)
    for gx0, gx1 in groups:  # グループごとに背景の箱（間はページ色＝別カテゴリに見える）
        d.rounded_rectangle([gx0, 0, gx1 - 1, _CELL - 1], radius=8, fill=_BG)
    for x0, _x1, (kind, val) in cells:
        cx, cy = x0 + _CELL // 2, _CELL // 2
        if kind == "tool":
            if val == "丸":
                d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], outline="white", width=4)
            else:  # 矢印（左下→右上・先端が右上）
                d.line([cx - 12, cy + 12, cx + 12, cy - 12], fill="white", width=4)
                d.line([cx + 12, cy - 12, cx + 1, cy - 12], fill="white", width=4)
                d.line([cx + 12, cy - 12, cx + 12, cy - 1], fill="white", width=4)
            if val == sel_tool:
                d.rounded_rectangle([x0, 0, x0 + _CELL - 1, _CELL - 1], radius=8,
                                    outline="white", width=3)
        elif kind == "color":
            d.rectangle([x0 + 6, 6, x0 + _CELL - 7, _CELL - 7], fill=PALETTE[val])
            if val == sel_color:
                d.rounded_rectangle([x0, 0, x0 + _CELL - 1, _CELL - 1], radius=8,
                                    outline="white", width=3)
        else:  # undo（↩。印が無いときはグレー＝無効）
            col = "white" if undo_enabled else "#555555"
            uf = _undo_font(34)
            if uf is not None:  # フォントの ↩ 記号をそのまま描く（正しい形が出る）
                bbox = d.textbbox((0, 0), "↩", font=uf)
                d.text((cx - (bbox[0] + bbox[2]) / 2, cy - (bbox[1] + bbox[3]) / 2),
                       "↩", fill=col, font=uf)
            else:  # フォールバック：シンプルな左向き矢印
                d.line([cx + 11, cy, cx - 9, cy], fill=col, width=4)
                d.line([cx - 9, cy, cx - 1, cy - 8], fill=col, width=4)
                d.line([cx - 9, cy, cx - 1, cy + 8], fill=col, width=4)
    return img


def _toolbar_hit(x: int):
    """クリックx座標 → (kind, value) or None（グループ間の空きは無反応）"""
    cells, _groups, _w = _toolbar_layout()
    for x0, x1, it in cells:
        if x0 <= x <= x1:
            return it
    return None


def _collect_images(imgs) -> list:
    """②③に渡す画像データを組み立てる。
    - bytes/pil：表示解像度（AI入力・プレビュー用）
    - full_bytes：**元解像度**に印を描いたJPEG（Notion保存用＝解像度を落とさない）
    - raw_bytes：アップロードされた**生ファイルそのまま**（Drive保管用＝マークなし・無加工）
    """
    data = []
    for i, f in enumerate(imgs or []):
        base = Image.open(f).convert("RGB")
        disp = _fit(base)
        marks = _marks_of(f.name)
        marked_disp = draw_user_marks(disp, marks) if marks else disp
        scale = base.width / disp.width
        marked_full = draw_user_marks(base, marks, scale=scale) if marks else base
        bio = io.BytesIO()
        marked_disp.save(bio, format="PNG")
        biof = io.BytesIO()
        marked_full.save(biof, format="JPEG", quality=92)
        data.append({
            "n": i + 1, "filename": f.name, "bytes": bio.getvalue(), "mime": "image/png",
            "full_bytes": biof.getvalue(), "full_mime": "image/jpeg",
            "raw_bytes": f.getvalue(), "raw_mime": getattr(f, "type", None) or "image/jpeg",
            "marks": [{**m, "label": chr(64 + j)} for j, m in enumerate(marks, 1)],
            "pil": marked_disp,
        })
    return data


def _caption_text(fmt: str, n: int, desc: str, filename: str) -> str:
    """キャプション書式の適用。descが空（音声で言及なし）なら 画像N（ファイル名）だけ"""
    if not (desc or "").strip():
        return f"画像{n}（{filename}）"
    try:
        return fmt.format(n=n, desc=desc, filename=filename)
    except Exception:
        return f"画像{n}：{desc}（{filename}）"


def _prompt_diff_md(old: str, new: str) -> str:
    """プロンプト変更案の行単位差分（🔴削除・🟢追加）をmarkdownで返す"""
    o, n = old.split("\n"), new.split("\n")

    def disp(line):  # 行頭の "- " はリスト化を避けて表示用に置換
        return line.replace("- ", "– ", 1) if line.lstrip().startswith("- ") else line

    sm = difflib.SequenceMatcher(None, o, n)
    lines = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            lines += [disp(l) for l in n[j1:j2]]
        else:
            if op in ("replace", "delete"):
                lines += [f":red[~~{disp(l)}~~]" for l in o[i1:i2] if l.strip()]
            if op in ("replace", "insert"):
                lines += [f":green-background[{disp(l)}]" for l in n[j1:j2] if l.strip()]
    return "  \n".join(lines)


def _run_pipeline(imgs, tmpl, work_date, p: dict):
    """①〜④を実行して session_state に結果を入れ、runs/ に実験ログを保存。
    p: {"sources": [(bytes,mime)]|None, "extra_text": str, "extra_audio": (bytes,mime)|None,
        "from_reformat": bool}
    """
    usage.reset()  # このAI実行のトークン集計を開始（各AIが usage.record する）
    # 追加指示（テキスト＋音声）
    extra = (p.get("extra_text") or "").strip()
    if p.get("extra_audio"):
        with st.spinner("指示の文字起こし中…"):
            spoken = transcribe(*p["extra_audio"])
        extra = (extra + "\n" + spoken).strip()

    # ① 文字起こし（新しい音声がある場合のみ）
    if p.get("sources"):
        texts = []
        with st.spinner(f"① 文字起こし中…（音声{len(p['sources'])}件）"):
            for ab, mime in p["sources"]:
                texts.append(transcribe(ab, mime))
        st.session_state.transcript = "\n\n".join(t.strip() for t in texts if t.strip())
    transcript = st.session_state.transcript
    ref = st.session_state.get("ref_text", "") or ""  # 参考情報（URL等・ソースの一部）

    images = _collect_images(imgs)

    # ② 整形 or 修正（指示ありの修正＝指示以外変えない revise）
    prev_out = st.session_state.get("out")
    if p.get("from_reformat") and extra and prev_out is not None:
        stage = "revise"
        with st.spinner("✏️ 指示の箇所だけ修正中…（他は変えない）"):
            out = revise_structured(transcript, prev_out, extra)
    else:
        stage = "compose"
        with st.spinner("② 記録を整形中…（画像も読み取り）"):
            out = compose_record(transcript, images, tmpl, work_date=str(work_date),
                                 extra_instruction=extra, ref_text=ref)

    # ③ 検証（作業日・追加指示・参考情報もソースとして渡す）
    with st.spinner("③ 事実を検証中…"):
        vr = verify_record(transcript, render_structured(out), images,
                           work_date=str(work_date), extra_instruction=extra, ref_text=ref)

    fixed = 0
    for _ in range(2):  # ④ 事実の改変は自動修復（最大2周）
        facts = [i for i in vr.issues if i.type == "事実の改変"]
        if not facts:
            break
        with st.spinner(f"④ 事実の改変 {len(facts)}件を自動修正中…"):
            out = refine_structured(transcript, out, facts)
            vr = verify_record(transcript, render_structured(out), images,
                               work_date=str(work_date), extra_instruction=extra, ref_text=ref)
        fixed += len(facts)

    # トークン消費・推定コストの集計（この記録作成で走った全AI呼び出しの合計）
    usage_summary = usage.summary()
    st.session_state.usage = usage_summary
    st.session_state.usage_cum = usage.add(st.session_state.get("usage_cum"), usage_summary)

    # 実験ログ（プロンプト調整の記録。プロンプト・入力・出力・検証を1ファイルに）
    st.session_state.runlog_path = save_run({
        "stage": stage,
        "templates": tmpl,
        "extra_instruction": extra,
        "ref_text": ref,
        "work_date": str(work_date),
        "transcript": transcript,
        "images": [{"n": im["n"], "filename": im["filename"], "marks": im["marks"]}
                   for im in images],
        "output": out.model_dump(),
        "verify": vr.model_dump(),
        "auto_fixed": fixed,
        "usage": usage_summary,
    })

    # 修正なら直前の記録を保持（プレビューで差分ハイライトに使う）。新規録音なら差分なし
    st.session_state.prev_out = prev_out if p.get("from_reformat") else None
    st.session_state.out = out
    st.session_state.vr = vr
    st.session_state.images = images
    st.session_state.auto_fixed = fixed
    st.session_state.saved_url = None
    st.session_state.edit_mode = False
    st.session_state.done_msg = ("✏️ 部分修正を完了しました" if stage == "revise"
                                 else "✅ 記録作成を完了しました")


st.set_page_config(page_title="しゃべれぽAI", page_icon="🎙️", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown("""
<style>
.block-container {padding-top: 3rem; padding-bottom: 0.5rem;}
div[data-testid="stExpander"] summary p {font-weight: 600;}
/* 2列（左＝インプット・右＝AI出力）の高さを画面に合わせ、ページ全体のスクロールを不要にする */
.st-key-col_left, .st-key-col_right {
    height: calc(100vh - 170px) !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown("### しゃべれぽAI　"
            "<span style='font-size:0.85rem;color:#888;font-weight:400;'>"
            "実験・調査などの活動を、音声と画像からNotionに記録化するAIエージェント</span>",
            unsafe_allow_html=True)

# ---- 画面切替はサイドバー（タブの縦幅を節約）----
with st.sidebar:
    page = st.radio("画面", ["📝 記録作成", "⚙️ プロンプト設定"], label_visibility="collapsed")

# プロンプト設定はセッションに保持（画面を切り替えても編集が消えない）
if "tmpl_store" not in st.session_state:
    st.session_state.tmpl_store = load_prompts()
st.session_state.setdefault("tmpl_undo", {})

# ---- 実行状態 ----
busy = st.session_state.get("pending") is not None          # AI処理の実行予約中（次の描画で実行）
done = st.session_state.get("out") is not None              # 記録作成済み
locked = busy or (done and not st.session_state.get("edit_mode"))  # 入力ロック（グレーアウト）

# 部分修正の完了後は指示テキストをクリア（反映済み。ウィジェット生成前にここで消す）
if st.session_state.pop("clear_reformat", False):
    st.session_state.pop("extra_instruction", None)

# ---- プロンプト設定ページ ----
if page == "⚙️ プロンプト設定":
    if st.session_state.pop("just_saved_prompts", False):
        st.success("保存しました（次回以降もこの設定が使われます）")
    st.caption("ここでの変更は、次の「記録を作成する」「記録の一部を修正する」から反映されます。"
               "効果は、記録画面で「記録の一部を修正する」を指示なしで実行すると差分（🟢🔴）で確認できます。"
               "実行のたびに、使用したプロンプトが runs/ に記録されます。")
    ts = st.session_state.tmpl_store
    undo = st.session_state.tmpl_undo
    _saved_now = load_prompts()
    if any(ts[k] != _saved_now.get(k) for k in DEFAULT_TEMPLATES):
        st.markdown(":orange[**● 未保存の変更があります**]（保存しない場合、アプリ再起動で消えます）")

    # ============ 編集できるプロンプト（AI修正の対象もここ） ============
    with st.container(border=True):
        st.markdown("### ✏️ 編集できるプロンプト")
        st.caption("この枠の中の項目が調整対象です。下の「AIに修正を頼む」も、この項目だけを変更します"
                   "（変更できない固定ルールはページ下部で見られます）")

        # ── AIに修正を頼む（適用し、保存するまで何も変わらない）──
        with st.container(border=True):
            st.markdown("#### 🤖 AIに修正を頼む")
            st.caption("直したいことを伝えると、この枠内の項目への変更案を作ります")
            pe_text = st.text_area("修正したいこと（例：結果には必ず数値を入れる／考察は3項目以内にする）",
                                   key="pe_intent", disabled=busy)
            pe_audio = st.audio_input("🎙️ 音声で伝える（任意）", key="pe_audio", disabled=busy)
            if st.button("変更案を作成", disabled=busy):
                intent = (pe_text or "").strip()
                if pe_audio is not None:
                    with st.spinner("音声を文字起こし中…"):
                        spoken = transcribe(pe_audio.getvalue(),
                                            getattr(pe_audio, "type", None) or "audio/wav")
                    intent = (intent + "\n" + spoken).strip()
                if not intent:
                    st.warning("修正したいことを入力してください")
                else:
                    with st.spinner("変更案を作成中…"):
                        st.session_state.prompt_edits = propose_prompt_edits(
                            {k: ts[k] for k in DEFAULT_TEMPLATES}, intent,
                            FIXED_DISPLAY, TEMPLATE_LABELS)
                    if not st.session_state.prompt_edits:
                        st.info("変更が必要な項目はありませんでした")

        _edits = st.session_state.get("prompt_edits") or []
        if _edits:
            st.markdown(f"##### 変更案（{len(_edits)}件）— 差分（🔴削除・🟢追加）を確認して適用してください")
            ba, bb, _sp = st.columns([1, 1, 3])
            if ba.button("✅ すべて適用", disabled=busy):
                for e in _edits:
                    undo[e.item] = ts[e.item]
                    ts[e.item] = e.new_text
                st.session_state.prompt_edits = []
                st.rerun()
            if bb.button("🗑 すべて破棄"):
                st.session_state.prompt_edits = []
                st.rerun()
            for i, e in enumerate(_edits):
                with st.container(border=True):
                    st.markdown(f"**{TEMPLATE_LABELS.get(e.item, e.item)}** — {e.reason}")
                    st.markdown(_prompt_diff_md(ts[e.item], e.new_text))
                    pa, pb, _s2 = st.columns([1, 1, 3])
                    if pa.button("適用", key=f"pe_ap{i}", disabled=busy):
                        undo[e.item] = ts[e.item]
                        ts[e.item] = e.new_text
                        st.session_state.prompt_edits = [x for x in _edits if x is not e]
                        st.rerun()
                    if pb.button("破棄", key=f"pe_dis{i}"):
                        st.session_state.prompt_edits = [x for x in _edits if x is not e]
                        st.rerun()

        st.markdown("---")

        # ── 項目ごとの編集（変更済みバッジ・デフォルトに戻す・直前に戻す）──
        def _tmpl_item(key: str, height: int = None):
            changed = ts[key] != DEFAULT_TEMPLATES[key]
            label = TEMPLATE_LABELS[key] + ("　🟠 変更済み" if changed else "")
            if key == "caption":
                ts[key] = st.text_input(label, ts[key], help=TEMPLATE_HELP[key], disabled=busy)
            else:
                ts[key] = st.text_area(label, ts[key], height=height,
                                       help=TEMPLATE_HELP[key], disabled=busy)
            rc1, rc2, _rs = st.columns([1.3, 1.3, 3])
            if changed and rc1.button("デフォルトに戻す", key=f"rst_{key}", disabled=busy):
                undo[key] = ts[key]
                ts[key] = DEFAULT_TEMPLATES[key]
                st.rerun()
            if key in undo and rc2.button("↩ 直前に戻す", key=f"und_{key}", disabled=busy):
                ts[key] = undo.pop(key)
                st.rerun()

        c1, c2 = st.columns(2)
        with c1:
            _tmpl_item("details", 400)
            _tmpl_item("style", 120)
        with c2:
            _tmpl_item("summary", 150)
            _tmpl_item("title", 90)
            _tmpl_item("properties", 90)
            _tmpl_item("caption")

        if sum(len(ts[k]) for k in DEFAULT_TEMPLATES) > 4000:
            st.caption("⚠️ 指示が長くなっています。長すぎる指示は効きが悪くなることがあります")

        # ── 保存（キャプション書式の検証つき）──
        if st.button("💾 この設定を保存", type="primary", disabled=busy):
            unknown = [m for m in re.findall(r"\{([^{}]*)\}", ts["caption"])
                       if m not in ("n", "desc", "filename")]
            if unknown:
                st.error(f"キャプション書式に使えない変数があります: {unknown}"
                         "（使えるのは {{n}} {{desc}} {{filename}}）".replace("{{", "{").replace("}}", "}"))
            else:
                if not ts["details"].strip() or not ts["summary"].strip():
                    st.warning("空欄の項目があります（実行時はデフォルトが使われます）")
                save_prompts(ts)
                st.session_state.just_saved_prompts = True
                st.rerun()

        with st.expander("⚠️ すべてデフォルトに戻す"):
            sure = st.checkbox("すべての項目を出荷時のデフォルトに戻します。よろしいですか？")
            if st.button("すべて戻す", disabled=(not sure) or busy):
                st.session_state.tmpl_undo = {k: ts[k] for k in DEFAULT_TEMPLATES}
                st.session_state.tmpl_store = dict(DEFAULT_TEMPLATES)
                st.rerun()

    # ============ 固定ルール（参照用・最下部） ============
    with st.expander("🔒 固定ルール（変更不可・参照用）"):
        st.caption("記録の信頼性（事実を変えない）とアプリの動作（出力構造・画像配置）を支えるため、"
                   "UIからは変更できません。上の編集項目と組み合わせてAIに渡されます")
        st.text(FIXED_DISPLAY)
    st.stop()

tmpl = st.session_state.tmpl_store


def _step_head(text: str):
    """ステップ見出し（ロック中はグレー表示）"""
    st.markdown(f"#### :gray[{text}]" if locked else f"#### {text}")


def _reformat_ui(disabled: bool):
    """記録の一部を修正するUI（テキスト or 音声で指示。文字起こしは再利用＝音声の再処理なし）"""
    with st.container(border=True):
        st.markdown("#### 🔁 記録の一部を修正する")
        st.caption("指示（テキスト or 音声）で、記録の**指示箇所だけ**を修正します（他は変えません）。"
                   "指示を空にして実行すると、プロンプト設定の変更を反映して全体を作り直します。")
        extra_text = st.text_area("修正指示（テキスト・任意）例：結果はもっと簡潔に／考察を1つに絞る",
                                  key="extra_instruction", disabled=disabled)
        extra_audio = st.audio_input("🎙️ 修正指示（音声・任意）", key="extra_audio",
                                     disabled=disabled)
        if st.button("✍️ 修正する", disabled=disabled, use_container_width=True):
            st.session_state.pending = {
                "sources": None,
                "extra_text": extra_text or "",
                "extra_audio": (extra_audio.getvalue(),
                                getattr(extra_audio, "type", None) or "audio/wav")
                               if extra_audio is not None else None,
                "from_reformat": True,
            }
            st.rerun()


# ---- 記録作成ページ：左＝インプット／右＝AI出力（独立スクロール）----
col_work, col_prev = st.columns(2, gap="medium")

# ============ 左列：ユーザーによるインプット ============
with col_work:
    st.markdown("##### ユーザーによるインプット")
    with st.container(height=760, key="col_left"):

        # ── ロック中の案内（理由＋解除手段を一番上に）──
        if done and not st.session_state.get("edit_mode"):
            li, lb = st.columns([7, 3])
            with li:
                st.info("🔒 作成済みの記録と食い違わないよう、入力欄（作業日・画像・音声・マーク）を変更不可にしています")
            with lb:
                # on_click（コールバックは再実行の前に走る）を使う。ボタン直後の st.rerun() は
                # 画像アップローダの描画前に実行を打ち切り、「描画されなかったウィジェット」として
                # アップロード済み画像が破棄されるバグがあった
                st.button("✏️ 編集を再開する", disabled=busy, use_container_width=True,
                          on_click=lambda: st.session_state.update(edit_mode=True))

        # ── STEP 1 ──
        with st.container(border=True):
            _step_head("1️⃣ 作業日を入力する")
            work_date = st.date_input("作業日", key="work_date_in",
                                      disabled=locked, label_visibility="collapsed")

        # ── STEP 2 ──
        with st.container(border=True):
            _step_head("2️⃣ 画像をアップロードする（スキップ可）")
            imgs = st.file_uploader(
                "現場・実験の写真（複数可）", accept_multiple_files=True,
                type=["png", "jpg", "jpeg", "webp"], key="imgs_up",
                disabled=locked, label_visibility="collapsed",
            )

        # ── STEP 3 ──
        with st.container(border=True):
            _step_head("3️⃣ AIに音声で説明する")
            st.caption("""録音開始ボタンを押して、やったことや結果などについて話してください（録音済みの音声ファイルも使用可能です）。
- 手順2でアップロードした画像は、下の「画像にマーク」に表示されます。「1枚目は〜」「3枚目のAは〜」のように、画像の枚数やマークを含めて説明してください。
- URLなどのテキスト情報は、下の「テキスト情報」に貼り付け、その概要を説明してください。""")
            with st.expander("💡 話す時のコツ", expanded=False):
                st.caption("""- 以下の内容を含めると、活用しやすい記録になります。台本としてご利用ください
  1. なぜやったか、何をやりたいか（背景・目的）
  2. 何をしたか（概要、日時・場所・メンバー・方法・手順・ワーク・使用機器など）
  3. 何が分かったか、何を考えたか（結果・考察）
  4. 何をどう判断したか・なぜか（結論・判断）
  5. 次に何をするか（ネクストアクション）
- 事実と推測・解釈を区別して話すと、記録の精度が上がります
  - 事実：〜であった、〜を確認した
  - 推測・解釈：〜と思われた、〜と考えられた、〜の可能性が高い""")
            with st.expander("🎙 マイクチェック（試し録音・任意）", expanded=False):
                st.caption("一言（5秒ほど）話して録音を止めると、聞き取れた内容を表示します。"
                           "マイクや話し方の問題を、本番の録音前に確認できます")
                chk = st.audio_input("マイクチェック", key="mic_check",
                                     disabled=locked, label_visibility="collapsed")
                if chk is not None:
                    sig = hash(chk.getvalue())
                    if st.session_state.get("mic_check_sig") != sig:  # 新しい録音のときだけ実行
                        with st.spinner("文字起こし中…"):
                            st.session_state.mic_check_text = transcribe(
                                chk.getvalue(), getattr(chk, "type", None) or "audio/wav")
                        st.session_state.mic_check_sig = sig
                    _t = (st.session_state.get("mic_check_text") or "").strip()
                    if _t:
                        st.success(f"聞き取れた内容：{_t}")
                    else:
                        st.warning("何も聞き取れませんでした。マイクの選択・音量を確認してください")
            ac1, ac2 = st.columns(2)
            with ac1:
                audio = st.audio_input("その場で録音", key="audio_rec", disabled=locked)
            with ac2:
                audio_files = st.file_uploader(
                    "音声ファイル（複数可）",
                    type=["m4a", "mp3", "wav", "aac", "ogg", "flac"],
                    accept_multiple_files=True, key="audio_files_up", disabled=locked,
                )
            if audio is not None:
                st.download_button(
                    "⬇️ 録音した音声を保存（取り直し保険）",
                    data=audio.getvalue(),
                    file_name=f"fieldnote_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav",
                    mime=getattr(audio, "type", None) or "audio/wav",
                )

            st.markdown("##### 🖍 画像にマーク")
            if not imgs:
                st.caption("STEP2で画像をアップロードすると、ここでマークをつけられます")
            else:
                st.caption("画像をクリックすると、マークとA, B, C…の記号がつきます")
                names = [f.name for f in imgs]
                if st.session_state.get("img_names") != names:
                    st.session_state.img_names = names
                    st.session_state.sel = 0
                    # 印はファイル名キーで保持しているためリセットしない（消失バグ対策）
                    for k in [key for key in list(st.session_state)
                              if str(key).startswith(("thp", "clkp"))]:
                        del st.session_state[k]

                sel = min(st.session_state.get("sel", 0), len(imgs) - 1)
                st.session_state.setdefault("mark_tool", "丸")
                st.session_state.setdefault("mark_cname", "赤")
                tool = st.session_state.mark_tool
                cname = st.session_state.mark_cname

                left, right = st.columns([1, 4])

                # 左：画像一覧（縦長）
                with left:
                    with st.container(height=560):
                        for i, f in enumerate(imgs):
                            if locked or not HAS_COORDS:
                                st.image(_thumb_sel(f, i == sel))
                                continue
                            # image-coordinatesは座標を保持し続けるので
                            # 「前回と座標が変わったサムネ＝今クリック」だけ反応させる
                            cc = streamlit_image_coordinates(_thumb_sel(f, i == sel), key=f"th{i}")
                            if cc is not None and cc != st.session_state.get(f"thp{i}"):
                                st.session_state[f"thp{i}"] = cc
                                st.session_state.sel = i
                                st.rerun()

                # 右：ツールバー（形・色・↩︎戻る）→ 画像詳細
                with right:
                    cur = imgs[sel]
                    marks = _marks_of(cur.name)
                    tb = _toolbar_img(tool, cname, undo_enabled=bool(marks))
                    if locked or not HAS_COORDS:
                        st.image(tb)
                    else:
                        tc = streamlit_image_coordinates(tb, key="toolbar")
                        if tc is not None and tc != st.session_state.get("toolbarp"):
                            st.session_state["toolbarp"] = tc
                            hit = _toolbar_hit(tc["x"])
                            if hit:
                                kind, val = hit
                                if kind == "tool":
                                    st.session_state.mark_tool = val
                                elif kind == "color":
                                    st.session_state.mark_cname = val
                                elif kind == "undo" and marks:
                                    marks.pop()
                                st.rerun()

                    st.markdown(f"**画像{sel + 1} / {len(imgs)}** — {cur.name}")
                    disp = _fit(Image.open(cur).convert("RGB"))
                    marked = draw_user_marks(disp, marks) if marks else disp
                    if locked or not HAS_COORDS:
                        st.image(marked)
                    else:
                        coords = streamlit_image_coordinates(marked, key=f"clk{sel}")
                        # 「前回と座標が変わったクリック」だけ反応（削除後の復活防止）
                        if coords and coords != st.session_state.get(f"clkp{sel}"):
                            st.session_state[f"clkp{sel}"] = coords
                            x, y = int(coords["x"]), int(coords["y"])
                            if not any(m["x"] == x and m["y"] == y for m in marks):
                                marks.append({"x": x, "y": y, "tool": tool,
                                              "color": PALETTE[cname], "cname": cname})
                                st.rerun()
            if imgs and not HAS_COORDS:
                st.warning("クリック注釈には streamlit-image-coordinates が必要です（pip install）")

            st.markdown("##### 📎 テキスト情報")
            st.caption("URL・メモなど。音声で「このURLは〜」と説明すると適切な場所に配置されます")
            st.text_area("テキスト情報", key="ref_text", height=68,
                         disabled=locked, label_visibility="collapsed")

        # ── STEP 4 ──
        with st.container(border=True):
            _step_head("4️⃣ 記録を作成する")
            if st.button("🚀 記録を作成する", type="primary",
                         use_container_width=True, disabled=locked):
                sources = []
                if audio is not None:
                    sources.append((audio.getvalue(),
                                    getattr(audio, "type", None) or "audio/wav"))
                for f in audio_files or []:
                    sources.append((f.getvalue(),
                                    getattr(f, "type", None) or "audio/mpeg"))
                if not sources:
                    st.warning("録音するか、音声ファイルをアップロードしてください")
                else:
                    st.session_state.pending = {"sources": sources, "extra_text": "",
                                                "extra_audio": None, "from_reformat": False}
                    st.rerun()
            if not locked and st.session_state.tmpl_store != load_prompts():
                st.caption("ℹ️ 保存されていないプロンプト変更があります（この作成に使用されます）")
            if busy:
                st.info("🤖 AI処理中…（1〜2分）**進捗は右列の上部に表示されます**")
                st.caption("⏳ 作成中はページを操作しないでください（処理が中断されます）。"
                           "中断されても、文字起こし済みなら「記録の一部を修正する」から再実行できます。")
            elif done and not st.session_state.get("saved_url"):
                st.success("✅ 記録を作成しました → **右列で検証結果とプレビューを確認**してください。"
                           "直したい点は下の「記録の一部を修正する」、問題なければ右の「**承認してNotionに保存**」")

        # 中断リカバリ：文字起こしは済んでいるが記録が無い場合
        if st.session_state.get("transcript") and not done and not busy:
            st.info("文字起こしは完了しています。中断された場合は下の「記録の一部を修正する」から再実行できます（音声の再処理なし）")
            _reformat_ui(disabled=busy)

        # ── 修正（記録作成後に出現。ロック解除は列上部の「編集を再開する」）──
        if done:
            _reformat_ui(disabled=busy)

        # 作成開始・完了の直後は左列を最下部へ（STEP4のメッセージが画面外だと気づけない）
        if busy or st.session_state.pop("scroll_left", False):
            _scroll_left_to_bottom()

# ============ 右列：AIによる出力 ============
with col_prev:
    st.markdown("##### AIによる出力")
    with st.container(height=760, key="col_right"):

        # ── AI処理の進捗／完了メッセージ（囲み・見出しなしの1行）──
        # ※Streamlitは要素を位置で照合するため、このスロットは状態によらず常設にする
        #   （処理中だけ要素を増やすと、前回描画の下の枠の中身がここに混ざって見える）
        status_slot = st.container()
        ai_status = None
        if busy:
            ai_status = status_slot  # 進捗（現在のステップ）は末尾の実行ブロックがここに書く
        elif st.session_state.get("done_msg"):
            with status_slot:
                st.markdown(st.session_state.done_msg)

        # ── 検証AIによる検証結果（常設）──
        with st.container(border=True):
            st.markdown("#### 🛡 検証AIによる検証結果")
            if not done:  # 処理中も説明を表示（内容は一般的な説明なので矛盾しない）
                st.caption(
                    "検証AIは、作成された記録をソース（文字起こし・画像など）と突き合わせて、"
                    "**事実が保たれているか**をチェックします。記録を作成すると結果がここに表示されます。"
                )
                st.caption("""**チェックの観点**
- 🚨 **事実の改変**：数値・結果・状態がソースと変わっていないか → **自動で修正**
- ℹ️ **推測の追加**：話していない情報が足されていないか
- ℹ️ **欠落**：重要な事実が抜けていないか""")
            if done:
                vr = st.session_state.vr
                if st.session_state.get("auto_fixed"):
                    st.info(f"🔧 事実の改変 {st.session_state.auto_fixed}件を検出し、自動修正しました（再検証済み）")
                facts = [i for i in vr.issues if i.type == "事実の改変"]
                others = [i for i in vr.issues if i.type != "事実の改変"]
                if not vr.issues and not st.session_state.get("auto_fixed"):
                    st.success("✅ 問題なし — そのまま承認できます")
                if facts:
                    st.error(f"🚨 未解消の事実の改変 {len(facts)}件（自動修正で直りきらず）")
                    for x in facts:
                        sec = f"[{x.section}] " if getattr(x, "section", "") else ""
                        st.write(f"- {sec}「{x.draft_says}」← 元「{x.source_says}」（{x.note}）")
                if others:
                    st.info(f"ℹ️ 参考 {len(others)}件（推測の追加・欠落／修正は任意）")
                    for x in others:
                        sec = f"[{x.section}] " if getattr(x, "section", "") else ""
                        st.write(f"- [{x.type}] {sec}「{x.draft_says}」（{x.note}）")

        # ── AIコスト（トークン消費・推定金額）──
        if done and st.session_state.get("usage"):
            u = st.session_state.usage
            with st.expander(f"🧮 AIコスト（このAI実行 {u['calls']}回・推定 約¥{u['jpy']:.1f}）",
                             expanded=False):
                st.caption(f"このAI実行の合計トークン **{u['total']:,}**"
                           f"（入力 {u['in']:,} / 出力 {u['out']:,}）・推定 **約¥{u['jpy']:.1f}**")
                cum = st.session_state.get("usage_cum")
                if cum and cum["calls"] > u["calls"]:
                    st.caption(f"この画面を開いてからの累計 {cum['total']:,} トークン・"
                               f"推定 約¥{cum['jpy']:.1f}")
                for r in u.get("breakdown", []):
                    st.caption(f"　• {r['label']}：{r['total']:,} tok"
                               f"（入 {r['in']:,} / 出 {r['out']:,}）")
                st.caption("※金額は概算（単価は変動）。正確な実費は GCP 請求で確認してください。"
                           "音声入力は単価が高めのため、実費はやや高くなる場合があります。")

        # ── 保存（検証結果の下）──
        if done:
            out = st.session_state.out
            images = st.session_state.get("images") or []
            by_n = {im["n"]: im for im in images}
            cap_by_n = {c.n: c.desc for c in out.captions}

            if st.button("✅ 承認してNotionに保存", type="primary",
                         use_container_width=True, disabled=busy):
                with st.spinner("保存中…（Notionに画像も直接アップロード）"):
                    image_blobs = [
                        (im["filename"], im["full_bytes"],
                         _caption_text(tmpl["caption"], im["n"],
                                       cap_by_n.get(im["n"], ""), im["filename"]),
                         im["full_mime"])
                        for im in images
                    ]
                    # Driveはバックアップ保管（記録フォルダ内の「画像」フォルダへ）。
                    # ※あくまで副次的な保管。ここが失敗しても主機能（Notion保存）は必ず通す。
                    drive_url, drive_links = None, None
                    drive_warn = None
                    drive_ok = (os.environ.get("DRIVE_OAUTH_CLIENT")
                                or os.environ.get("DRIVE_OAUTH_TOKEN_JSON"))
                    if image_blobs and drive_ok:
                        try:
                            from tools.drive_tools import (create_record_folder,
                                                           create_subfolder, upload_image)
                            wd = str(work_date)
                            yymmdd = wd[2:].replace("-", "") if wd else "nodate"
                            folder_id, drive_url = create_record_folder(f"{yymmdd}_{out.title}")
                            img_fid, img_folder_url = create_subfolder(folder_id, "画像")
                            drive_links = [("画像フォルダ", img_folder_url)]  # ソースにはフォルダURLだけ載せる
                            for im in images:  # Driveは生画像（マークなし・無加工）を保管
                                upload_image(img_fid, im["filename"],
                                             im.get("raw_bytes") or im["full_bytes"],
                                             im.get("raw_mime") or im["full_mime"])
                        except Exception as e:  # 認証切れ等。Driveだけ諦めてNotionは続行
                            drive_url, drive_links = None, None  # 途中失敗ならフォルダ参照も載せない
                            drive_warn = str(e)
                    url = save_structured(out, st.session_state.transcript,
                                          work_date=str(work_date),
                                          image_blobs=image_blobs,
                                          drive_folder_url=drive_url,
                                          drive_image_links=drive_links)
                st.session_state.saved_url = url
                st.session_state.drive_warn = drive_warn  # Drive失敗時のみ後で表示
            if st.session_state.get("saved_url"):
                st.success(f"保存しました 👉 {st.session_state.saved_url}")
                if st.session_state.get("drive_warn"):
                    st.warning("⚠️ Notionへの保存は完了しましたが、Google Driveへの画像バックアップは"
                               "スキップされました（Drive認証エラー）。記録本体はNotionに保存済みです。")

        # ── 記録プレビュー（枠付き・常設）──
        with st.container(border=True):
            st.markdown("#### 📄 記録プレビュー")
            if not done:
                st.caption("記録を作成すると、ここにNotion保存イメージが表示されます")
            else:
                # 修正後は、記録そのものに変更箇所をハイライトできる
                prev = st.session_state.get("prev_out")
                show_diff = False
                if prev is not None:
                    show_diff = st.checkbox(
                        "🔍 前回からの変更をハイライト（🟢追加・🔴削除）", value=True)

                def _dv(new: str, old) -> str:
                    """単一テキストのdiff表示（変更時のみ 旧=赤取り消し＋新=緑背景）"""
                    new = (new or "").strip()
                    old = (old or "").strip() if old is not None else None
                    if not show_diff or old is None or old == new:
                        return new
                    head = f":red[~~{old}~~] " if old else ""
                    return f"{head}:green-background[{new}]"

                _p = prev  # None なら diff なし（_dv内で素通し）
                st.markdown(f"### {str(work_date).replace('-', '/')}_"
                            f"{_dv(out.title, _p.title if _p else None)}")
                st.markdown("##### プロパティ")
                st.markdown(f"やったこと：{_dv(out.did, _p.did if _p else None)}\n\n"
                            f"結果：{_dv(out.result, _p.result if _p else None)}")
                st.divider()
                if (out.one_liner or "").strip():
                    st.markdown("### これなに？")
                    st.markdown(_dv(out.one_liner, _p.one_liner if _p else None))

                def _show_sections(sections, with_images=False, prev_sections=None):
                    placed = set()
                    diff_lines, deleted_blocks = (None, [])
                    if show_diff and prev_sections is not None:
                        diff_lines, deleted_blocks = diff_section_lines(prev_sections, sections)
                    for idx, sec in enumerate(sections):
                        if (sec.heading or "").strip():
                            st.markdown(f"##### {sec.heading}")
                        sec_imgs = []
                        if with_images:
                            for b in sec.bullets:
                                sec_imgs += [n for n in b.images if n in by_n and n not in placed]
                                placed.update(b.images)
                        if diff_lines is not None:
                            md = "\n".join(diff_lines[idx])
                        else:
                            md = ""
                            for b in sec.bullets:
                                if b.text.strip() == "ネクストアクション" and b.sub:
                                    # NAはラベル＋独立した箇条書きで表示（Notionと同じ見た目）
                                    md += f"\n{b.text}\n\n"
                                    for s in b.sub:
                                        md += f"- {s.text}\n"
                                    continue
                                md += f"- {b.text}\n"
                                for s in b.sub:
                                    md += f"    - {s.text}\n"
                                    md += "".join(f"        - {t}\n" for t in s.sub)
                        if md:
                            st.markdown(md)
                        for n in sec_imgs:  # セクション末尾に固めて表示
                            cap = _caption_text(tmpl["caption"], n,
                                                cap_by_n.get(n, ""), by_n[n]["filename"])
                            st.image(_preview_img(by_n[n]["pil"]), caption=cap)
                    for block in deleted_blocks:  # 丸ごと削除されたセクション
                        st.markdown("\n".join(block))
                    return placed

                st.markdown("### サマリ")
                _show_sections(out.summary,
                               prev_sections=prev.summary if prev else None)
                st.markdown("### 詳細")
                placed = _show_sections(out.details, with_images=True,
                                        prev_sections=prev.details if prev else None)
                leftover = [n for n in sorted(by_n) if n not in placed]
                if leftover:  # 本文で言及されなかった画像は「その他の画像」に並べる
                    st.markdown("##### その他の画像")
                    for n in leftover:
                        cap = _caption_text(tmpl["caption"], n,
                                            cap_by_n.get(n, ""), by_n[n]["filename"])
                        st.image(_preview_img(by_n[n]["pil"]), caption=cap)
                with st.expander("📄 ソース（文字起こし全文・Notionではトグル格納）"):
                    st.text(st.session_state.transcript)

# ---- 予約されたAI処理を実行（右列まで描画し終えてから実行。進捗は「AI処理状況」へ）----
if st.session_state.get("pending"):
    p = st.session_state.pending
    del st.session_state.pending  # エラー時に無限ループしないよう先にクリア
    _status = ai_status if ai_status is not None else st.container()
    with _status:
        _run_pipeline(imgs, tmpl, work_date, p)
    st.session_state.scroll_left = True  # 完了メッセージ（左列STEP4）を見せる
    if p.get("from_reformat"):
        st.session_state.clear_reformat = True  # 反映済みの修正指示テキストをクリア
    st.rerun()
