# 使用NVIDIA CUDA基础镜像，支持GPU推理
FROM nvidia/cuda:12.2.2-cudnn8-runtime-ubuntu22.04

# 设置工作目录
WORKDIR /app

# 安装 Python 3.10 和 pip
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    ffmpeg \
    libgl1 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libglib2.0-0 \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# 下载 LatentSync-1.6 模型
RUN pip install -U huggingface_hub
RUN mkdir -p checkpoints
RUN huggingface-cli download --resume-download ByteDance/LatentSync-1.6 whisper/tiny.pt --local-dir checkpoints
RUN huggingface-cli download --resume-download ByteDance/LatentSync-1.6 latentsync_unet.pt --local-dir checkpoints

# 下载并解压 buffalo_l 模型，用于人脸检测和面部对齐
RUN mkdir -p checkpoints/auxiliary/models
RUN wget https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip -O checkpoints/auxiliary/models/buffalo_l.zip
RUN cd checkpoints/auxiliary/models && unzip buffalo_l.zip && rm buffalo_l.zip

# 复制并安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 启动命令
CMD ["python3", "-u", "api/main.py"] 