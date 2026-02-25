# 🎥 VibeVideo

一款功能强大、现代化的视频翻译与配音工具。它可以自动从 YouTube 下载视频，提取音频，由 AI 驱动进行翻译，并生成高质量的中文配音与字幕。

---

## ✨ 核心特性

- 📥 **智能下载**：支持 YouTube 等视频平台的自动下载（基于 yt-dlp）。
- 🗣️ **精准转录**：使用 Whisper 模型（ggml-large-v3）进行高精度的语音转文字。
- 🤖 **AI 驱动翻译**：集成 LLM（如 translategemma）提供自然、地道的翻译效果。
- 🎙️ **高质量配音**：支持多种语音风格（TTS），默认使用 `zh-CN-YunxiNeural`。
- ⚡ **多模型策略**：支持多端 LLM 提供商配置，具备优先级切换、轮询负载均衡等策略。
- 🖥️ **现代化 UI**：简洁易用的前端界面，实时监控任务进度。

---

## 🚀 快速开始

### 1. 克隆项目
```bash
git clone https://github.com/pigeon2049/vibevideo.git
cd vibevideo
```

### 2. 环境准备
确保您的系统中已安装以下环境：
- **Node.js**: v22.16.0+
- **Python**: 3.11.8+

### 3. 安装外部工具 (Windows)
请将以下工具下载并将解压后的exe文件放置在 `backend\bin` 目录下：
- **yt-dlp**: [下载链接](https://github.com/yt-dlp/yt-dlp/releases/download/2026.02.04/yt-dlp.exe)
- **FFmpeg**: [下载链接](https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.0.1-full_build.7z) 
- **Deno**: [下载链接](https://github.com/denoland/deno/releases/download/v2.6.9/deno-x86_64-pc-windows-msvc.zip)

### 4. 下载模型
将以下模型文件放入 `models/` 目录下：
- `ggml-large-v3.bin`
- `ggml-silero-v5.1.2.bin`

---

## ⚙️ 配置说明

### 编辑 `backend/.env`
在 `backend` 目录下创建或编辑 `.env` 文件，配置您的 AI 服务：

```env
DEFAULT_VOICE_ZH=zh-CN-YunxiNeural

# ======== LLM API 配置 ========
# 策略支持: priority (优先级/失败切换), round_robin (轮流负载均衡), concurrent (多线程并发)
LLM_STRATEGY=priority

# 提供商 0 (默认: Ollama)
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://localhost:11434/v1
LLM_MODEL=translategemma:12b

# 提供商 1 (可选: 其他 OpenAI 兼容接口)
OPENAI_API_KEY1=sk-xxxxxx
OPENAI_BASE_URL1=https://openrouter.ai/api/v1
LLM_MODEL1=openai/gpt-oss-120b:free
```

### YouTube Cookie
为了提高视频下载成功率，推荐安装 [Get cookies.txt locally](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) 插件，并将导出的 cookie 粘贴至对应配置项。

---

## 🛠️ 运行应用

### 自动化运行
双击项目根目录下的脚本：
1. **安装依赖**：运行 `install_deps.bat`
2. **启动应用**：运行 `start_app.bat`

### 访问界面
启动成功后，打开浏览器访问：
[http://localhost:5173/](http://localhost:5173/)

---

## 📝 注意事项
- 目前版本在字幕翻译完成后，建议**刷新页面**以显示“生成视频”按钮。
- 本项目目前主要针对 Windows 环境进行开发与测试。

---

## 🤝 贡献与反馈
欢迎提交 Issue 或 Pull Request 来完善 VibeVideo！

