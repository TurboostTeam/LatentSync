import logging
from typing import Optional, Dict, Any
from datetime import datetime
from .redis_client import get_redis_client

logger = logging.getLogger(__name__)

class TaskManager:
    def __init__(self):
        self.redis_store = None
        self._initialize_redis()
    
    def _initialize_redis(self):
        """初始化Redis连接"""
        try:
            self.redis_store = get_redis_client()
            if not self.redis_store.health_check():
                raise Exception("Redis健康检查失败")
            logger.info("Redis 连接成功")
        except Exception as e:
            logger.error(f"Redis 初始化失败: {e}")
            raise RuntimeError(f"Redis连接是必需的，请检查Redis配置和服务状态: {e}")
    
    def update_task_status(self, task_id: str, status: str, message: str = "", **kwargs):
        """更新任务状态"""
        if not self.redis_store:
            raise RuntimeError("Redis连接未初始化")
        
        self.redis_store.update_task_status(task_id, status, message, **kwargs)
    
    def get_task_status_data(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态数据"""
        if not self.redis_store:
            raise RuntimeError("Redis连接未初始化")
        
        return self.redis_store.get_task(task_id)
    
    def list_all_tasks(self):
        """列出所有任务"""
        if not self.redis_store:
            raise RuntimeError("Redis连接未初始化")
        
        return self.redis_store.list_tasks()
    
    def delete_task_data(self, task_id: str) -> bool:
        """删除任务数据"""
        if not self.redis_store:
            raise RuntimeError("Redis连接未初始化")
        
        return self.redis_store.delete_task(task_id)
    
    def create_task_data(self, task_id: str, task_data: dict):
        """创建任务数据"""
        if not self.redis_store:
            raise RuntimeError("Redis连接未初始化")
        
        self.redis_store.set_task(task_id, task_data)
    
    def health_check(self) -> bool:
        """检查Redis连接健康状态"""
        if not self.redis_store:
            return False
        return self.redis_store.health_check()

# 全局任务管理器实例
task_manager = None

def get_task_manager():
    """获取任务管理器实例"""
    global task_manager
    if task_manager is None:
        task_manager = TaskManager()
    return task_manager 