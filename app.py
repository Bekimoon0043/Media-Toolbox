# app.py - Optimized for Render Free (512 MB) + max 3-minute media
import os
import subprocess
import tempfile
import json
from flask import Flask, request, send_file, render_template, jsonify, g
import whisper

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 80 * 1024 * 1024  # 80 MB limit (safer for free tier)
app.config['WHISPER_MODEL'] = os.environ.get('WHISPER_MODEL', 'tiny')
app.config['MAX_DURATION_SECONDS'] = 180  # 3 minutes hard limit

# Load Whisper model once at startup (tiny only for free tier)
try:
    model = whisper.load_model(app.config['WHISPER_MODEL'])
    print(f"Whisper model '{app.config['WHISPER_MODEL']}' loaded")
except Exception as e:
    print(f"Failed to load Whisper model: {e}")
    model = None


@app.before_request
def before_request():
    g.temp_files = []


@app.after_request
def after_request(response):
    files = list(getattr(g, 'temp_files', []))
    def _cleanup():
        for path in files:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except Exception:
                pass
    response.call_on_close(_cleanup)
    return response


def register_temp_file(path):
    if hasattr(g, 'temp_files'):
        g.temp_files.append(path)
    return path


def create_temp_file(suffix=''):
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    register_temp_file(path)
    return path


def run_ffmpeg(cmd, description='ffmpeg command'):
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        return result
    except subprocess.TimeoutExpired:
        raise Exception(f"{description} timed out")
    except subprocess.CalledProcessError as e:
        raise Exception(f"{description} failed: {e.stderr[:500] if e.stderr else str(e)}")


def get_duration(path):
    """Return duration in seconds using ffprobe, or None on failure."""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        info = json.loads(result.stdout)
        return float(info.get('format', {}).get('duration', 0))
    except Exception:
        return None


def extract_audio_to_wav(input_path):
    """Extract mono 16kHz wav (smallest + best for Whisper)."""
    output_path = create_temp_file('.wav')
    cmd = [
        'ffmpeg', '-i', input_path,
        '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
        '-y', output_path
    ]
    run_ffmpeg(cmd, 'Audio extraction for Whisper')
    return output_path


# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html', whisper_model=app.config['WHISPER_MODEL'])


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'whisper_model': app.config['WHISPER_MODEL'],
        'whisper_loaded': model is not None,
        'max_duration_seconds': app.config['MAX_DURATION_SECONDS'],
        'note': 'Optimized for Render Free + max 3 min videos'
    })


@app.route('/separate', methods=['POST'])
def separate_audio():
    """Extract audio from video → MP3."""
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    video_file = request.files['video']
    if not video_file.filename:
        return jsonify({'error': 'Empty file'}), 400

    input_path = create_temp_file('_input_video')
    video_file.save(input_path)

    duration = get_duration(input_path)
    if duration and duration > app.config['MAX_DURATION_SECONDS']:
        return jsonify({
            'error': f'Video too long ({duration:.1f}s). Maximum allowed is {app.config["MAX_DURATION_SECONDS"]} seconds (3 minutes).'
        }), 400

    output_path = create_temp_file('.mp3')
    cmd = ['ffmpeg', '-i', input_path, '-vn', '-acodec', 'libmp3lame', '-b:a', '128k', '-y', output_path]
    try:
        run_ffmpeg(cmd, 'Audio extraction')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return send_file(output_path, as_attachment=True, download_name='audio.mp3')


@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    """
    Transcribe audio/video with Whisper (tiny).
    This is the main feature Rendi does NOT have.
    Accepts field name 'audio' or 'file' or 'video'.
    """
    if not model:
        return jsonify({'error': 'Whisper model not loaded'}), 500

    # Accept multiple possible field names
    media_file = None
    for key in ('audio', 'file', 'video'):
        if key in request.files and request.files[key].filename:
            media_file = request.files[key]
            break

    if media_file is None:
        return jsonify({'error': 'No audio/video file provided. Use field name: audio, file, or video'}), 400

    input_path = create_temp_file('_input_media')
    media_file.save(input_path)

    # Duration check
    duration = get_duration(input_path)
    if duration and duration > app.config['MAX_DURATION_SECONDS']:
        return jsonify({
            'error': f'Media too long ({duration:.1f}s). Maximum allowed is {app.config["MAX_DURATION_SECONDS"]} seconds (3 minutes) on free tier.'
        }), 400

    # Always extract to small mono 16kHz wav first (saves a lot of RAM)
    try:
        audio_path = extract_audio_to_wav(input_path)
    except Exception as e:
        return jsonify({'error': f'Failed to extract audio: {str(e)}'}), 500

    # Transcribe
    try:
        result = model.transcribe(audio_path, word_timestamps=False, fp16=False)
    except Exception as e:
        return jsonify({'error': f'Whisper transcription failed: {str(e)}'}), 500

    segments = []
    for seg in result.get('segments', []):
        segments.append({
            'start': round(seg['start'], 3),
            'end': round(seg['end'], 3),
            'text': seg['text'].strip()
        })

    return jsonify({
        'text': result.get('text', '').strip(),
        'segments': segments,
        'language': result.get('language', 'unknown'),
        'duration_seconds': round(duration, 2) if duration else None
    })


@app.route('/info', methods=['POST'])
def media_info():
    """Get media information using ffprobe."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'Empty file'}), 400

    input_path = create_temp_file('_info')
    file.save(input_path)

    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', input_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        info = json.loads(result.stdout)
        info['filename'] = file.filename
        return jsonify(info)
    except Exception as e:
        return jsonify({'error': f'ffprobe failed: {str(e)}'}), 500


@app.route('/convert', methods=['POST'])
def convert_media():
    """Convert to another format (light version)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'Empty file'}), 400

    output_format = request.form.get('format', 'mp3').lower()
    if output_format not in ('mp3', 'wav', 'aac', 'ogg', 'mp4'):
        return jsonify({'error': 'Supported formats: mp3, wav, aac, ogg, mp4'}), 400

    input_path = create_temp_file('_convert_input')
    file.save(input_path)

    duration = get_duration(input_path)
    if duration and duration > app.config['MAX_DURATION_SECONDS']:
        return jsonify({'error': f'File too long. Max {app.config["MAX_DURATION_SECONDS"]} seconds.'}), 400

    output_path = create_temp_file(f'.{output_format}')

    if output_format in ('mp3', 'aac', 'wav', 'ogg'):
        codec = {'mp3': 'libmp3lame', 'aac': 'aac', 'wav': 'pcm_s16le', 'ogg': 'libvorbis'}[output_format]
        cmd = ['ffmpeg', '-i', input_path, '-vn', '-c:a', codec, '-b:a', '128k', '-y', output_path]
    else:
        cmd = ['ffmpeg', '-i', input_path, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '28', '-c:a', 'aac', '-b:a', '128k', '-y', output_path]

    try:
        run_ffmpeg(cmd, 'Conversion')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return send_file(output_path, as_attachment=True, download_name=f'converted.{output_format}')


@app.route('/trim', methods=['POST'])
def trim_media():
    """Trim by start/end time (stream copy when possible)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'Empty file'}), 400

    start = request.form.get('start', '0')
    end = request.form.get('end', None)

    input_path = create_temp_file('_trim_input')
    file.save(input_path)

    ext = os.path.splitext(file.filename)[1] or '.mp4'
    output_path = create_temp_file(ext)

    cmd = ['ffmpeg', '-i', input_path, '-ss', str(start)]
    if end:
        cmd += ['-to', str(end)]
    cmd += ['-c', 'copy', '-avoid_negative_ts', 'make_zero', '-y', output_path]

    try:
        run_ffmpeg(cmd, 'Trimming')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return send_file(output_path, as_attachment=True, download_name=f'trimmed{ext}')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
