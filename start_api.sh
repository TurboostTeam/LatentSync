#!/bin/bash

# 启动 Lip Sync API 服务

set -e

echo "启动 Lip Sync API ..."

# 加载 .env 文件
source .env

# 设置默认端口
API_PORT=${API_PORT}

# 设置 Python 路径
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# 启动API服务
echo "Port: $API_PORT"
echo "================================================"
python -m uvicorn api.main:app --host 0.0.0.0 --port $API_PORT
