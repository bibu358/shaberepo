"""FieldNoteKeeper のデータ型（Pydantic）"""
from pydantic import BaseModel


class Record(BaseModel):
    """1件の記録。サマリ＋ソース（原文保持）＋詳細 ＋ Notionプロパティ用メタ。"""
    title: str = ""              # 題名（Notion Title）
    summary: str                 # AIが作る概要
    sources: list[str]           # 原文の走り書き（そのまま保持）
    details: str                 # 構造化された詳細（markdown）
    did: str = ""                # やったこと（1行・Notionプロパティ用）
    result: str = ""             # 結果（1行・Notionプロパティ用）
    work_date: str | None = None  # 作業日 YYYY-MM-DD（入力時に指定）
    author: str | None = None     # 作業者＝NotionユーザーID（入力時に指定）
    images: list[str] = []               # 画像のDrive URL
    drive_folder_url: str | None = None  # 記録ごとDriveフォルダのURL


class FormatterOutput(BaseModel):
    """整形AIが生成する部分（sources は原文をそのまま使うので含めない）"""
    title: str
    summary: str
    details: str
    did: str
    result: str


class Issue(BaseModel):
    """検証AIが見つけた矛盾1件"""
    type: str          # "事実の改変" / "推測の追加" / "欠落"
    source_says: str   # 元データ（ソース）の記述
    draft_says: str    # ドラフト（整形結果）の記述
    note: str          # 説明


class VerifyResult(BaseModel):
    """検証AI（事実ガード）の結果"""
    verdict: str       # "問題あり" / "問題なし"
    issues: list[Issue]
