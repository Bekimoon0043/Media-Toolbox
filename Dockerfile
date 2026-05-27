# Dockerfile
FROM python:3.9-slim

# Install ffmpeg, wget, and build dependencies for torch/whisper
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    wget \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download Whisper tiny model (cached in container)
RUN python -c "import whisper; whisper.load_model('tiny')"

# Copy application code
COPY . .

ENV WHISPER_MODEL=tiny
EXPOSE 5000

CMD ["python", "app.py"]