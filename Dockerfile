# Media Toolbox — production image for Render / Docker
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WHISPER_MODEL=tiny \
    PORT=5000

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) CPU-only PyTorch (must use pytorch.org index — do NOT list torch in requirements.txt)
RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
      torch==2.4.1 torchaudio==2.4.1 \
      --index-url https://download.pytorch.org/whl/cpu

# 2) App deps (whisper + flask, etc.) — no torch here so pip will not reinstall GPU wheels from PyPI
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download Whisper tiny model into the image
RUN python -c "import whisper; whisper.load_model('tiny')"

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 2 --timeout 300 --reuse-port app:app
