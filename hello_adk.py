"""ADK Hello World（Vertex AI経由・ADC認証）

ADKフレームワークでエージェントを定義し、Geminiを呼べることを確認する。
Phase 0 の最終ステップ＝「ADK + Gemini」の足場。
"""
import os
import asyncio

# Vertex AI 経由で Gemini を使う設定（ADCで認証）
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = "fieldnotekeeper"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

# --- エージェント定義（3要素：モデル・指示・(ツールは無し)）---
root_agent = LlmAgent(
    name="hello_agent",
    model="gemini-2.5-flash",
    instruction="あなたは親切なアシスタントです。日本語で簡潔に答えてください。",
)

APP = "fieldnotekeeper-hello"
USER = "local-user"


async def main():
    runner = InMemoryRunner(agent=root_agent, app_name=APP)
    session = await runner.session_service.create_session(app_name=APP, user_id=USER)

    msg = types.Content(
        role="user",
        parts=[types.Part(text="あなたはADK経由で呼ばれたエージェントです。一言で日本語で挨拶してください。")],
    )

    async for event in runner.run_async(
        user_id=USER, session_id=session.id, new_message=msg
    ):
        if event.is_final_response():
            print("=== ADKエージェントの返答 ===")
            print(event.content.parts[0].text)


if __name__ == "__main__":
    asyncio.run(main())
