"""差分・原文保持の評価ユーティリティ

diff_section_lines：再整形の前後（Section群）を比較し、プレビューにそのまま流せる
色付きmarkdown行を返す（🟢追加=green背景・🔴削除=赤取り消し線。
変更は「旧行の削除＋新行の追加」として表示＝変更前の内容が常に見える）。
"""
import difflib


def ratio(old: str, new: str) -> float:
    """文字ベースの一致率（参考値・順序変更で下がる）"""
    return difflib.SequenceMatcher(None, old, new).ratio()


def _atom(b) -> str:
    """Bullet → 比較キー（text・子・孫をまとめて1項目として扱う）"""
    parts = [b.text]
    for s in b.sub:
        parts.append(s.text)
        parts.extend(s.sub)
    return "\x00".join(parts)


def _bullet_lines(b, mark: str = "") -> list[str]:
    """Bullet（子・孫つき）→ markdown行。markで🟢追加/🔴削除の色付け"""
    def fmt(text, depth):
        pad = "    " * depth
        if mark == "green":
            return f"{pad}- :green-background[{text}]"
        if mark == "red":
            return f"{pad}- :red[~~{text}~~]"
        return f"{pad}- {text}"
    lines = [fmt(b.text, 0)]
    for s in b.sub:
        lines.append(fmt(s.text, 1))
        lines.extend(fmt(t, 2) for t in s.sub)
    return lines


def _green(b) -> list[str]:
    return _bullet_lines(b, "green")


def _red(b) -> list[str]:
    return _bullet_lines(b, "red")


def diff_section_lines(old_sections, new_sections):
    """新セクション群それぞれの「色付きmarkdown行リスト」と、削除されたセクションのブロックを返す。
    戻り値: (per_section_lines: list[list[str]], deleted_blocks: list[list[str]])
    """
    old_by_head = {(s.heading or "").strip(): s for s in old_sections}
    per_section = []
    for ns in new_sections:
        os_ = old_by_head.get((ns.heading or "").strip())
        lines = []
        if os_ is None:  # セクションごと新規
            for b in ns.bullets:
                lines += _green(b)
            per_section.append(lines)
            continue
        sm = difflib.SequenceMatcher(
            None, [_atom(b) for b in os_.bullets], [_atom(b) for b in ns.bullets])
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                for b in ns.bullets[j1:j2]:
                    lines += _bullet_lines(b)
            elif op == "insert":
                for b in ns.bullets[j1:j2]:
                    lines += _green(b)
            elif op == "delete":
                for b in os_.bullets[i1:i2]:
                    lines += _red(b)
            else:  # replace（変更）＝旧行の削除＋新行の追加として表示（変更前が見える）
                for b in os_.bullets[i1:i2]:
                    lines += _red(b)
                for b in ns.bullets[j1:j2]:
                    lines += _green(b)
        per_section.append(lines)

    # 丸ごと削除されたセクション（見出しが新側に無い）
    new_heads = {(s.heading or "").strip() for s in new_sections}
    deleted_blocks = []
    for os_ in old_sections:
        h = (os_.heading or "").strip()
        if h and h not in new_heads:
            block = [f"##### :red[~~{h}~~]"]
            for b in os_.bullets:
                block += _red(b)
            deleted_blocks.append(block)
    return per_section, deleted_blocks
