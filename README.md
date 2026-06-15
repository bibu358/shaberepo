# FieldNoteKeeper

実験・現場作業の走り書き（PCメモ・手書きメモ・写真・データ）を、短時間・省力のまま
「見やすく・十分で・チームで二次活用できる記録資産」に変えるAIエージェント。

DevOps × AI Agent Hackathon 2026（Google Cloud / Findy）

## 技術スタック
- ADK (Agent Development Kit) + Gemini (Vertex AI)
- Streamlit (UI) / diff表示は difflib
- Cloud Run (deploy) + GitHub Actions (CI/CD)
- Notion DB (記録の保存先)

## 状態
Phase 0（セットアップ・疎通）完了。MVP開発中。

## ローカル実行（開発用）
```sh
python3.12 -m venv venv
./venv/bin/pip install -r requirements.txt   # 後日整備
./venv/bin/python hello_adk.py               # ADK疎通確認
```
