from fastapi import FastAPI, Request
from pydantic import BaseModel
import uvicorn
import os
import tempfile
from faster_whisper import WhisperModel
from gtts import gTTS
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

import torch
from bark import SAMPLE_RATE, generate_audio, preload_models
from bark.generation import load_codec_model, codec_decode
from bark.api import semantic_to_waveform
from bark import generate_text_semantic
from bark.voice import clone_voice, load_voice
import numpy as np
import scipy.io.wavfile as wavfile

from datetime import datetime

app = FastAPI()

# Load your voice
VOICE_SAMPLE_PATH = "3voice.wav"
CLONED_SPEAKER = clone_voice(VOICE_SAMPLE_PATH)

# Auth Google Drive
gauth = GoogleAuth()
gauth.LoadCredentialsFile("service-account.json")
if gauth.credentials is None:
    gauth.LocalWebserverAuth()
else:
    gauth.Authorize()
drive = GoogleDrive(gauth)

class RequestBody(BaseModel):
    text: str

@app.post("/speak")
async def speak(req: RequestBody):
    text = req.text
    print("Received text:", text)

    semantic_tokens = generate_text_semantic(text, history_prompt=CLONED_SPEAKER)
    audio_array = semantic_to_waveform(semantic_tokens, history_prompt=CLONED_SPEAKER)

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
        "drive_link": f"https://drive.google.com/uc?id={file_drive['id']}&export=download"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
