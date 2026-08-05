# Media Toolbox — production image for Render / Docker
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WHISPER_MODEL=tiny \
    PORT=5000

# ffmpeg + compilers (needed if any package falls back to building from source)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only PyTorch first (do not put torch in requirements.txt)
RUN pip install --upgrade "pip<25" setuptools wheel && \
    pip install \
      torch==2.4.1 torchaudio==2.4.1 \
      --index-url https://download.pytorch.org/whl/cpu

# App packages — no torch here so pip won't fight the CPU install
COPY requirements.txt .
RUN pip install -r requirements.txt

# Cache Whisper tiny weights in the image
RUN python -c "import whisper; whisper.load_model('tiny'); print('whisper ok')"

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 2 --timeout 300 --reuse-port app:app
