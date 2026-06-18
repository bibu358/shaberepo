FROM python:3.12-slim

WORKDIR /app

# 依存を先に入れてレイヤーキャッシュを効かせる
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリ本体
COPY . .

# Vertex AI 経由でGeminiを使う（PROJECT/LOCATIONはapp.py側でも設定）
ENV GOOGLE_GENAI_USE_VERTEXAI=TRUE
ENV GOOGLE_CLOUD_LOCATION=global

# Cloud Run は $PORT を渡してくる
CMD streamlit run app.py \
    --server.port=${PORT:-8080} \
    --server.address=0.0.0.0 \
    --server.headless=true
