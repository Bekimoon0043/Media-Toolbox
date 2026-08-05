# Media Toolbox — production image for Render / Docker
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WHISPER_MODEL=tiny \
    PORT=5000

# Install ffmpeg + compilers
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. Upgrade pip and install build tools
RUN pip install --upgrade "pip<25" wheel

# 2. Install CPU-only PyTorch first (saves massive space and RAM)
# Note: torch will install a newer setuptools, which we'll fix next.
RUN pip install \
      torch==2.4.1 torchaudio==2.4.1 \
      --index-url https://download.pytorch.org/whl/cpu

# 3. Fix setuptools for openai-whisper build
# openai-whisper 20240930 needs pkg_resources, which is missing in setuptools >= 70.
RUN pip install "setuptools<70"

# 4. Install openai-whisper with build isolation disabled
# This ensures it uses the 'setuptools<70' we just installed.
RUN pip install --no-build-isolation openai-whisper==20240930

# 5. Install other app requirements
COPY requirements.txt .
RUN pip install -r requirements.txt

# 6. Pre-cache Whisper tiny weights into the image (saves startup time/RAM)
RUN python -c "import whisper; whisper.load_model('tiny'); print('whisper tiny cached')"

COPY . .

# Run as non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

# Use 1 worker and 2 threads to stay within Render Free Tier RAM (512MB)
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 2 --timeout 300 --reuse-port app:app
