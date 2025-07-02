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
    S3_BUCKET: str = os.getenv("S3_BUCKET", "")  # 可选的默认桶名

    # Redis配置
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_SSL: bool = os.getenv("REDIS_SSL", "False").lower() == "true"
    REDIS_USERNAME: Optional[str] = os.getenv("REDIS_USERNAME")

    # 模型配置
    MODEL_CONFIG_PATH: str = os.getenv(
        "MODEL_CONFIG_PATH", "configs/unet/stage2_512.yaml"
    )
    MODEL_CHECKPOINT_PATH: str = os.getenv(
        "MODEL_CHECKPOINT_PATH", "checkpoints/latentsync_unet.pt"
    )

    # API配置
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # 对象存储URL配置
    SIGNED_URL_EXPIRE_HOURS: int = int(os.getenv("SIGNED_URL_EXPIRE_HOURS", "24"))

    @classmethod
    def detect_storage_backend(cls) -> str:
        """
        自动检测存储后端类型
        返回: "ALIYUN_OSS" 或 "S3_COMPATIBLE"
        """
        endpoint_lower = cls.S3_ENDPOINT.lower()

        # 检查endpoint是否指向阿里云OSS
        aliyun_indicators = [
            "aliyuncs.com",
            "oss-cn-",
            "oss-us-",
            "oss-eu-",
            "oss-ap-",
            ".oss.",
        ]

        if any(indicator in endpoint_lower for indicator in aliyun_indicators):
            return "ALIYUN_OSS"

        # 默认使用S3兼容模式
        return "S3_COMPATIBLE"

    @classmethod
    def get_effective_storage_config(cls):
        """
        根据检测到的存储后端返回有效的配置
        """
        backend = cls.detect_storage_backend()

        if backend == "ALIYUN_OSS":
            return {
                "backend": "ALIYUN_OSS",
                "endpoint": cls.S3_ENDPOINT,
                "access_key": cls.S3_ACCESS_KEY,
                "secret_key": cls.S3_SECRET_KEY,
                "secure": cls.S3_SECURE,
                "region": cls.S3_REGION,
                "bucket": cls.S3_BUCKET,
            }

        # S3兼容模式
        return {
            "backend": "S3_COMPATIBLE",
            "endpoint": cls.S3_ENDPOINT,
            "access_key": cls.S3_ACCESS_KEY,
            "secret_key": cls.S3_SECRET_KEY,
            "secure": cls.S3_SECURE,
            "region": cls.S3_REGION,
        }

    @classmethod
    def validate(cls):
        """验证配置"""
        if not os.path.exists(cls.MODEL_CONFIG_PATH):
            raise FileNotFoundError(f"模型配置文件不存在: {cls.MODEL_CONFIG_PATH}")

        if not os.path.exists(cls.MODEL_CHECKPOINT_PATH):
            raise FileNotFoundError(f"模型权重文件不存在: {cls.MODEL_CHECKPOINT_PATH}")

        # 验证存储配置
        storage_config = cls.get_effective_storage_config()
        if storage_config["backend"] == "ALIYUN_OSS":
            if not storage_config.get("bucket"):
                raise ValueError("使用阿里云OSS时，必须配置 S3_BUCKET 环境变量指定桶名")


config = Config()
