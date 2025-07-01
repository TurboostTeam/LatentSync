"""
RunPod Serverless Handler - FastAPI 适配器
将 RunPod 请求转换为对 FastAPI 应用的内部调用
"""
import asyncio
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局 FastAPI 应用实例和初始化状态
app = None
is_initialized = False

async def initialize_fastapi_app():
    """初始化 FastAPI 应用（只执行一次）"""
    global app, is_initialized
    
    if not is_initialized:
        logger.info("初始化 FastAPI 应用...")
        
        try:
            from api.server import app as fastapi_app
            from api.server import startup_event
            
            # 运行 FastAPI 启动事件
            await startup_event()
            
            app = fastapi_app
            is_initialized = True
            logger.info("FastAPI 应用初始化完成")
        except Exception as e:
            logger.error(f"FastAPI 应用初始化失败: {e}")
            raise

def handler(job):
    """
    RunPod Serverless Handler 函数
    将 RunPod 请求转换为 FastAPI 内部调用
    
    Args:
        job (dict): 包含输入数据和请求元数据的字典
        
    Returns:
        dict: 处理结果
    """
    try:
        # 确保 FastAPI 应用已初始化（只初始化一次）
        if not is_initialized:
            asyncio.run(initialize_fastapi_app())
        
        # 获取输入数据
        job_input = job.get("input", {})
        
        # 检查操作类型
        operation = job_input.get("operation", "lipsync")
        
        # 将操作分派到对应的处理函数
        if operation == "health":
            return handle_health_check()
        elif operation == "lipsync":
            return handle_lipsync_request(job_input)
        elif operation == "status":
            return handle_status_request(job_input)
        elif operation == "list_tasks":
            return handle_list_tasks()
        elif operation == "queue_status":
            return handle_queue_status()
        elif operation == "delete_task":
            return handle_delete_task(job_input)
        else:
            return {
                "error": f"不支持的操作: {operation}",
                "supported_operations": ["health", "lipsync", "status", "list_tasks", "queue_status", "delete_task"]
            }
            
    except Exception as e:
        logger.error(f"Handler 处理错误: {e}")
        return {"error": f"处理请求时发生错误: {str(e)}"}

def handle_health_check():
    """处理健康检查请求 - 调用 FastAPI 健康检查端点"""
    try:
        # 调用 FastAPI 健康检查函数
        from api.server import health_check
        
        result = asyncio.run(health_check())
        
        # 只添加 RunPod 模式标识，保持原始响应格式
        result["mode"] = "runpod_serverless"
        
        return result
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "mode": "runpod_serverless"
        }

def handle_lipsync_request(job_input):
    """处理唇形同步请求 - 调用 FastAPI 创建任务端点"""
    try:
        # 验证输入参数
        video_url = job_input.get("video_url")
        audio_url = job_input.get("audio_url")
        
        if not video_url or not audio_url:
            return {
                "error": "缺少必需参数: video_url 和 audio_url",
                "required_params": ["video_url", "audio_url"]
            }
        
        # 创建 FastAPI 请求对象
        from api.models import LipSyncRequest
        from api.server import create_lip_sync_task
        
        request = LipSyncRequest(video_url=video_url, audio_url=audio_url)
        
        # 调用 FastAPI 创建任务函数
        result = asyncio.run(create_lip_sync_task(request))
        
        # 转换为字典并添加模式标识
        response = result.dict()
        response["mode"] = "runpod_serverless"
        
        return response
        
    except Exception as e:
        logger.error(f"处理唇形同步请求失败: {e}")
        return {"error": f"创建任务失败: {str(e)}"}

def handle_status_request(job_input):
    """处理任务状态查询请求 - 调用 FastAPI 状态查询端点"""
    try:
        task_id = job_input.get("task_id")
        if not task_id:
            return {"error": "缺少参数: task_id"}
        
        # 调用 FastAPI 状态查询函数
        from api.server import get_task_status
        from fastapi import HTTPException
        
        try:
            result = asyncio.run(get_task_status(task_id))
            
            # 转换为字典并添加模式标识，保持原始格式
            response = result.dict()
            response["mode"] = "runpod_serverless"
            
            return response
            
        except HTTPException as e:
            if e.status_code == 404:
                return {"error": "任务不存在", "task_id": task_id}
            else:
                return {"error": f"查询任务状态失败: {e.detail}"}
        
    except Exception as e:
        logger.error(f"查询任务状态失败: {e}")
        return {"error": f"查询任务状态失败: {str(e)}"}

def handle_list_tasks():
    """处理任务列表查询请求 - 调用 FastAPI 任务列表端点"""
    try:
        # 调用 FastAPI 任务列表函数
        from api.server import list_tasks
        
        result = asyncio.run(list_tasks())
        
        # list_tasks 返回的是列表，需要包装成字典格式
        response = {
            "tasks": result,
            "mode": "runpod_serverless"
        }
        
        return response
        
    except Exception as e:
        logger.error(f"获取任务列表失败: {e}")
        return {"error": f"获取任务列表失败: {str(e)}"}

def handle_queue_status():
    """处理获取队列状态请求 - 调用 FastAPI 队列状态端点"""
    try:
        # 调用 FastAPI 队列状态函数
        from api.server import get_queue_status
        
        result = asyncio.run(get_queue_status())
        
        # 添加模式标识
        result["mode"] = "runpod_serverless"
        
        return result
        
    except Exception as e:
        logger.error(f"获取队列状态失败: {e}")
        return {"error": f"获取队列状态失败: {str(e)}"}

def handle_delete_task(job_input):
    """处理删除任务请求 - 调用 FastAPI 删除任务端点"""
    try:
        task_id = job_input.get("task_id")
        if not task_id:
            return {"error": "缺少参数: task_id"}
        
        # 调用 FastAPI 删除任务函数
        from api.server import delete_task
        from fastapi import HTTPException
        
        try:
            result = asyncio.run(delete_task(task_id))
            
            # 只添加模式标识，保持原始响应格式
            result["mode"] = "runpod_serverless"
            
            return result
            
        except HTTPException as e:
            if e.status_code == 404:
                return {"error": "任务不存在", "task_id": task_id}
            else:
                return {"error": f"删除任务失败: {e.detail}"}
        
    except Exception as e:
        logger.error(f"删除任务失败: {e}")
        return {"error": f"删除任务失败: {str(e)}"}

def start_runpod_handler():
    """启动 RunPod Serverless Handler"""
    try:
        import runpod
    except ImportError:
        logger.error("runpod 库未安装，无法启动 RunPod 模式")
        logger.info("请运行: pip install runpod")
        raise
    
    logger.info("启动 RunPod Serverless Handler (FastAPI 适配器模式)")
    runpod.serverless.start({"handler": handler})
