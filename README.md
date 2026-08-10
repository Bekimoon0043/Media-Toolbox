# Media Toolbox + Whisper AI (Render Free optimized)

Lightweight media processing API with **ffmpeg** + **OpenAI Whisper** transcription.

**Optimized for Render Free tier (512 MB)** and videos up to **3 minutes**.

This is the main thing **Rendi.dev does not give you**: speech-to-text with timestamps.

## Features (what Rendi does NOT have)

| Endpoint | Description |
|----------|-------------|
| `POST /transcribe` | **Whisper transcription** + timestamps + language detection |
| `POST /separate` | Extract audio from video → MP3 |
| `POST /info` | Media info (ffprobe) |
| `POST /convert` | Convert format (mp3/wav/aac/ogg/mp4) |
| `POST /trim` | Trim by start/end time |
| `GET /health` | Health check |

## Limits (Free tier)

- Maximum duration: **3 minutes (180 seconds)**
- Whisper model: **tiny** only
- Upload size: ~80 MB
- Memory: optimized for 512 MB

## Deploy on Render (Free)

1. Go to [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint**
2. Connect the repo `Bekimoon0043/Media-Toolbox`
3. Click **Apply**

Or manual:
- New → Web Service
- Runtime: **Docker**
- Plan: **Free**
- Env var: `WHISPER_MODEL=tiny`

## API examples

```bash
# Health
curl https://YOUR.onrender.com/health

# Transcribe (the main unique feature)
curl -X POST -F "audio=@clip.mp3" https://YOUR.onrender.com/transcribe

# Also accepts video directly
curl -X POST -F "video=@clip.mp4" https://YOUR.onrender.com/transcribe

# Extract audio
curl -X POST -F "video=@clip.mp4" -o audio.mp3 https://YOUR.onrender.com/separate
```

## Notes

- First request after sleep can take 30–60 seconds.
- Keep videos ≤ 3 minutes.
- Use `tiny` model only on free plan.

## License

MIT
