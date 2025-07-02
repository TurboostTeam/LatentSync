#!/bin/bash

# 启动 Lip Sync API 服务

set -e

echo "启动 Lip Sync API ..."

# 设置 Python 路径
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# 启动API服务
echo "PYTHONPATH: $PYTHONPATH"
echo "================================================"
python3 -u api/main.py --fastapi
