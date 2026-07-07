"""しゃべれぽAI のデータ型（Pydantic）"""
from pydantic import BaseModel


# ---- 構造化記録（2026-07-02 AIフロー再設計）----
# 原則「構造はプログラム、中身はAI」：AIはmarkdownを書かず、この型の穴埋めだけを行う。
# 見出しレベル・箇条書き記法・階層のレンダリングは100%プログラム側（notion_tools）。

class SubItem(BaseModel):
    """箇条書きの子項目（さらに孫を持てる＝帰属→主張→根拠の3階層を表現）"""
    text: str
    sub: list[str] = []     # 孫項目（根拠の詳細・具体値など）


class Bullet(BaseModel):
    """箇条書き1項目。textは記法なしの素の文（先頭に - や ・ を付けない）。"""
    text: str
    sub: list[SubItem] = []  # 子項目（主張・根拠など。各子は孫subを持てる）
    images: list[int] = []   # この項目が言及する画像番号（1始まり。セクション末尾に表示）


class Section(BaseModel):
    heading: str
    bullets: list[Bullet]


class Caption(BaseModel):
    """画像キャプションの中身。書式（画像N：…（ファイル名））はプログラムが付与。"""
    n: int        # 画像番号（1始まり）
    desc: str     # 説明文のみ


class FormatOutput(BaseModel):
    """整形AI（②）の出力＝構造化記録"""
    title: str
    one_liner: str = ""            # 「これなに？」＝この記録が何かの1行説明
    summary: list[Section]
    details: list[Section]
    did: str                       # やったこと1行（Notionプロパティ）
    result: str                    # 結果1行（Notionプロパティ）
    captions: list[Caption] = []


class TranscriptOutput(BaseModel):
    """文字起こしAI（①）の出力"""
    transcript: str


# ---- 以下は旧フローの型（run_slice等の互換のため残置）----

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


class VoiceOutput(BaseModel):
    """音声整形AIの出力。transcript＝文字起こし全文（＝ソース/原文）"""
    transcript: str
    title: str
    summary: str
    details: str
    did: str
    result: str


class MarkSpec(BaseModel):
    """画像注釈の1マーク。位置はクリック座標(points[index-1])を使う。"""
    index: int           # クリック位置の番号（A=1, B=2 …）
    type: str            # circle / arrow / rect
    label: str = ""
    color: str = "red"
    size: int = 40


class MarkPlan(BaseModel):
    marks: list[MarkSpec]
    description: str = ""  # 画像全体の説明（キャプション用の1行）


class ImagePlacement(BaseModel):
    """画像を本文のどの行の後に置くか（位置だけ。本文は変えない）。"""
    n: int                # 画像番号（1始まり）
    after_line: str = ""  # この行（本文からそのまま抜粋）の後に挿入。適切な行が無ければ空


class ImagePlacements(BaseModel):
    items: list[ImagePlacement]


class Issue(BaseModel):
    """検証AIが見つけた矛盾1件"""
    type: str          # "事実の改変" / "推測の追加" / "欠落"
    section: str = ""  # 指摘箇所のセクション名（サマリ／結果／考察 など）
    source_says: str   # 元データ（ソース）の記述
    draft_says: str    # ドラフト（整形結果）の記述
    note: str          # 説明


class VerifyResult(BaseModel):
    """検証AI（事実ガード）の結果"""
    verdict: str       # "問題あり" / "問題なし"
    issues: list[Issue]
