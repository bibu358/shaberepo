# しゃべれぽAI

実験・調査などの活動を、音声と画像から Notion に記録化する AI エージェント。

DevOps × AI Agent Hackathon 2026（Google Cloud / Findy）提出作品。

| リンク | URL |
|---|---|
| 🚀 アプリ（Cloud Run） | https://fieldnotekeeper-mthwpora2q-an.a.run.app |
| 📕 ProtoPedia（作品ページ） | https://protopedia.net/prototype/8805 |
| 🎬 デモ動画 | https://www.youtube.com/watch?v=TnPN72RezY4 |

## これは何？

作業のことを口頭で説明し、必要なら画像にクリックでマーク（A, B…）を付けると、AIが構造化された記録（背景・目的／やったこと／結果／考察／結論・判断／ネクストアクション）に整形し、検証を経て Notion に保存します。

設計の核は「**構造はプログラム、中身はAI**」。記録の骨格・書式・画像の描画はプログラムが担保し、AIは事実を変えずに内容を埋めます。検証AIが「ソース（文字起こし・画像）と記録の間で事実が保たれているか」をチェックし、事実の改変は自動修復します。

## スクリーンショット

| 入力（音声・画像・マーク） | 画像へのマーク | 完成した記録と検証結果 |
|---|---|---|
| ![入力画面](docs/protopedia/CleanShot%202026-07-10%20at%2002.01.27@2x.png) | ![画像にマーク](docs/protopedia/CleanShot%202026-07-10%20at%2002.01.57@2x.png) | ![完成した記録](docs/protopedia/CleanShot%202026-07-10%20at%2002.02.53@2x.png) |

## 特徴

- **4つのAIエージェント**：① 文字起こし（音声→テキスト）→ ② 整形（構造化記録の生成・structured output）→ ③ 検証（ソースとの事実照合）→ ④ 修正（事実の改変だけを自動修復し再検証・最大2周）
- **事実ガード**：検証AIが「事実の改変／推測の追加／欠落」を検出。改変は自動修復し、残りはユーザーがレビューして承認
- **画像とマークの対応づけ**：画像をクリックして丸・矢印のマーク（A, B…）を付け、「3枚目のAは〜」と話すと、キャプション付きで記録の適切なセクションに配置される
- **部分修正**：作成後の記録に対し、指示（テキスト or 音声）した箇所だけを修正（他は変えない）。変更箇所は差分ハイライトで確認できる
- **プロンプト設定**：記録の書式・構成をUIから編集できる。AIへの修正依頼→差分レビュー→適用のフローつき
- **AIコストの可視化**：1回の記録作成で消費したトークン数と推定金額を表示

## 使い方（2〜3分で試せます）

1. アプリを開く → 作業日を入力
2. 画像をアップロード（任意）。「画像にマーク」で画像をクリックするとA, B…のマークが付く
3. 「録音開始」を押し、やったこと・結果などを口頭で説明（「話す時のコツ」に台本あり）
4. 「記録を作成する」→ 検証結果とプレビューを確認 →「承認してNotionに保存」

> ⚠️ **注意：秘密情報を入れないでください。** 本アプリはデモ用の単一アカウント構成で、作成した記録（音声の文字起こし・画像）はすべて**開発者の Notion / Google Drive に保存されます**。お試しの際は、公開されて困らない内容でお願いします。

## アーキテクチャ

![システムアーキテクチャ図](docs/architecture.png)

Streamlit（Cloud Run）がUIとパイプライン制御を担い、AIエージェント層が Vertex AI（Gemini 2.5 Flash）を呼び出します。ユーザーが承認した記録のみ Notion に保存され（画像は File Upload API で直接アップロード）、無加工の元画像は Google Drive にバックアップされます。詳細は [docs/architecture.md](docs/architecture.md)。

## 技術スタック

| 領域 | 技術 |
|---|---|
| AI | Gemini 2.5 Flash（Vertex AI・structured output） |
| UI | Streamlit |
| インフラ | Cloud Run（asia-northeast1）・Secret Manager |
| CI/CD | GitHub Actions（main への push → Cloud Build → 自動デプロイ） |
| 保存先 | Notion API（ページ作成・画像 File Upload）・Google Drive API（OAuth） |
| 画像処理 | Pillow（マーク描画・Noto Sans JP 同梱） |

## リポジトリ構成

```
app.py               # Streamlit UI（2列レイアウト・実行ロック・差分表示・プロンプト設定）
agents/              # AIエージェント層
  transcribe.py      #   ① 文字起こしAI
  composer.py        #   ② 整形AI（＋部分修正 revise / ④ 修正AI refine・画像配置の補完）
  verifier.py        #   ③ 検証AI（事実の改変・推測の追加・欠落）
  prompt_editor.py   #   プロンプト修正AI（設定ページのAI提案）
core/                # スキーマ（structured output）・プロンプト・マーク描画・diff・コスト集計
tools/               # Notion保存（markdown→ブロック変換）・Drive保存
check_regression.py  # プロンプト変更時の回帰チェック（固定入力で構造的不変条件を機械検査）
docs/                # アーキテクチャ図・提出資料
```

## ローカル開発

```sh
python3.12 -m venv venv
./venv/bin/pip install -r requirements.txt

# .env に以下を設定：
#   NOTION_TOKEN / NOTION_DATABASE_ID（Notion コネクトのトークンと保存先DB）
#   DRIVE_OAUTH_CLIENT / DRIVE_PARENT_FOLDER_ID（Drive バックアップ・任意）
# Gemini は Vertex AI 経由（gcloud auth application-default login で ADC 認証）

./venv/bin/streamlit run app.py

# プロンプトを変更したら、採用前に回帰チェックを実行
./venv/bin/python check_regression.py
```
