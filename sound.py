from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sounddevice as sd
print(sd.query_devices())
from dotenv import main
from pydantic import BaseModel
import wavio
import os
import aiohttp
import asyncio

# Initialize environment variables
main.load_dotenv()

# Initialize app and CORS policies
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RecordRequest(BaseModel):
    duration: float;
    user_id: str | None = None

# Load API key
GLADIA_KEY = os.environ['GLADIA_KEY']

# Prepare device
device_index = sd.default.device # Ensure default is used for input and output
device_info = sd.query_devices(device_index, 'input')  # Automatically queries the default input device
samplerate = int(device_info['default_samplerate']) # Extract the default sample rate from the device information
file_path = "./voice/output.wav" # Set the file path where the audio will be saved

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
                    response.raise_for_status()  
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
            response.raise_for_status()
            response_data = await response.json()
            
            result_url = response_data.get("result_url")
            if not result_url:
                raise ValueError("Result URL is missing in the transcription response.")
            
        print("Transcription in progress...", end="", flush=True)
        progress_dots = ""
        while True:
            async with session.get(result_url, headers=headers) as poll_response:
                poll_response.raise_for_status()
                poll_data = await poll_response.json()
                if poll_data.get("status") == "done":
                    print("\033[K\nTranscription complete!")
                    return poll_data.get("result", {}).get("transcription", {}).get("full_transcript")
                else:
                    progress_dots += "."
                    print(f"\rTranscription in progress...{progress_dots}", end="", flush=True)
                    await asyncio.sleep(1) 
                

async def post_transcription(transcription, user_id):
    url = 'http://127.0.0.1:8800/agent'
    data = {
        "user_input": transcription,
        "user_locale": "eng",
        "user_id": user_id,
        "platform": "web"
    }
    headers = {"Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            response.raise_for_status() 
            return await response.json()

@app.post("/start")
async def start_recording():
    global audio_data
    duration = 20  # Maximum duration
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
    user_id = record_request.user_id # fetch unique UserId
    print(f'User ID->{user_id}')
    
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
    result = await post_transcription(transcription, user_id)
    ans = result["output"]
    print(ans)
    
    # Delete the audio file
    os.remove(file_path)
    print(f"Deleted file {file_path}")
    
    return {"question": transcription, "reply": ans}

# start command -> uvicorn sound:app --reload --port 8880
