"""画像を Google Drive に保管する（OAuth ユーザー認証）。

個人Gmailではサービスアカウントに保存容量が無くアップロードできない
（"Service Accounts do not have storage quota"）ため、
ユーザー本人のOAuth認証（本人の容量）を使う。
※組織のWorkspaceなら「共有ドライブ＋SA」の方が楽。

必要な環境変数：
- DRIVE_OAUTH_CLIENT      : OAuthクライアントの credentials JSON パス
- DRIVE_OAUTH_TOKEN       : 認証トークンの保存先（既定 token.json）
- DRIVE_PARENT_FOLDER_ID  : 画像を入れる親フォルダID

初回だけ `authorize_drive.py` を実行 → ブラウザ同意 → token.json 作成。
以降は token.json を使う（同意不要、期限切れは自動更新）。
"""
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME = "application/vnd.google-apps.folder"


def get_credentials() -> Credentials:
    """token.json があれば使い、無ければブラウザ同意で作成。期限切れは自動更新。"""
    token_path = os.environ.get("DRIVE_OAUTH_TOKEN", "token.json")
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                os.environ["DRIVE_OAUTH_CLIENT"], SCOPES
            )
            creds = flow.run_local_server(port=0)
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


def upload_image(folder_id: str, filename: str, data: bytes, mimetype: str) -> str:
    """画像を folder_id にアップロードし、閲覧URLを返す"""
    drive = _drive()
    media = MediaInMemoryUpload(data, mimetype=mimetype or "application/octet-stream")
    meta = {"name": filename, "parents": [folder_id]}
    f = drive.files().create(
        body=meta, media_body=media, fields="id, webViewLink", supportsAllDrives=True
    ).execute()
    return f["webViewLink"]
