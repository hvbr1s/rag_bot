from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import sounddevice as sd
print(sd.query_devices())
from dotenv import load_dotenv
from pydantic import BaseModel
import wavio
import numpy as np
import os
import aiohttp
import asyncio

# Initialize environment variables
load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this as needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RecordRequest(BaseModel):
    duration: float

GLADIA_KEY = os.environ['GLADIA_KEY']

device_index = 4  # Your C922 Pro Stream Webcam index
device_info = sd.query_devices(device_index, 'input')
samplerate = int(device_info['default_samplerate'])
file_path = "./voice/output.wav"

def record_audio(duration, samplerate, device):
    print("Recording...")
    audio_data = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=2, dtype='int16', device=device)
    sd.wait()
    print("Recording finished")
    return audio_data

def save_wav(file_path, data, samplerate):
    wavio.write(file_path, data, samplerate, sampwidth=2)
    print(f"Saved to {file_path}")

async def upload_audio(file_path):
    url = "https://api.gladia.io/v2/upload"
    headers = {
        'x-gladia-key': GLADIA_KEY,
    }
    file_full_path = os.path.abspath(file_path)
    print(f"Uploading audio file from path: {file_full_path}")
    
    try:
        async with aiohttp.ClientSession() as session:
            with open(file_full_path, 'rb') as audio_file:
                data = aiohttp.FormData()
                data.add_field('audio', audio_file, filename=os.path.basename(file_full_path))
                async with session.post(url, headers=headers, data=data) as response:
                    print(f"Response status code: {response.status}")
                    response_text = await response.text()
                    print(f"Response content: {response_text}")
                    response.raise_for_status()  # Ensure we notice bad responses
                    return await response.json()
    except FileNotFoundError:
        print(f"File not found: {file_full_path}")
        raise
    except Exception as e:
        print(f"An error occurred while uploading audio: {e}")
        raise

async def get_transcription(audio_url):
    headers = {
        "x-gladia-key": GLADIA_KEY,
        "Content-Type": "application/json"
    }
    data = {"audio_url": audio_url}
    
    async with aiohttp.ClientSession() as session:
        async with session.post("https://api.gladia.io/v2/transcription/", headers=headers, json=data) as response:
            response.raise_for_status()  # Ensure we notice bad responses
            response_data = await response.json()
            
            result_url = response_data.get("result_url")
            if not result_url:
                raise ValueError("Result URL is missing in the transcription response.")
        
        while True:
            async with session.get(result_url, headers=headers) as poll_response:
                poll_data = await poll_response.json()
                print(poll_data)
                if poll_data.get("status") == "done":
                    return poll_data.get("result", {}).get("transcription", {}).get("full_transcript")
                await asyncio.sleep(1)

async def post_transcription(transcription):
    url = 'http://127.0.0.1:8800/agent'
    data = {
        "user_input": transcription,
        "user_locale": "eng",
        "user_id": "8811",
        "platform": "slack"
    }
    headers = {"Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            response.raise_for_status()  # Ensure we notice bad responses
            return await response.json()

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", 'r') as f:
        return HTMLResponse(content=f.read())

@app.post("/start")
async def start_recording():
    global audio_data
    duration = 20  # Set a maximum duration
    audio_data = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=2, dtype='int16', device=device_index)
    print("Recording started")
    return {"status": "recording started"}

@app.post("/stop")
async def stop_recording(record_request: RecordRequest):
    global audio_data
    sd.stop()
    print("Recording stopped")
    duration = record_request.duration  # seconds
    print(f"Received duration: {duration} seconds")
    
    # Save audio data
    save_wav(file_path, audio_data, samplerate)
    
    # Upload audio and get transcription
    upload_response = await upload_audio(file_path)
    audio_url = upload_response.get("audio_url")
    print(audio_url)
    if not audio_url:
        raise ValueError("Audio URL is missing in the upload response.")
    
    transcription = await get_transcription(audio_url)
    print(transcription)
    
    # Post transcription to another API
    result = await post_transcription(transcription)
    print(f'Server answer ----->>>> {result}')
    ans = result["output"]
    print(ans)
    
    # Delete the audio file
    os.remove(file_path)
    print(f"Deleted file {file_path}")
    
    return {"question": transcription, "reply": ans}
