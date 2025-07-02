import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import redis

from .config import config

logger = logging.getLogger(__name__)


class RedisTaskStore:
    """Redis任务状态存储"""

    def __init__(self):
        connection_params = {
            "host": config.REDIS_HOST,
            "port": config.REDIS_PORT,
            "password": config.REDIS_PASSWORD,
            "db": config.REDIS_DB,
            "decode_responses": True,
        }

        # 如果配置了SSL，添加SSL参数
        if config.REDIS_SSL:
            connection_params["ssl"] = True
            connection_params["ssl_cert_reqs"] = None  # 不验证证书

        # 如果配置了用户名，添加用户名参数
        if config.REDIS_USERNAME:
            connection_params["username"] = config.REDIS_USERNAME

        self.redis_client = redis.Redis(**connection_params)
        self.task_prefix = "task:"

    def _get_task_key(self, task_id: str) -> str:
        """获取任务的Redis key"""
        return f"{self.task_prefix}{task_id}"

    def set_task(
        self, task_id: str, task_data: Dict[str, Any], expire_seconds: int = 86400
    ):
        """设置任务状态"""
        key = self._get_task_key(task_id)

        # 处理datetime对象
        serializable_data = {}
        for k, v in task_data.items():
            if isinstance(v, datetime):
                serializable_data[k] = v.isoformat()
            else:
                serializable_data[k] = v

        self.redis_client.setex(key, expire_seconds, json.dumps(serializable_data))
        logger.debug(f"设置任务状态: {task_id}")

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        key = self._get_task_key(task_id)
        data = self.redis_client.get(key)

        if data is None:
            return None

        task_data = json.loads(data)

        # 将ISO格式时间字符串转换回datetime对象
        for k, v in task_data.items():
            if k.endswith("_at") and isinstance(v, str):
                try:
                    task_data[k] = datetime.fromisoformat(v)
                except (ValueError, TypeError):
                    pass

        return task_data

    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        key = self._get_task_key(task_id)
        result = self.redis_client.delete(key)
        logger.debug(f"删除任务: {task_id}")
        return result > 0

    def list_tasks(self) -> list:
        """列出所有任务"""
        keys = self.redis_client.keys(f"{self.task_prefix}*")
        tasks = []

        for key in keys:
            data = self.redis_client.get(key)
            if data:
                task_data = json.loads(data)
                # 转换时间字段
                for k, v in task_data.items():
                    if k.endswith("_at") and isinstance(v, str):
                        try:
                            task_data[k] = datetime.fromisoformat(v)
                        except (ValueError, TypeError):
                            pass
                tasks.append(task_data)

        # 按创建时间排序
        tasks.sort(key=lambda x: x.get("created_at", datetime.min), reverse=True)
        return tasks

    def update_task_status(
        self, task_id: str, status: str, message: str = "", **kwargs
    ):
        """更新任务状态"""
        task_data = self.get_task(task_id)
        if task_data is None:
            logger.warning(f"任务不存在: {task_id}")
            return False

        task_data["status"] = status
        task_data["message"] = message

        # 更新其他字段
        for k, v in kwargs.items():
            task_data[k] = v

        # 如果任务完成或失败，设置完成时间
        if status in ["completed", "failed"]:
            task_data["completed_at"] = datetime.now()

        self.set_task(task_id, task_data)
        return True

    def health_check(self) -> bool:
        """健康检查"""
        try:
            self.redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis健康检查失败: {e}")
            return False


def get_redis_client():
    """获取Redis客户端实例"""
    return RedisTaskStore()
