"""Phase 2 垂直スライス：メモ → 整形 → 検証(1回) → 表示

検証AIは「事実の改変」だけをチェックする。自動修正はしない。
事実改変があれば警告として人に見せ、修正/承認はユーザーが判断する（Human-in-the-loop）。
ワンボタン修正は Streamlit UI（Phase 3）で実装予定。
"""
import os

from dotenv import load_dotenv

load_dotenv()  # .env から NOTION_TOKEN / NOTION_DATABASE_ID を読む

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = "fieldnotekeeper"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

from core.diff import ratio
from core.render import render_record
from core.runlog import save_run
from agents.formatter import format_record, refine_record
from agents.verifier import verify

MEMO = [
    "6/3 樹脂キャップの耐久試験",
    "サンプルA 3個",
    "温度たぶん60℃くらい 湿度は測ってない",
    "5000回開閉でA-1ひび",
    "A-2は8000回でヒンジ割れ",
    "A-3は1万回いけた",
    "前回ロットより弱い気がする。材料ロット変えたから？要確認",
    "次は温度下げて再試験",
    "材料の証明書も確認",
    "山田さんにヒンジ形状の影響ありそうか聞く",
]

def main():
    print("【整形】...")
    rec, fmeta = format_record(MEMO, work_date="2026-06-03")

    print("【検証】...")
    vr, vmeta = verify(rec.sources, rec.summary, rec.details)
    first_verdict = vr.verdict
    first_issues = [i.model_dump() for i in vr.issues]

    # 事実の改変があったときだけ、該当箇所のみ再整形（推測の追加・欠落は表示のみ）
    refine_meta = None
    reverify_meta = None
    fact_issues = [i for i in vr.issues if i.type == "事実の改変"]
    if fact_issues:
        print(f"→ 事実の改変 {len(fact_issues)}件。該当箇所のみ再整形...")
        rec, refine_meta = refine_record(MEMO, rec, fact_issues)
        print("【再検証】...")
        vr, reverify_meta = verify(rec.sources, rec.summary, rec.details)

    # 記録（このままNotionに保存される完成形）
    print("\n" + "=" * 56)
    print("■ 記録（このままNotionに貼れる形）")
    print("=" * 56)
    print(render_record(rec))

    # 検証結果（3種：事実改変は再整形済み／推測・欠落は参考）
    print("\n" + "=" * 56)
    print("■ 検証結果")
    print("=" * 56)
    facts = [i for i in vr.issues if i.type == "事実の改変"]
    others = [i for i in vr.issues if i.type != "事実の改変"]
    if not vr.issues:
        print("✅ 問題なし")
    else:
        if facts:
            print(f"🚨 事実の改変 {len(facts)}件（再整形しても残存）:")
            for x in facts:
                print(f"  - 「{x.draft_says}」← 元「{x.source_says}」（{x.note}）")
        if others:
            print(f"ℹ️ 参考 {len(others)}件（推測の追加・欠落／修正はユーザー判断）:")
            for x in others:
                print(f"  - [{x.type}]「{x.draft_says}」（{x.note}）")
    if fact_issues:
        print("\n※ 事実の改変は検出時に「該当箇所のみ」再整形を実施済み")

    r = ratio("\n".join(MEMO), rec.details)
    print(f"\n[参考] 原文とdetailsの文字一致率: {r:.0%}")

    # 生データ保存（プロンプト・生出力をセットで記録）
    run_data = {
        "input_memo": MEMO,
        "format_1": fmeta,  # 初回整形（model, prompt, raw_output）
        "verify_1": {**vmeta, "verdict": first_verdict, "issues": first_issues},
        "final": {"summary": rec.summary, "details": rec.details, "sources": rec.sources},
        "ratio": r,
    }
    if refine_meta:
        run_data["refine"] = refine_meta  # 事実改変の再整形
        run_data["verify_2"] = {
            **reverify_meta,
            "verdict": vr.verdict,
            "issues": [i.model_dump() for i in vr.issues],
        }
    path = save_run(run_data)
    print(f"\n📁 生データ（プロンプト・生出力の全量）: {path}")

    # Notion保存（NOTION_TOKEN があれば保存。承認フローは将来UIで）
    if os.environ.get("NOTION_TOKEN"):
        from tools.notion_tools import save_record
        url = save_record(rec, rec.title or MEMO[0])
        print(f"📝 Notion保存: {url}")
    else:
        print("（NOTION_TOKEN 未設定 → Notion保存はスキップ。設定すれば自動保存されます）")


if __name__ == "__main__":
    main()
