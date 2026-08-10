# Media Toolbox — optimized for Render Free (512 MB)
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WHISPER_MODEL=tiny \
    PORT=5000

# Install only what we need
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install CPU torch first
RUN pip install --upgrade "pip<25" wheel && \
    pip install torch==2.4.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cpu && \
    pip install "setuptools<70" && \
    pip install --no-build-isolation openai-whisper==20240930

COPY requirements.txt .
RUN pip install -r requirements.txt

# Pre-cache tiny model
RUN python -c "import whisper; whisper.load_model('tiny'); print('whisper tiny cached')"

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

# Single worker, single thread, longer timeout for 3-min transcription
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 1 --timeout 180 --reuse-port app:app
