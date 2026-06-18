"""FieldNoteKeeper Streamlit UI（Phase 3）
メモ入力 → 整形＆検証 → （事実改変だけ修正）→ プレビュー → Notion保存
実行: ./venv/bin/streamlit run app.py
"""
import os

from dotenv import load_dotenv

load_dotenv()  # .env から NOTION_TOKEN / NOTION_DATABASE_ID
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = "fieldnotekeeper"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

import streamlit as st

from agents.formatter import format_record, refine_record
from agents.verifier import verify
from core.render import render_record
from tools.notion_tools import save_record

st.set_page_config(page_title="FieldNoteKeeper", page_icon="🧪")
st.title("🧪 FieldNoteKeeper")
st.caption("走り書きメモ → 整形 → 事実検証 → Notion保存")

PLACEHOLDER = """6/3 樹脂キャップの耐久試験
サンプルA 3個
温度たぶん60℃くらい 湿度は測ってない
5000回開閉でA-1ひび
A-2は8000回でヒンジ割れ
A-3は1万回いけた
前回ロットより弱い気がする。材料ロット変えたから？要確認"""

# ---- 入力 ----
memo_text = st.text_area("メモ（1行1項目）", height=220, placeholder=PLACEHOLDER)
work_date = st.date_input("作業日")
uploaded = st.file_uploader(
    "画像（任意・複数可。ドラッグ&ドロップ可）",
    accept_multiple_files=True,
    type=["png", "jpg", "jpeg", "webp", "gif"],
)

if st.button("整形して検証", type="primary"):
    lines = [ln.strip() for ln in memo_text.splitlines() if ln.strip()]
    if not lines:
        st.warning("メモを入力してください")
    else:
        with st.spinner("整形中…"):
            rec, _ = format_record(lines, work_date=str(work_date))
        with st.spinner("検証中…"):
            vr, _ = verify(rec.sources, rec.summary, rec.details)
        st.session_state.rec = rec
        st.session_state.vr = vr
        st.session_state.saved_url = None

# ---- 結果 ----
if "rec" in st.session_state:
    rec = st.session_state.rec
    vr = st.session_state.vr

    st.divider()
    st.subheader("検証結果")
    facts = [i for i in vr.issues if i.type == "事実の改変"]
    others = [i for i in vr.issues if i.type != "事実の改変"]

    if not vr.issues:
        st.success("✅ 問題なし — そのまま承認できます")
    else:
        if facts:
            st.error(f"🚨 事実の改変 {len(facts)}件")
            for x in facts:
                st.write(f"- 「{x.draft_says}」← 元「{x.source_says}」（{x.note}）")
            if st.button("事実の改変を修正（該当箇所だけ直す）"):
                with st.spinner("修正中…"):
                    rec, _ = refine_record(rec.sources, rec, facts)
                    vr, _ = verify(rec.sources, rec.summary, rec.details)
                st.session_state.rec = rec
                st.session_state.vr = vr
                st.rerun()
        if others:
            st.info(f"ℹ️ 参考 {len(others)}件（推測の追加・欠落／修正は任意）")
            for x in others:
                st.write(f"- [{x.type}]「{x.draft_says}」（{x.note}）")

    st.divider()
    st.subheader("記録プレビュー（このままNotionに保存）")
    st.markdown(render_record(rec))

    st.divider()
    if uploaded:
        st.caption(f"添付画像 {len(uploaded)}件：" + ", ".join(f.name for f in uploaded))

    if st.button("✅ 承認してNotionに保存", type="primary"):
        with st.spinner("保存中…（画像があればDriveにも）"):
            if uploaded and os.environ.get("DRIVE_OAUTH_CLIENT"):
                from tools.drive_tools import create_record_folder, upload_image
                yymmdd = rec.work_date[2:].replace("-", "") if rec.work_date else "nodate"
                folder_id, folder_url = create_record_folder(f"{yymmdd}_{rec.title}")
                rec.images = [
                    upload_image(folder_id, f.name, f.getvalue(), f.type) for f in uploaded
                ]
                rec.drive_folder_url = folder_url
                st.session_state.rec = rec
            elif uploaded:
                st.warning("この環境ではDrive保存が未設定のため、画像はスキップしてテキストのみ保存します")
            url = save_record(rec, rec.title)
        st.session_state.saved_url = url

    if st.session_state.get("saved_url"):
        st.success(f"保存しました 👉 {st.session_state.saved_url}")
