"""画像を Google Drive に保管する（OAuth ユーザー認証）。

個人Gmailではサービスアカウントに保存容量が無くアップロードできない
（"Service Accounts do not have storage quota"）ため、
ユーザー本人のOAuth認証（本人の容量）を使う。
※組織のWorkspaceなら「共有ドライブ＋SA」の方が楽。

環境変数（ローカル）：
- DRIVE_OAUTH_CLIENT      : OAuthクライアントの credentials JSON パス
- DRIVE_OAUTH_TOKEN       : 認証トークンの保存先（既定 token.json）
- DRIVE_PARENT_FOLDER_ID  : 画像を入れる親フォルダID

環境変数（Cloud Run など）：
- DRIVE_OAUTH_TOKEN_JSON  : token.json の「中身」（Secret Manager等で注入）。
                            refresh_token を含むのでブラウザ無しで認証が回る。

ローカル初回だけ `authorize_drive.py` を実行 → ブラウザ同意 → token.json 作成。
"""
import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME = "application/vnd.google-apps.folder"


def get_credentials() -> Credentials:
    """トークンを取得する。
    - Cloud Run等：環境変数 DRIVE_OAUTH_TOKEN_JSON（token.jsonの中身）から読む。
      refresh_token を含むのでブラウザ無しで自動更新できる（ファイルには書き戻さない）。
    - ローカル：token.json ファイルを使い、無ければブラウザ同意で作成・保存。
    """
    token_json = os.environ.get("DRIVE_OAUTH_TOKEN_JSON")  # Cloud Run: 中身
    token_path = os.environ.get("DRIVE_OAUTH_TOKEN", "token.json")  # ローカル: パス

    creds = None
    if token_json:
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    elif os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())  # access_tokenをメモリ上で更新
        elif token_json:
            # Cloud Run等：対話フローは不可。トークンが無効なら再生成が必要
            raise RuntimeError(
                "Drive認証トークンが無効です。ローカルで token.json を再生成して Secret を更新してください。"
            )
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                os.environ["DRIVE_OAUTH_CLIENT"], SCOPES
            )
            creds = flow.run_local_server(port=0)
        # 書き戻しはローカル（ファイル運用）のときだけ。Cloud Runはファイルシステムが読み取り専用
        if not token_json:
            with open(token_path, "w") as f:
                f.write(creds.to_json())
    return creds


def _drive():
    return build("drive", "v3", credentials=get_credentials())


def create_record_folder(name: str) -> tuple[str, str]:
    """親フォルダ直下に name フォルダを作成。 (folder_id, folder_url) を返す"""
    drive = _drive()
    meta = {
        "name": name,
        "mimeType": FOLDER_MIME,
        "parents": [os.environ["DRIVE_PARENT_FOLDER_ID"]],
    }
    f = drive.files().create(
        body=meta, fields="id, webViewLink", supportsAllDrives=True
    ).execute()
    return f["id"], f["webViewLink"]


def create_subfolder(parent_id: str, name: str) -> tuple[str, str]:
    """指定フォルダ直下にサブフォルダを作成。 (folder_id, folder_url) を返す"""
    drive = _drive()
    meta = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
    f = drive.files().create(
        body=meta, fields="id, webViewLink", supportsAllDrives=True
    ).execute()
    return f["id"], f["webViewLink"]


def upload_image(folder_id: str, filename: str, data: bytes, mimetype: str) -> str:
    """画像を folder_id にアップロードし、閲覧URLを返す"""
    drive = _drive()
    media = MediaInMemoryUpload(data, mimetype=mimetype or "application/octet-stream")
    meta = {"name": filename, "parents": [folder_id]}
    f = drive.files().create(
        body=meta, media_body=media, fields="id, webViewLink", supportsAllDrives=True
    ).execute()
    # Driveはバックアップ保管（非公開）。Notion表示は別途 file_upload で直接アップロードする
    return f["webViewLink"]
