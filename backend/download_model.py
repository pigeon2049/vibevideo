import os
import sys

# 启用镜像加速
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
print(f"已启用镜像加速: {os.environ['HF_ENDPOINT']}")

from faster_whisper import download_model

# 默认下载 large-v3，除非通过命令行指定
model_size = sys.argv[1] if len(sys.argv) > 1 else "large-v3"
output_dir = "models"
full_output_path = os.path.join(os.getcwd(), output_dir, model_size)

print(f"\n正在准备下载 {model_size} 模型...")
print(f"目标路径: {full_output_path}")
print("下载过程可能需要几分钟，请留意下方的进度条...")

try:
    # download_model returns the path to the model directory
    # huggingface_hub (which is used internally) should show a progress bar by default
    model_path = download_model(model_size, output_dir=full_output_path)
    
    print(f"\n✅ 模型下载成功！")
    print(f"模型保存路径: {model_path}")
    print(f"\n请修改你的代码以使用该路径加载模型，例如：")
    print(f"model = WhisperModel(r'{model_path}', ...)")
    
except Exception as e:
    print(f"\n❌ 下载失败: {e}")
    print("请检查网络连接。当前已尝试使用 hf-mirror.com 镜像。")
