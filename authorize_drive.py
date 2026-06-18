"""初回の Drive OAuth 認証スクリプト。
実行するとブラウザが開いて同意 → token.json を作成する。
（アプリ起動中に同意フローが走るのを避けるため、先にこれで認証しておく）

使い方:
  ./venv/bin/python authorize_drive.py
"""
from dotenv import load_dotenv

load_dotenv()

from tools.drive_tools import get_credentials

if __name__ == "__main__":
    get_credentials()
    print("✅ 認証完了。token.json を作成/更新しました。以後アプリはこれを使います。")
