from typing import Dict, Type

from bullmq_worker.utils.config import config
from bullmq_worker.utils.logging import logger
from bullmq_worker.storage.base_storage_client import BaseStorageClient
from bullmq_worker.storage.aliyun_oss_client import AliyunOSSClient
from bullmq_worker.storage.minio_client import MinIOClient


# 客户端注册表
CLIENT_REGISTRY: Dict[str, Type[BaseStorageClient]] = {
    "minio": MinIOClient,
    "aliyun_oss": AliyunOSSClient,
}


class StorageFactory:
    def __init__(self):
        self.s3_endpoint = config.S3_ENDPOINT
        self.s3_access_key = config.S3_ACCESS_KEY
        self.s3_secret_key = config.S3_SECRET_KEY
        self.s3_region = config.S3_REGION
        self.s3_bucket = config.S3_BUCKET

        self.backend_type = self._detect_storage_backend()
        self.client = self._create_client()

    def _detect_storage_backend(self):
        endpoint_lower = self.s3_endpoint.lower()

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
            backend_type = "aliyun_oss"
        else:
            backend_type = "minio"

        logger.info(f"检测到存储后端: {backend_type}")
        return backend_type


    def _create_client(self):
        client_class = CLIENT_REGISTRY.get(self.backend_type)
        if not client_class:
            raise ValueError(f"不支持的存储后端: {self.backend_type}")
        
        return client_class(
            endpoint=self.s3_endpoint,
            access_key=self.s3_access_key,
            secret_key=self.s3_secret_key,
            region=self.s3_region,
            bucket_name=self.s3_bucket,
        )



def test_client():
    client = StorageFactory().client

    # 上传文件
    local_path = "assets/demo1_audio.wav"
    url = client.upload_file(
        object_key="wjw_demo1_audio.wav",
        local_path=local_path
    )

    # 下载文件
    bucket, object_key = client.parse_url(url)
    client.download_file(
        object_key=object_key,
        local_path=f"downloads/{object_key}"
    )


if __name__ == "__main__":
    test_client()
