"""プロンプト変更後の回帰チェック。

固定入力（runs/ のスナップショット＝洗濯機点検の文字起こし＋画像メタ）で整形AIを1回実行し、
過去にデグレした点を含む「構造的な不変条件」を機械検査する。
プロンプト（composer固定フレーム・prompts.jsonのデフォルト）を変更したら、採用前に必ず実行すること。

使い方:
  ./venv/bin/python check_regression.py [runsのJSONパス]
（省略時は GOLDEN_RUN を使用。画像バイトはダミーのグレー画像＝配置判断は文字起こしとメタで行われる）
"""
import io
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = "fieldnotekeeper"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

from PIL import Image

from agents.composer import compose_record
from core.prompts import DEFAULT_TEMPLATES

GOLDEN_RUN = "runs/20260705-144047.json"  # 洗濯機点検（画像6枚・マークあり）


def _dummy_png() -> bytes:
    bio = io.BytesIO()
    Image.new("RGB", (64, 64), "#888888").save(bio, format="PNG")
    return bio.getvalue()


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else GOLDEN_RUN
    d = json.load(open(path, encoding="utf-8"))
    transcript = d["transcript"]
    png = _dummy_png()
    images = [{"n": im["n"], "filename": im["filename"], "bytes": png, "mime": "image/png",
               "marks": im.get("marks", [])} for im in d.get("images", [])]

    print(f"入力: {path}（画像{len(images)}枚・ダミーバイト）")
    print("整形AIを実行中…")
    out = compose_record(transcript, images, dict(DEFAULT_TEMPLATES),
                         work_date=d.get("work_date", "2026-07-05"))

    summary_texts = [b.text for sec in out.summary for b in sec.bullets]
    detail_heads = [sec.heading for sec in out.details]
    placed = [n for sec in out.details for b in sec.bullets for n in b.images]
    has_grand = any(s.sub for sec in out.details for b in sec.bullets for s in b.sub)

    checks = [
        ("画像が本文に配置されている（imagesが1つ以上）", len(placed) > 0),
        ("言及された画像の過半数が配置されている", len(set(placed)) >= 3),
        ("サマリの最後がネクストアクション", bool(summary_texts) and "ネクストアクション" in summary_texts[-1]),
        ("サマリに下した結論（修理をしない旨）が含まれる",
         any(any(k in t for k in ("見送", "行わない", "修理しない", "やめ", "せず"))
             for t in summary_texts)),
        ("詳細に『結果』と『結論・判断』の見出しがある",
         any("結果" in h for h in detail_heads) and any("結論" in h for h in detail_heads)),
        ("結果に3階層（孫）が使われている", has_grand),
        ("全画像分のcaptionsがある", len(out.captions) == len(images)),
        ("1つの親の子が5個以下（チャンクサイズ＝読みやすさ）",
         max((len(b.sub) for sec in out.details for b in sec.bullets), default=0) <= 5),
        ("サマリが4項目以下（3文＋ネクストアクション）", len(summary_texts) <= 4),
    ]

    print()
    ok = True
    for name, passed in checks:
        print(("✅" if passed else "❌"), name)
        ok = ok and passed
    print()
    print("結果:", "PASS（採用してよい）" if ok else "FAIL（プロンプトを見直すこと）")
    if placed:
        print(f"参考: 配置された画像 = {sorted(set(placed))}")
    print("参考: サマリ =")
    for t in summary_texts:
        print("  -", t[:60])
    with open("runs/regression_last_output.json", "w", encoding="utf-8") as f:
        f.write(out.model_dump_json())  # 診断用に最終出力を保存
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
