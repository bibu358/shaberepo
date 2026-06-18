"""Record を Notion 等に貼り付ける完成形テキスト（markdown）に整形する"""
from core.schema import Record


def render_record(rec: Record) -> str:
    """サマリ＋ソース（原文＋画像）＋詳細 を1つの記録テキストにまとめる"""
    sources = "\n".join(f"- {s}" for s in rec.sources)
    md = (
        "## サマリ\n"
        f"{rec.summary}\n\n"
        "## ソース（原文メモ）\n"
        f"{sources}\n"
    )
    if rec.images:
        imgs = "\n".join(f"- {u}" for u in rec.images)
        md += "\n### 画像\n" f"{imgs}\n"
    md += "\n## 詳細\n" f"{rec.details}\n"
    return md
