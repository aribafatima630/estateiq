FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    HF_HOME=/opt/hf \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SCRAPER_ENABLED=false

COPY backend/requirements-deploy.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "from huggingface_hub import hf_hub_download; hf_hub_download('sentence-transformers/all-MiniLM-L6-v2', 'model.safetensors'); hf_hub_download('sentence-transformers/all-MiniLM-L6-v2', 'tokenizer.json')"

COPY backend/app ./app
COPY data/processed/estateiq.db /data/processed/estateiq.db
COPY data/indexes/estateiq.npy /data/indexes/estateiq.npy
COPY data/indexes/meta.json /data/indexes/meta.json
COPY --from=web /web/dist ./static

EXPOSE 8000
CMD ["python", "-m", "app.cli", "serve"]
