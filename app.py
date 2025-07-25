from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import os
import tempfile
import base64
from datetime import datetime

import numpy as np
import scipy.io.wavfile as wavfile

from bark import SAMPLE_RATE, generate_text_semantic, semantic_to_waveform
from bark.voice import clone_voice

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

app = FastAPI()

# === STEP 1: Decode service account JSON from base64 ===
gdrive_b64 = os.getenv("GDRIVE_CRED_B64")
if not gdrive_b64:
    raise RuntimeError("Missing GDRIVE_CRED_B64 environment variable.")

cred_path = os.path.join(tempfile.gettempdir(), "service_account.json")
with open(cred_path, "wb") as f:
    f.write(base64.b64decode(gdrive_b64))

# === STEP 2: Google Drive Auth ===
gauth = GoogleAuth()
gauth.LoadCredentialsFile(cred_path)
if gauth.credentials is None:
    gauth.LoadClientConfigFile(cred_path)
    gauth.LocalWebserverAuth()
else:
    gauth.Authorize()

drive = GoogleDrive(gauth)

# === STEP 3: Voice Cloning Setup ===
VOICE_SAMPLE_PATH = "3voice.wav"
CLONED_SPEAKER = clone_voice(VOICE_SAMPLE_PATH)

# === Request schema ===
class RequestBody(BaseModel):
    text: str

# === Endpoint ===
@app.post("/speak")
async def speak(req: RequestBody):
    text = req.text
    print("Received text:", text)

    semantic_tokens = generate_text_semantic(text, history_prompt=CLONED_SPEAKER)
    audio_array = semantic_to_waveform(semantic_tokens, history_prompt=CLONED_SPEAKER)

    # Save to temp path
    tmp_audio_path = os.path.join(tempfile.gettempdir(), "final_speech.wav")
    wavfile.write(tmp_audio_path, SAMPLE_RATE, audio_array)

    # Upload to Google Drive
    upload_name = f"final_speech_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
    file_drive = drive.CreateFile({'title': upload_name})
    file_drive.SetContentFile(tmp_audio_path)
    file_drive.Upload()
    file_drive.InsertPermission({
        'type': 'anyone',
        'value': 'anyone',
        'role': 'reader'
    })

    return {
        "message": "Voice generated and uploaded successfully.",
        "drive_link": f"https://drive.google.com/uc?id={file_drive['id']}&export=download"
    }

# === Local Dev ===
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
