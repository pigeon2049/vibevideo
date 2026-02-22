import edge_tts
import os
from utils.file_manager import AUDIO_DIR, generate_temp_filename

# Voice constants
VOICE_EN_US = "en-US-AriaNeural"
VOICE_ZH_CN = "zh-CN-YunxiNeural"
# Add more as needed

async def generate_speech(text: str, voice: str, output_file: str = None) -> str:
    """
    Generates speech from text.
    Returns path to the generated audio file.
    """
    if not output_file:
        output_file = os.path.join(AUDIO_DIR, generate_temp_filename("mp3"))
        
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)
    
    return output_file

async def generate_speech_for_segments(segments: list, voice: str) -> list:
    """
    Generates speech for a list of segments.
    Adds "audio_file" key to each segment.
    """
    for segment in segments:
        text = segment["text"]
        if text.strip():
            audio_path = await generate_speech(text, voice)
            segment["audio_file"] = audio_path
        else:
            segment["audio_file"] = None
            
    return segments

if __name__ == "__main__":
    import asyncio
    
    async def test():
        path = await generate_speech("Hello, this is a test of Vibe Video.", VOICE_EN_US)
        print(f"Generated at: {path}")
        
    asyncio.run(test())
