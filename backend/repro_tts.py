import asyncio
import edge_tts
import os

import re

def is_speakable(text):
    # Check if there's at least one alphanumeric character
    return bool(re.search(r'[\w\u4e00-\u9fff]', text))

async def test_tts(text, voice):
    print(f"Testing text: '{text}' with voice: '{voice}'")
    if not is_speakable(text):
        print(f"Result for '{text[:10]}...': Skipped (not speakable)")
        return

    filename = f"test_{hashlib.md5(text.encode()).hexdigest()[:8]}.mp3"
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(filename)
        print(f"Result for '{text[:10]}...': Success!")
    except Exception as e:
        print(f"Result for '{text[:10]}...': Failed with {type(e).__name__}: {e}")
    finally:
        await asyncio.sleep(0.5)
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except:
                pass


async def main():
    # Test normal text
    await test_tts("Hello world", "en-US-AriaNeural")
    # Test just a period
    await test_tts(".", "en-US-AriaNeural")
    # Test just a comma
    await test_tts(",", "en-US-AriaNeural")
    # Test empty string with space
    await test_tts("   ", "en-US-AriaNeural")
    # Test Chinese default
    await test_tts("你好", "zh-CN-YunxiNeural")
    # Test period in Chinese default
    await test_tts("。", "zh-CN-YunxiNeural")
    # Test empty translation (often seen in logs)
    await test_tts("", "zh-CN-YunxiNeural")

if __name__ == "__main__":
    import hashlib
    asyncio.run(main())

