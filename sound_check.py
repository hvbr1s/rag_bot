import sounddevice as sd
import wavio
import numpy as np

def record_audio_test(duration, samplerate, device):
    print("Recording...")
    audio_data = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=2, dtype='int16', device=device)
    sd.wait()
    print("Recording finished")
    return audio_data

def save_wav(file_path, data, samplerate):
    wavio.write(file_path, data, samplerate, sampwidth=2)
    print(f"Saved to {file_path}")

duration = 10  # seconds
device_index = 4  # Your C922 Pro Stream Webcam index
device_info = sd.query_devices(device_index, 'input')
samplerate = int(device_info['default_samplerate'])
file_path = "./voice/output.wav"

# Record audio
audio_data = record_audio_test(duration, samplerate, device_index)

# Check if audio data is not silent
if np.all(audio_data == 0):
    print("Recorded audio is silent, please check your microphone.")
else:
    print("Audio recorded successfully, saving to file.")
    save_wav(file_path, audio_data, samplerate)