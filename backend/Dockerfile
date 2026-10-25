FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/app/models/huggingface
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-fra tesseract-ocr-ara \
    espeak-ng ffmpeg libgl1 libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY requirements.txt .
RUN uv pip install --system --no-cache torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && uv pip install --system --no-cache -r requirements.txt
COPY . .
RUN mkdir -p models data && useradd --uid 10001 --create-home backend && chown -R backend:backend /app
USER backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--ws-max-size", "15728640"]
