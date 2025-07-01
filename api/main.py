import logging
import os
import uuid
from datetime import datetime

from fastapi import BackgroundTasks, FastAPI, HTTPException

from api.config import config
from api.models import LipSyncRequest, LipSyncResponse, TaskStatus
from api.queue_processor import get_queue_processor
from api.storage import get_storage_manager
from api.task_manager import get_task_manager

# 配置日志
logging.basicConfig(level=getattr(logging, "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(title="Lip Sync API", description="唇形同步API服务")

# 全局管理器实例
task_manager = None
queue_processor = None
storage_manager = None


@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化"""
    global task_manager, queue_processor, storage_manager

    logger.info("启动 Lip Sync API...")

    # 验证配置
    try:
        config.validate()
    except FileNotFoundError as e:
        logger.error(f"配置验证失败: {e}")
        raise

    # 初始化管理器（不包括模型初始化）
    try:
        task_manager = get_task_manager()
        storage_manager = get_storage_manager()
        queue_processor = get_queue_processor()

        # 启动队列处理器
        await queue_processor.start_processing()

        logger.info("所有管理器初始化完成（不包括模型初始化）")
    except Exception as e:
        logger.error(f"管理器初始化失败: {e}")
        raise

    logger.info("API 启动完成")


@app.get("/")
async def root():
    """根路径"""
    return {"message": "Lip Sync API 正在运行", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    """健康检查"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(),
        "storage": "redis",
    }

    if task_manager:
        redis_healthy = task_manager.health_check()
        health_status["redis"] = "healthy" if redis_healthy else "unhealthy"
        if not redis_healthy:
            health_status["status"] = "unhealthy"
    else:
        health_status["redis"] = "disconnected"
        health_status["status"] = "unhealthy"

    # 添加队列状态
    if queue_processor:
        queue_status = queue_processor.get_queue_status()
        health_status["queue"] = queue_status

    return health_status


@app.post("/lipsync", response_model=LipSyncResponse)
async def create_lip_sync_task(request: LipSyncRequest):
    """
    创建唇形同步任务

    - 请求体参数:
        - video_url: 输入视频的对象存储地址
        - audio_url: 输入音频的对象存储地址

    - 返回值:
        - task_id: 任务ID
        - status: 任务状态
        - message: 任务消息
    """
    task_id = str(uuid.uuid4())

    # 创建任务状态记录
    task_data = {
        "task_id": task_id,
        "status": "pending",
        "message": "任务已创建，等待处理",
        "output_s3_url": None,
        "created_at": datetime.now(),
        "completed_at": None,
    }
    task_manager.create_task_data(task_id, task_data)

    # 将任务添加到队列
    await queue_processor.add_task(task_id, request)

    return LipSyncResponse(
        task_id=task_id, status="pending", message="任务已创建，正在队列中等待处理"
    )


@app.get("/tasks/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """获取任务状态"""
    task_data = task_manager.get_task_status_data(task_id)
    if task_data is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskStatus(**task_data)


@app.get("/tasks")
async def list_tasks():
    """列出所有任务"""
    return task_manager.list_all_tasks()


@app.get("/queue/status")
async def get_queue_status():
    """获取队列状态"""
    if queue_processor:
        return queue_processor.get_queue_status()
    else:
        return {"error": "队列处理器未初始化"}


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除任务（如果任务正在运行，会先中断进程然后删除所有数据）"""
    # 检查任务是否存在
    task_data = task_manager.get_task_status_data(task_id)
    if task_data is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 尝试取消任务（如果正在运行）
    if queue_processor:
        cancelled = await queue_processor.cancel_task(task_id)
        if cancelled:
            logger.info(f"任务 {task_id} 已被中断")

    # 删除任务数据
    if not task_manager.delete_task_data(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")

    return {"message": f"任务 {task_id} 已删除"}
