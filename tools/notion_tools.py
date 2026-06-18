"""承認済み Record を Notion DB に1ページとして保存する。

必要な環境変数：
- NOTION_TOKEN        : Notion integration の token（secret_…）
- NOTION_DATABASE_ID  : 保存先DBの database_id

プロパティ：題名 / 作業日 / 作業者 / やったこと / 結果
本文：## サマリ → ## ソース（原文） → ## 詳細
"""
import os

from notion_client import Client

from core.schema import Record


def _h2(text: str) -> dict:
    return {"object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]}}


def _para(text: str) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]}}


def _bullet(text: str) -> dict:
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": text}}]}}


def _h3(text: str) -> dict:
    return {"object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": text}}]}}


def _blocks(rec: Record) -> list[dict]:
    blocks = [_h2("サマリ"), _para(rec.summary), _h2("ソース（原文メモ）")]
    blocks += [_bullet(s) for s in rec.sources]
    if rec.images:
        blocks.append(_h3("画像"))
        blocks += [_bullet(u) for u in rec.images]
    blocks += [_h2("詳細"), _para(rec.details)]
    return blocks


def _full_title(rec: Record, title: str | None) -> str:
    """YYYY/MM/DD_タイトル 形式（作業日があれば前置）"""
    base = title or rec.title
    if rec.work_date:
        return f"{rec.work_date.replace('-', '/')}_{base}"
    return base


def save_record(rec: Record, title: str | None = None) -> str:
    """Record を1ページ作成し、ページURLを返す"""
    notion = Client(auth=os.environ["NOTION_TOKEN"])
    db_id = os.environ["NOTION_DATABASE_ID"]

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
        children=_blocks(rec),
    )
    return page["url"]
