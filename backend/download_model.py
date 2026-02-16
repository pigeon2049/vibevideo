import os

# 之前尝试开启镜像，根据您的要求已禁用
# os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
# print(f"已启用镜像加速: {os.environ['HF_ENDPOINT']}")
print("已禁用镜像加速，使用默认源下载...")

from faster_whisper import download_model

model_size = "small"
# 将模型保存在当前目录下的 models/small 文件夹中
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
    print("请检查网络连接。如果镜像无法访问，请尝试修改脚本注释掉 HF_ENDPOINT 设置。")
