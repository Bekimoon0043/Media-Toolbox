# Media Toolbox + Whisper AI

Web UI and API for media processing with **ffmpeg** and **OpenAI Whisper** transcription (timestamps, multilingual).

## Features

| Tool | Endpoint | Description |
|------|----------|-------------|
| Extract audio | `POST /separate` | Video → MP3 |
| Transcribe | `POST /transcribe` | Whisper segments + full text |
| Merge | `POST /merge` | Video + audio + volume |
| Media info | `POST /info` | ffprobe JSON |
| Convert | `POST /convert` | Format conversion (mp3/wav/aac/ogg/mp4) |
| Trim | `POST /trim` | Cut by start/end time |
| Speed | `POST /stretch` | Change audio tempo |
| Burn subs | `POST /burn_subtitles` | SRT burned into video |
| Dub | `POST /dub` | Replace audio with optional offset |
| Health | `GET /health` | Service + model status |

Upload limit: **100 MB**. Temp files are cleaned after each request.

---

## Deploy on Render (from GitHub)

### Option A — Blueprint (recommended)

1. Open [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint**.
2. Connect the repo `Bekimoon0043/Media-Toolbox`.
3. Render reads `render.yaml` and creates a Docker web service.
4. Click **Apply**.

### Option B — Manual Web Service

1. **New** → **Web Service** → connect this GitHub repo.
2. Settings:
   - **Runtime**: Docker
   - **Branch**: `main`
   - **Dockerfile path**: `./Dockerfile`
   - **Plan**: Free (or Starter for more RAM/timeout)
3. Optional env var: `WHISPER_MODEL=tiny` (keep tiny on free tier).

After deploy, open `https://<your-service>.onrender.com` and check `GET /health`.

---

## Local run (Docker)

```bash
docker build -t media-toolbox .
docker run -p 5000:5000 -e WHISPER_MODEL=tiny media-toolbox
```

Or without Docker (ffmpeg required):

```bash
pip install -r requirements.txt
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
python app.py
```

---

## Notes for Render free tier

- **512 MB RAM** — keep `WHISPER_MODEL=tiny`. Larger models will OOM.
- Free instances sleep after idle; first request can take ~30–60s.
- Long videos/transcriptions may hit platform timeouts; prefer short clips.

---

## API examples

```bash
curl https://YOUR.onrender.com/health
curl -X POST -F "audio=@sample.mp3" https://YOUR.onrender.com/transcribe
curl -X POST -F "video=@clip.mp4" -o audio.mp3 https://YOUR.onrender.com/separate
```

## License

MIT
