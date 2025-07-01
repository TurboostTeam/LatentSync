"""
统一服务启动器 - 主入口程序
支持 RunPod Serverless 和 FastAPI 服务器两种部署模式
"""
import os
import logging
import uvicorn
from dotenv import load_dotenv, find_dotenv

from api.server import app
from api.runpod_handler import start_runpod_handler

load_dotenv(find_dotenv())

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_deployment_mode():
    """
    检测部署模式
    
    Returns:
        str: 'runpod' 或 'fastapi'
    """
    
    # 自动检测：
    # 如果有 RUNPOD_POD_ID 或 RUNPOD_ENDPOINT_ID 环境变量，说明在 RunPod 环境中
    if os.getenv('RUNPOD_POD_ID') or os.environ.get('RUNPOD_ENDPOINT_ID'):
        return 'runpod'
    
    # 默认使用 FastAPI 模式
    return 'fastapi'

def start_fastapi_server():
    """启动 FastAPI 服务器"""
    logger.info("启动 FastAPI 服务器模式")

    port = int(os.getenv('PORT', '8000'))
    logger.info(f"FastAPI 服务器启动在 {port}")
    uvicorn.run(app, host='0.0.0.0', port=port)

def start_runpod_serverless():
    """启动 RunPod Serverless 模式"""
    logger.info("启动 RunPod Serverless 模式")

    start_runpod_handler()

def main():
    """主入口函数"""
    logger.info("=== 唇形同步服务启动器 ===")
    
    # 检测并启动对应服务
    mode = get_deployment_mode()
    logger.info(f"部署模式: {mode}")
    
    if mode == 'runpod':
        start_runpod_serverless()
    else:  # fastapi
        start_fastapi_server()

if __name__ == "__main__":
    main() 