import speech_recognition as sr

r = sr.Recognizer()

print("Testing microphone index 1...")
with sr.Microphone(device_index=1) as source:
    print("Say something now...")
    r.adjust_for_ambient_noise(source, duration=1)
    audio = r.listen(source, timeout=10)
    print("Got audio! Processing...")
    try:
        text = r.recognize_google(audio)
        print(f"You said: {text}")
    except Exception as e:
        print(f"Error: {e}")