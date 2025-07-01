import os
from typing import Optional

from dotenv import find_dotenv, load_dotenv

# 加载环境变量
load_dotenv(find_dotenv())


class Config:
    """API配置类"""

    # S3兼容对象存储配置
    S3_ENDPOINT: str = os.getenv("S3_ENDPOINT", "localhost:9000")
    S3_ACCESS_KEY: str = os.getenv("S3_ACCESS_KEY", "minioadmin")
    S3_SECRET_KEY: str = os.getenv("S3_SECRET_KEY", "minioadmin")
    S3_SECURE: bool = os.getenv("S3_SECURE", "False").lower() == "true"
    S3_REGION: str = os.getenv("S3_REGION", "us-east-1")

    # Redis配置
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))

    # 模型配置
    MODEL_CONFIG_PATH: str = os.getenv(
        "MODEL_CONFIG_PATH", "configs/unet/stage2_512.yaml"
    )
    MODEL_CHECKPOINT_PATH: str = os.getenv(
        "MODEL_CHECKPOINT_PATH", "checkpoints/latentsync_unet.pt"
    )

    # API配置
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    @classmethod
    def validate(cls):
        """验证配置"""
        if not os.path.exists(cls.MODEL_CONFIG_PATH):
            raise FileNotFoundError(f"模型配置文件不存在: {cls.MODEL_CONFIG_PATH}")

        if not os.path.exists(cls.MODEL_CHECKPOINT_PATH):
            raise FileNotFoundError(f"模型权重文件不存在: {cls.MODEL_CHECKPOINT_PATH}")


config = Config()
