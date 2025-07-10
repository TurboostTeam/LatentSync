import os
from typing import Optional
from dotenv import find_dotenv, load_dotenv

# 加载环境变量
load_dotenv(find_dotenv())


class Config:
    """API配置类"""

    # S3兼容对象存储配置
    S3_ENDPOINT: str = os.getenv("S3_ENDPOINT")
    S3_ACCESS_KEY: str = os.getenv("S3_ACCESS_KEY")
    S3_SECRET_KEY: str = os.getenv("S3_SECRET_KEY")
    S3_REGION: str = os.getenv("S3_REGION")
    S3_BUCKET: str = os.getenv("S3_BUCKET")

    # Redis配置
    REDIS_HOST: str = os.getenv("REDIS_HOST")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")
    REDIS_DB: int = int(os.getenv("REDIS_DB"))
    REDIS_SSL: bool = os.getenv("REDIS_SSL").lower() == "true"

    # 模型配置
    MODEL_CONFIG_PATH: str = os.getenv(
        "MODEL_CONFIG_PATH", "configs/unet/stage2_512.yaml"
    )
    MODEL_CHECKPOINT_PATH: str = os.getenv(
        "MODEL_CHECKPOINT_PATH", "checkpoints/latentsync_unet.pt"
    )


config = Config()