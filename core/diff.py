"""差分・原文保持の評価ユーティリティ"""
import difflib


def ratio(old: str, new: str) -> float:
    """文字ベースの一致率（参考値・順序変更で下がる）"""
    return difflib.SequenceMatcher(None, old, new).ratio()
