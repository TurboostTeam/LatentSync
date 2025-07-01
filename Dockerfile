# 使用NVIDIA CUDA基础镜像，支持GPU推理
FROM nvidia/cuda:12.2.2-cudnn8-runtime-ubuntu22.04

# 设置工作目录
WORKDIR /app

# 安装 Python 3.10 和 pip
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# OpenCV 依赖
RUN apt -y install libgl1

# 下载模型
RUN pip install -U huggingface_hub
RUN mkdir -p checkpoints
RUN huggingface-cli download --resume-download ByteDance/LatentSync-1.6 whisper/tiny.pt --local-dir checkpoints
RUN huggingface-cli download --resume-download ByteDance/LatentSync-1.6 latentsync_unet.pt --local-dir checkpoints

# 复制requirements文件
COPY requirements.txt .

# Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 启动命令
CMD ["python3", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"] 