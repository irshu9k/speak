from flask import Flask, request, jsonify
import os
from werkzeug.utils import secure_filename
from pydub import AudioSegment
import uuid
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import subprocess
import base64

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

# ================================
# Google Drive Auth using base64
# ================================
encoded_creds = os.environ.get("GOOGLE_SERVICE_ACCOUNT_BASE64")

if not encoded_creds:
    raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_BASE64 environment variable")

decoded_json_path = "temp_service_account.json"
with open(decoded_json_path, "wb") as f:
    f.write(base64.b64decode(encoded_creds))

SCOPES = ['https://www.googleapis.com/auth/drive']
credentials = service_account.Credentials.from_service_account_file(
    decoded_json_path, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)

# Bark CLI command template
BARK_CMD = "python bark-clone/cli.py --text \"{text}\" --custom-voice {voice} --output {output}"

@app.route('/clone', methods=['POST'])
def clone_voice():
    if 'text' not in request.form:
        return jsonify({'error': 'Missing text'}), 400
    text = request.form['text']

    if 'audio' not in request.files:
        return jsonify({'error': 'Audio sample required'}), 400

    audio = request.files['audio']
    filename = secure_filename(audio.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    audio.save(filepath)

    # Convert to .wav if not already
    if not filepath.endswith('.wav'):
        sound = AudioSegment.from_file(filepath)
        filepath = filepath.rsplit('.', 1)[0] + '.wav'
        sound.export(filepath, format='wav')

    # Copy audio to Bark custom voice folder
    voice_id = str(uuid.uuid4())
    custom_voice_path = f"bark-clone/custom_voice/{voice_id}.wav"
    os.makedirs("bark-clone/custom_voice", exist_ok=True)
    os.rename(filepath, custom_voice_path)

    output_path = f"{OUTPUT_FOLDER}/{voice_id}_output.wav"
    cmd = BARK_CMD.format(text=text, voice=voice_id, output=output_path)

    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        return jsonify({"error": "Voice cloning failed"}), 500

    # Convert to mp3
    mp3_path = output_path.replace(".wav", ".mp3")
    AudioSegment.from_wav(output_path).export(mp3_path, format="mp3")

    # Upload to Google Drive
    file_metadata = {'name': 'final_speech.mp3', 'mimeType': 'audio/mpeg'}
    media = MediaFileUpload(mp3_path, mimetype='audio/mpeg')
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()

    file_id = file.get('id')
    drive_service.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'reader'}).execute()
    url = f"https://drive.google.com/uc?id={file_id}&export=download"

    return jsonify({'success': True, 'url': url})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
