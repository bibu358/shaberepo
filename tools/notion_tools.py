"""承認済み Record を Notion DB に1ページとして保存する。

必要な環境変数：
- NOTION_TOKEN        : Notion integration の token（secret_…）
- NOTION_DATABASE_ID  : 保存先DBの database_id

プロパティ：題名 / 作業日 / 作業者 / やったこと / 結果
本文：## サマリ → ## ソース（原文） → ## 詳細
"""
import os
import re

import requests
from notion_client import Client

from core.schema import Record, FormatOutput

NOTION_VERSION = "2022-06-28"


def _upload_to_notion(data: bytes, filename: str, mimetype: str = "image/png") -> str:
    """Notion File Upload API で画像を直接アップロードし file_upload id を返す。"""
    token = os.environ["NOTION_TOKEN"]
    h = {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION}
    # 1. アップロード枠を作成
    r = requests.post(
        "https://api.notion.com/v1/file_uploads",
        headers={**h, "Content-Type": "application/json"},
        json={"filename": filename, "content_type": mimetype},
        timeout=60,
    )
    r.raise_for_status()
    up = r.json()
    # 2. ファイル送信
    r2 = requests.post(
        up["upload_url"], headers=h,
        files={"file": (filename, data, mimetype)}, timeout=120,
    )
    r2.raise_for_status()
    return up["id"]


def _h2(text: str, color: str = None) -> dict:
    h = {"rich_text": [{"type": "text", "text": {"content": text}}]}
    if color:
        h["color"] = color
    return {"object": "block", "type": "heading_2", "heading_2": h}


_URL_RE = re.compile(r"https?://[^\s　）)】>」]+")


def _rich(text: str) -> list[dict]:
    """テキスト中のURLをクリック可能なリンクにした rich_text 配列を返す"""
    parts, last = [], 0
    for m in _URL_RE.finditer(text):
        if m.start() > last:
            parts.append({"type": "text", "text": {"content": text[last:m.start()]}})
        parts.append({"type": "text",
                      "text": {"content": m.group(0), "link": {"url": m.group(0)}}})
        last = m.end()
    if last < len(text):
        parts.append({"type": "text", "text": {"content": text[last:]}})
    return parts or [{"type": "text", "text": {"content": ""}}]


def _para(text: str) -> dict:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich(text)}}


def _bullet(text: str) -> dict:
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": _rich(text)}}


def _h3(text: str) -> dict:
    return {"object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": text}}]}}


def _md_to_blocks(md: str, image_items=None) -> list[dict]:
    """簡易markdown → Notionブロック。[[画像N]] は image_items[N-1] の画像に置換。"""
    out = []
    for raw in md.split("\n"):
        s = raw.strip()
        if not s:
            continue
        m = re.fullmatch(r"\[\[画像(\d+)\]\]", s)
        if m and image_items:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(image_items):
                iid, cap = image_items[idx]
                out.append(_image_block(iid, cap))
            continue
        if s.startswith("### "):
            out.append(_h3(s[4:]))
        elif s.startswith("## "):
            out.append(_h2(s[3:]))
        elif s.startswith("- "):
            out.append(_bullet(s[2:]))
        elif s.startswith("・"):
            out.append(_bullet(s[1:]))
        else:
            out.append(_para(s))
    return out


def _image_block(file_upload_id: str, caption: str = "") -> dict:
    """Notionにアップロード済みの画像（file_upload）を貼るブロック（caption付き）。"""
    img = {"type": "file_upload", "file_upload": {"id": file_upload_id}}
    if caption:
        img["caption"] = [{"type": "text", "text": {"content": caption}}]
    return {"object": "block", "type": "image", "image": img}


def _image_block_small(file_upload_id: str, caption: str = "") -> dict:
    """画像を2カラムの左側に入れ、表示幅を約半分にする（文章の読みやすさ優先）。
    アップロードはフル解像度のまま＝Notion上でクリック拡大すれば元の解像度で見られる。"""
    return {"object": "block", "type": "column_list", "column_list": {"children": [
        {"object": "block", "type": "column",
         "column": {"children": [_image_block(file_upload_id, caption)]}},
        {"object": "block", "type": "column",
         "column": {"children": [_para("")]}},
    ]}}


def _blocks(rec: Record, image_items=None) -> list[dict]:
    """image_items: [(file_upload_id, caption), ...]。詳細本文の [[画像N]] 位置に画像を挿入。"""
    blocks = [_h2("サマリ")]
    blocks += _md_to_blocks(rec.summary, image_items)
    blocks.append(_h2("ソース（原文メモ）"))
    blocks += [_bullet(s) for s in rec.sources]
    blocks.append(_h2("詳細"))
    blocks += _md_to_blocks(rec.details, image_items)
    return blocks


def _full_title(rec: Record, title: str | None) -> str:
    """YYYY/MM/DD_タイトル 形式（作業日があれば前置）"""
    base = title or rec.title
    if rec.work_date:
        return f"{rec.work_date.replace('-', '/')}_{base}"
    return base


# ---- 構造化記録の保存（2026-07-02 AIフロー再設計）----
# 「構造はプログラム、中身はAI」：見出し・箇条書き・階層・トグルは全てここで組む。

def _clean(text: str) -> str:
    """AIが誤って付けた行頭記号を除去（二重防御）"""
    return text.lstrip("-・•●○* 　").strip()


def _bullet_nested(text: str, sub=None, extra_children: list[dict] = None) -> dict:
    """箇条書き（sub は子ブロック。子はさらに孫を持てる＝最大3階層）"""
    b = _bullet(_clean(text))
    children = []
    for s in sub or []:
        if isinstance(s, str):  # 旧形式（文字列）互換
            children.append(_bullet(_clean(s)))
            continue
        child = _bullet(_clean(s.text))
        grand = [_bullet(_clean(t)) for t in (s.sub or [])]
        if grand:
            child["bulleted_list_item"]["children"] = grand
        children.append(child)
    children += extra_children or []
    if children:
        b["bulleted_list_item"]["children"] = children
    return b


def _toggle(title: str, children: list[dict]) -> dict:
    return {"object": "block", "type": "toggle",
            "toggle": {"rich_text": [{"type": "text", "text": {"content": title}}],
                       "children": children}}


def _chunks(text: str, size: int = 1900) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def _section_blocks(sections, image_map=None, placed=None) -> list[dict]:
    """Section群 → h3＋ネスト箇条書き。Bullet.images の画像は
    そのセクションの末尾にまとめて配置する。"""
    out = []
    placed = placed if placed is not None else set()
    for sec in sections:
        if (sec.heading or "").strip():  # 空見出し（サマリ等）はスキップ
            out.append(_h3(_clean(sec.heading)))
        sec_imgs = []
        for b in sec.bullets:
            out.append(_bullet_nested(b.text, b.sub))
            for n in b.images or []:
                if image_map and n in image_map and n not in placed:
                    sec_imgs.append(n)
                    placed.add(n)
        for n in sec_imgs:  # セクション末尾に固めて配置（表示は半幅・解像度は維持）
            iid, cap = image_map[n]
            out.append(_image_block_small(iid, cap))
    return out


def save_structured(out: FormatOutput, transcript: str, work_date: str | None = None,
                    image_blobs=None, drive_folder_url: str | None = None,
                    drive_image_links=None) -> str:
    """構造化記録を1ページ作成し、ページURLを返す。
    image_blobs: [(filename, bytes, caption[, mimetype])] を画像1..Nの順で渡す。
    drive_image_links: [(ラベル, DriveのURL)]（ソースの「画像」に列挙）
    本文構成：サマリ → 詳細（画像は言及セクション末尾・未配置は「その他の画像」）
             → ソース（画像のDriveリンク＋文字起こしトグル）
    """
    notion = Client(auth=os.environ["NOTION_TOKEN"])
    db_id = os.environ["NOTION_DATABASE_ID"]

    # 画像アップロード（n → (file_upload_id, caption)）。失敗してもテキストは保存
    image_map = {}
    for i, item in enumerate(image_blobs or [], 1):
        name, data, cap = item[0], item[1], item[2]
        mime = item[3] if len(item) > 3 else "image/png"
        try:
            image_map[i] = (_upload_to_notion(data, name, mime), cap)
        except Exception:
            pass

    GRAY = "gray_background"
    placed = set()
    blocks = []
    if (out.one_liner or "").strip():
        blocks.append(_h2("これなに？", GRAY))
        blocks.append(_para(out.one_liner.strip()))
    blocks.append(_h2("サマリ", GRAY))
    for sec in out.summary:
        for b in sec.bullets:
            if b.text.strip() == "ネクストアクション" and b.sub:
                # NAは箇条書きでなくラベル＋独立した箇条書きで表示（読みやすさ優先）
                blocks.append(_para("ネクストアクション"))
                for s in b.sub:
                    blocks.append(_bullet(_clean(s if isinstance(s, str) else s.text)))
            else:
                blocks.append(_bullet_nested(b.text, b.sub))
    blocks.append(_h2("詳細", GRAY))
    blocks += _section_blocks(out.details, image_map, placed)
    leftover = [n for n in sorted(image_map) if n not in placed]
    if leftover:                         # 本文に配置されなかった画像は「その他の画像」へ
        blocks.append(_h3("その他の画像"))
        for n in leftover:
            iid, cap = image_map[n]
            blocks.append(_image_block_small(iid, cap))
    blocks.append(_h2("ソース", GRAY))
    if drive_image_links:
        blocks.append(_h3("画像"))
        for label, url in drive_image_links:
            blocks.append(_bullet(f"{label}: {url}"))  # URLは_richで自動リンク化
    blocks.append(_h3("文字起こし"))
    paras = [_para(c) for p in transcript.split("\n\n") if p.strip() for c in _chunks(p.strip())]
    blocks.append(_toggle("文字起こし全文", paras[:100]))

    title = f"{work_date.replace('-', '/')}_{out.title}" if work_date else out.title
    props = {
        "題名": {"title": [{"text": {"content": title}}]},
        "やったこと": {"rich_text": [{"text": {"content": out.did}}]},
        "結果": {"rich_text": [{"text": {"content": out.result}}]},
    }
    if work_date:
        props["作業日"] = {"date": {"start": work_date}}
    if drive_folder_url:
        props["DriveフォルダURL"] = {"url": drive_folder_url}

    page = notion.pages.create(parent={"database_id": db_id}, properties=props, children=blocks)
    return page["url"]


def save_record(rec: Record, title: str | None = None, image_blobs=None) -> str:
    """Record を1ページ作成し、ページURLを返す。
    image_blobs: [(filename, bytes), ...] があれば Notion に直接アップロードして本文に貼る。
    """
    notion = Client(auth=os.environ["NOTION_TOKEN"])
    db_id = os.environ["NOTION_DATABASE_ID"]

    # 画像をNotionに直接アップロード（(file_upload id, caption) を集める）
    image_items = []
    if image_blobs:
        for name, data, cap in image_blobs:
            try:
                image_items.append((_upload_to_notion(data, name), cap))
            except Exception:
                pass  # 画像失敗でもテキストは保存する

    props = {
        "題名": {"title": [{"text": {"content": _full_title(rec, title)}}]},
        "やったこと": {"rich_text": [{"text": {"content": rec.did}}]},
        "結果": {"rich_text": [{"text": {"content": rec.result}}]},
    }
    if rec.work_date:
        props["作業日"] = {"date": {"start": rec.work_date}}
    if rec.author:
        props["作業者"] = {"people": [{"id": rec.author}]}
    if rec.drive_folder_url:
        props["DriveフォルダURL"] = {"url": rec.drive_folder_url}

    page = notion.pages.create(
        parent={"database_id": db_id},
        properties=props,
        children=_blocks(rec, image_items),
    )
    return page["url"]
