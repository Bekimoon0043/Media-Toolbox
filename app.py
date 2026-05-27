# app.py
import os
import subprocess
import tempfile
import shutil
import json
import time
import wave
from flask import Flask, request, send_file, render_template, jsonify, g, after_this_request
import whisper

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB limit
app.config['WHISPER_MODEL'] = os.environ.get('WHISPER_MODEL', 'tiny')  # tiny, base, small, medium, large

# -------------------------------------------------------------------
# Load Whisper model once at startup
# -------------------------------------------------------------------
try:
    model = whisper.load_model(app.config['WHISPER_MODEL'])
except Exception as e:
    print(f"Failed to load Whisper model: {e}")
    model = None

# -------------------------------------------------------------------
# Temporary file cleanup: after each request, delete registered files
# -------------------------------------------------------------------
@app.before_request
def before_request():
    g.temp_files = []

def cleanup_temp_files():
    for path in getattr(g, 'temp_files', []):
        try:
            if os.path.exists(path):
                os.unlink(path)
        except Exception:
            pass

@app.after_request
def after_request(response):
    cleanup_temp_files()
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

# -------------------------------------------------------------------
# Helper: run ffmpeg with error handling
# -------------------------------------------------------------------
def run_ffmpeg(cmd, description='ffmpeg command'):
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return result
    except subprocess.CalledProcessError as e:
        raise Exception(f"{description} failed: {e.stderr}")

# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/separate', methods=['POST'])
def separate_audio():
    """Extract audio from uploaded video and return as MP3."""
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    video_file = request.files['video']
    if video_file.filename == '':
        return jsonify({'error': 'Empty file'}), 400

    input_path = create_temp_file('_input_video')
    video_file.save(input_path)

    output_path = create_temp_file('.mp3')

    cmd = ['ffmpeg', '-i', input_path, '-vn', '-acodec', 'libmp3lame', '-y', output_path]
    run_ffmpeg(cmd, 'Audio extraction')

    return send_file(output_path, as_attachment=True, download_name='audio.mp3')

@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    """Transcribe uploaded audio using Whisper (returns segments with timestamps)."""
    if not model:
        return jsonify({'error': 'Whisper model not loaded'}), 500
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400
    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({'error': 'Empty file'}), 400

    # Save uploaded audio to temporary file
    input_path = create_temp_file('_input_audio')
    audio_file.save(input_path)

    # Transcribe with Whisper (supports any format, uses ffmpeg internally)
    try:
        result = model.transcribe(input_path, word_timestamps=False)
    except Exception as e:
        return jsonify({'error': f'Whisper transcription failed: {str(e)}'}), 500

    # Return segments with timestamps and full text
    segments = []
    for seg in result['segments']:
        segments.append({
            'start': round(seg['start'], 3),
            'end': round(seg['end'], 3),
            'text': seg['text'].strip()
        })
    return jsonify({
        'text': result['text'].strip(),
        'segments': segments,
        'language': result.get('language', 'unknown')
    })

@app.route('/merge', methods=['POST'])
def merge_video_audio():
    """Merge uploaded video and audio, adjusting volume."""
    if 'video' not in request.files or 'audio' not in request.files:
        return jsonify({'error': 'Both video and audio files are required'}), 400
    video_file = request.files['video']
    audio_file = request.files['audio']
    if video_file.filename == '' or audio_file.filename == '':
        return jsonify({'error': 'Empty file(s)'}), 400

    volume = request.form.get('volume', '1.0')
    try:
        volume = float(volume)
    except ValueError:
        return jsonify({'error': 'Volume must be a number'}), 400

    video_path = create_temp_file('_video')
    video_file.save(video_path)
    audio_path = create_temp_file('_audio')
    audio_file.save(audio_path)

    output_path = create_temp_file('_merged.mp4')

    cmd = ['ffmpeg', '-i', video_path, '-i', audio_path,
           '-filter:a', f'volume={volume}',
           '-c:v', 'copy', '-c:a', 'aac',
           '-map', '0:v:0', '-map', '1:a:0',
           '-shortest', '-y', output_path]
    run_ffmpeg(cmd, 'Merge')

    return send_file(output_path, as_attachment=True, download_name='merged.mp4')

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'whisper_model': app.config['WHISPER_MODEL'],
        'whisper_loaded': model is not None
    })

@app.route('/info', methods=['POST'])
def media_info():
    """Get media information using ffprobe."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty file'}), 400

    input_path = create_temp_file('_info')
    file.save(input_path)

    # Use ffprobe to get JSON output
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json',
           '-show_format', '-show_streams', input_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
        # Add a synthetic filename field
        info['filename'] = file.filename
        return jsonify(info)
    except subprocess.CalledProcessError as e:
        return jsonify({'error': f'ffprobe failed: {e.stderr}'}), 500
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid ffprobe output'}), 500

@app.route('/convert', methods=['POST'])
def convert_media():
    """Convert media file to a different format."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty file'}), 400

    output_format = request.form.get('format', 'mp3').lower()
    audio_bitrate = request.form.get('audio_bitrate', '128k')
    video_codec = request.form.get('video_codec', 'libx264')

    input_path = create_temp_file('_convert_input')
    file.save(input_path)

    output_path = create_temp_file(f'.{output_format}')

    # Build ffmpeg command based on output format
    if output_format in ['mp3', 'aac', 'wav', 'ogg']:
        cmd = ['ffmpeg', '-i', input_path, '-vn',
               '-c:a', 'libmp3lame' if output_format == 'mp3' else 'aac' if output_format == 'aac' else 'pcm_s16le' if output_format == 'wav' else 'libvorbis',
               '-b:a', audio_bitrate, '-y', output_path]
    else:  # video formats: mp4, avi, mov, etc.
        cmd = ['ffmpeg', '-i', input_path,
               '-c:v', video_codec, '-c:a', 'aac',
               '-b:a', audio_bitrate, '-y', output_path]

    run_ffmpeg(cmd, 'Conversion')

    download_name = f'converted.{output_format}'
    return send_file(output_path, as_attachment=True, download_name=download_name)

@app.route('/trim', methods=['POST'])
def trim_media():
    """Trim audio/video by start and end times."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty file'}), 400

    start = request.form.get('start', '0')
    end = request.form.get('end', None)

    input_path = create_temp_file('_trim_input')
    file.save(input_path)

    output_path = create_temp_file('_trimmed')

    # Determine output extension from input
    ext = os.path.splitext(file.filename)[1] or '.mp4'
    output_path = output_path + ext

    cmd = ['ffmpeg', '-i', input_path, '-ss', start]
    if end:
        cmd += ['-to', end]
    cmd += ['-c', 'copy', '-avoid_negative_ts', 'make_zero', '-y', output_path]

    run_ffmpeg(cmd, 'Trimming')

    return send_file(output_path, as_attachment=True, download_name=f'trimmed{ext}')

@app.route('/stretch', methods=['POST'])
def stretch_audio():
    """Change playback speed of audio (tempo)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty file'}), 400

    speed = request.form.get('speed', '1.0')
    try:
        speed = float(speed)
        if speed <= 0:
            raise ValueError
    except ValueError:
        return jsonify({'error': 'Speed must be a positive number'}), 400

    input_path = create_temp_file('_stretch_input')
    file.save(input_path)

    output_path = create_temp_file('_stretched.mp3')

    # Use atempo filter (maximum 2.0 per filter, chain if needed)
    if speed == 1.0:
        tempo_filter = 'atempo=1.0'
    elif speed <= 2.0:
        tempo_filter = f'atempo={speed}'
    else:
        # Chain atempo filters: atempo=2.0, atempo={speed/2}
        tempo_filter = f'atempo=2.0,atempo={speed/2.0}'

    cmd = ['ffmpeg', '-i', input_path, '-filter:a', tempo_filter, '-y', output_path]
    run_ffmpeg(cmd, 'Stretching')

    return send_file(output_path, as_attachment=True, download_name='stretched.mp3')

@app.route('/burn_subtitles', methods=['POST'])
def burn_subtitles():
    """Burn subtitles (SRT file) into video."""
    if 'video' not in request.files or 'subtitles' not in request.files:
        return jsonify({'error': 'Both video and subtitles files are required'}), 400
    video_file = request.files['video']
    subs_file = request.files['subtitles']
    if video_file.filename == '' or subs_file.filename == '':
        return jsonify({'error': 'Empty file(s)'}), 400

    video_path = create_temp_file('_burn_video')
    video_file.save(video_path)
    subs_path = create_temp_file('_subs.srt')
    subs_file.save(subs_path)

    output_path = create_temp_file('_burned.mp4')

    cmd = ['ffmpeg', '-i', video_path, '-vf', f'subtitles={subs_path}', '-c:a', 'copy', '-y', output_path]
    run_ffmpeg(cmd, 'Burning subtitles')

    return send_file(output_path, as_attachment=True, download_name='subtitled_video.mp4')

@app.route('/dub', methods=['POST'])
def dub_video():
    """Replace video audio with new audio, with optional offset (sync fix)."""
    if 'video' not in request.files or 'audio' not in request.files:
        return jsonify({'error': 'Both video and audio files are required'}), 400
    video_file = request.files['video']
    audio_file = request.files['audio']
    if video_file.filename == '' or audio_file.filename == '':
        return jsonify({'error': 'Empty file(s)'}), 400

    offset = request.form.get('offset', '0')
    try:
        offset = float(offset)
    except ValueError:
        return jsonify({'error': 'Offset must be a number (seconds)'}), 400

    video_path = create_temp_file('_dub_video')
    video_file.save(video_path)
    audio_path = create_temp_file('_dub_audio')
    audio_file.save(audio_path)

    output_path = create_temp_file('_dubbed.mp4')

    # Apply delay to audio if offset != 0
    if offset == 0:
        audio_delay_filter = None
    else:
        # adelay produces silence padding, then asetpts to keep timestamps
        # Use: `adelay=delay_in_ms|all=1`
        delay_ms = int(offset * 1000)
        audio_delay_filter = f'adelay={delay_ms}|{delay_ms}'

    # Build command
    if audio_delay_filter:
        cmd = ['ffmpeg', '-i', video_path, '-i', audio_path,
               '-filter_complex', f'[1:a]{audio_delay_filter}[delayed]',
               '-map', '0:v:0', '-map', '[delayed]',
               '-c:v', 'copy', '-c:a', 'aac', '-shortest', '-y', output_path]
    else:
        cmd = ['ffmpeg', '-i', video_path, '-i', audio_path,
               '-map', '0:v:0', '-map', '1:a:0',
               '-c:v', 'copy', '-c:a', 'aac', '-shortest', '-y', output_path]

    run_ffmpeg(cmd, 'Dubbing')

    return send_file(output_path, as_attachment=True, download_name='dubbed_video.mp4')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)