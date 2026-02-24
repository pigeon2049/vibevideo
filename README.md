##自动下载youtube视频并生成翻译和中文语音
---
```
git clone https://github.com/pigeon2049/vibevideo.git
cd vibevideo
```

下载并解压exe到backend\bin
---
https://github.com/yt-dlp/yt-dlp/releases/download/2026.02.04/yt-dlp.exe

https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.0.1-full_build.7z

https://github.com/denoland/deno/releases/download/v2.6.9/deno-x86_64-pc-windows-msvc.zip

---


下载并放到models/
----
ggml-large-v3.bin

ggml-silero-v5.1.2.bin


youtube下载需要粘贴cookie
----
https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc


LLM
---
```
ollama pull translategemma:12b
```

新建.env
---
```
DEFAULT_VOICE_ZH=zh-CN-YunxiNeural
# ======== LLM API 配置 ========
# 策略支持: priority (优先级/失败切换), round_robin (轮流负载均衡), concurrent (多线程并发)
LLM_STRATEGY=priority

# 提供商 0 (默认项)
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://localhost:11434/v1
LLM_MODEL=translategemma:12b

# 提供商 1
OPENAI_API_KEY1=sk-
OPENAI_BASE_URL1=https://openrouter.ai/api/v1
LLM_MODEL1=openai/gpt-oss-120b:free

# 提供商 2
#OPENAI_API_KEY2=
#OPENAI_BASE_URL2=https://ollama.com/v1
#LLM_MODEL2=qwen3.5:397b

# 提供商 3
#OPENAI_API_KEY3=
#OPENAI_BASE_URL3=
#LLM_MODEL3=

# 提供商 4
#OPENAI_API_KEY4=
#OPENAI_BASE_URL4=
#LLM_MODEL4=

```

Python 3.11.8  其它版本未测试

运行: start_app.bat
