"""Record を Notion 等に貼り付ける完成形テキスト（markdown）に整形する"""
from core.schema import Record, FormatOutput


def render_structured(out: FormatOutput) -> str:
    """構造化記録（FormatOutput）→ 検証AI・プレビュー用のテキスト"""
    lines = [f"# {out.title}", ""]
    if (out.one_liner or "").strip():
        lines += ["## これなに？", out.one_liner, ""]
    def _bullet_lines(b, imgs_note: str = ""):
        ls = [f"- {b.text}{imgs_note}"]
        for s in b.sub:
            ls.append(f"    - {s.text}")
            ls.extend(f"        - {t}" for t in s.sub)
        return ls

    lines.append("## サマリ")
    for sec in out.summary:
        if (sec.heading or "").strip():
            lines.append(f"### {sec.heading}")
        for b in sec.bullets:
            lines.extend(_bullet_lines(b))
    lines.append("")
    lines.append("## 詳細")
    for sec in out.details:
        lines.append(f"### {sec.heading}")
        for b in sec.bullets:
            imgs = "".join(f" ［ここに画像{n}を配置］" for n in b.images)
            lines.extend(_bullet_lines(b, imgs))
    caps = [c for c in out.captions if (c.desc or "").strip()]  # 言及なし画像（desc空）は載せない
    if caps:
        lines.append("")
        lines.append("## 画像キャプション")
        lines.extend(f"- 画像{c.n}：{c.desc}" for c in caps)
    lines += ["", "## プロパティ（Notion一覧用の1行要約）",
              f"- やったこと: {out.did}", f"- 結果: {out.result}"]
    return "\n".join(lines)


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
