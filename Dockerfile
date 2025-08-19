# 使用NVIDIA CUDA基础镜像，支持GPU推理
FROM nvidia/cuda:12.2.2-cudnn8-runtime-ubuntu22.04

# 设置工作目录
WORKDIR /app

# 安装系统依赖：Python、Node.js和其他必要工具
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
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Node.js 18 (LTS)
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs

# 下载 LatentSync-1.6 模型
RUN pip install -U huggingface_hub
RUN mkdir -p checkpoints
RUN huggingface-cli download --resume-download ByteDance/LatentSync-1.6 whisper/tiny.pt --local-dir checkpoints
RUN huggingface-cli download --resume-download ByteDance/LatentSync-1.6 latentsync_unet.pt --local-dir checkpoints

# 下载并解压 buffalo_l 模型，用于人脸检测和面部对齐
RUN mkdir -p checkpoints/auxiliary/models/buffalo_l
RUN wget https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip -O checkpoints/auxiliary/models/buffalo_l.zip
RUN cd checkpoints/auxiliary/models && unzip buffalo_l.zip -d buffalo_l && rm buffalo_l.zip

# 下载 sd-vae-ft-mse 模型
RUN export HF_HOME=checkpoints
RUN huggingface-cli download --resume-download stabilityai/sd-vae-ft-mse diffusion_pytorch_model.safetensors
RUN huggingface-cli download --resume-download stabilityai/sd-vae-ft-mse config.json


# 复制并安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制TypeScript项目的package.json和lock文件
COPY bullmq_worker/package*.json ./bullmq_worker/
WORKDIR /app/bullmq_worker

# 安装Node.js依赖
RUN npm ci --only=production


# 切换回主工作目录，并复制剩余的项目文件
WORKDIR /app
COPY . .

# 切换到worker目录
WORKDIR /app/bullmq_worker

# 构建TypeScript项目
RUN npm run build

# 启动命令 - 启动TypeScript版本的BullMQ worker服务
CMD ["node", "dist/index.js"] 