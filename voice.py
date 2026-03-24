import asyncio
import edge_tts
import speech_recognition as sr
import sounddevice as sd
import soundfile as sf
import io
import threading
from rich.console import Console
console=Console()
VOICE="en-US-ChristopherNeural"
recognizer=sr.Recognizer()
stop_speaking=threading.Event()
async def speak_async(text):
    communicate=edge_tts.Communicate(text,VOICE)
    audio_buffer=io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"]=="audio":audio_buffer.write(chunk["data"])
    audio_buffer.seek(0)
    data,samplerate=sf.read(audio_buffer)
    if not stop_speaking.is_set():
        sd.play(data,samplerate)
        sd.wait()
def _speak_worker(text):
    asyncio.run(speak_async(text))
def speak(text):
    stop_speaking.clear()
    t=threading.Thread(target=_speak_worker,args=(text,),daemon=True)
    t.start()
def stop():
    stop_speaking.set()
    sd.stop()
def listen():
    with sr.Microphone(device_index=1) as source:
        console.print("[dim]Listening...[/dim]")
        recognizer.adjust_for_ambient_noise(source,duration=0.5)
        try:
            audio=recognizer.listen(source,timeout=5,phrase_time_limit=10)
            text=recognizer.recognize_google(audio)
            return text
        except:return None
