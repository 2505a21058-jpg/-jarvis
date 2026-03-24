import asyncio
import edge_tts

async def test():
    voices = [
        ('en-US-GuyNeural', 'Guy'),
        ('en-US-ChristopherNeural', 'Christopher'),
        ('en-GB-RyanNeural', 'Ryan British'),
        ('en-GB-ThomasNeural', 'Thomas British'),
    ]
    
    for voice_id, name in voices:
        print(f"Testing {name}...")
        c = edge_tts.Communicate(
            f'Hello Sir, I am JARVIS. {name} voice online and ready.',
            voice_id
        )
        await c.save(f'{name}.mp3')
        print(f"Saved {name}.mp3")

asyncio.run(test())
print("Done! Check the mp3 files!")