import os
import oss2
from typing import  Tuple
from urllib.parse import unquote, urlparse

from bullmq_worker.utils.logging import logger
from bullmq_worker.storage.base_storage_client import BaseStorageClient


class AliyunOSSClient(BaseStorageClient):
    """阿里云OSS客户端"""

    def __init__(self, endpoint: str, access_key: str, secret_key: str, region: str, bucket_name: str):
        super().__init__(endpoint, access_key, secret_key, region, bucket_name)

        # 创建认证对象
        auth = oss2.Auth(self.access_key, self.secret_key)

        # 创建Bucket对象
        self.bucket = oss2.Bucket(auth, self.endpoint, self.bucket_name)

        # 检查桶是否存在
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """阿里云OSS的桶需要在控制台创建，这里只检查是否存在"""
        try:
            self.bucket.get_bucket_info()
            logger.info(f"桶 {self.bucket_name} 存在")
        except oss2.exceptions.NoSuchBucket:
            logger.error(f"桶 {self.bucket_name} 不存在")
            raise RuntimeError(f"桶 {self.bucket_name} 不存在")
        except Exception as e:
            logger.error(f"检查桶状态失败: {e}")
            raise RuntimeError(f"检查桶状态失败: {e}")

    def download_file(self, object_key: str, local_path: str) -> str:
        """从阿里云OSS下载文件"""
        try:
            # 创建本地目录
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            # 下载文件
            self.bucket.get_object_to_file(object_key, local_path)

            logger.info(f"下载成功: {self.bucket_name}/{object_key} -> {local_path}")

        except oss2.exceptions.NoSuchKey:
            logger.error(f"文件不存在: {self.bucket_name}/{object_key}")
            raise RuntimeError(f"文件不存在: {self.bucket_name}/{object_key}")
        except oss2.exceptions.OssError as e:
            logger.error(f"阿里云OSS下载失败: {e}")
            raise RuntimeError(f"阿里云OSS下载失败: {e}")

    def upload_file(self, object_key: str, local_path: str) -> str:
        """上传文件到阿里云OSS"""
        try:
            # 检查本地文件是否存在
            if not os.path.exists(local_path):
                raise FileNotFoundError(f"本地文件不存在: {local_path}")
            
            # 上传文件
            with open(local_path, "rb") as file_obj:
                self.bucket.put_object(object_key, file_obj)
            logger.info(f"上传成功: {local_path} -> {self.bucket_name}/{object_key}")
            
            # 生成预签名URL
            output_url = self.build_url(object_key)

            return output_url

        except oss2.exceptions.OssError as e:
            logger.error(f"阿里云OSS上传失败: {e}")
            raise RuntimeError(f"阿里云OSS上传失败: {e}")
    
    def build_url(self, object_key: str, signer_url_expire_hours: int = 24) -> str:
        """构建阿里云OSS URL - 生成预签名URL以支持私有文件访问"""
        try:
            expire_seconds = signer_url_expire_hours * 3600
            signed_url = self.bucket.sign_url("GET", object_key, expire_seconds)

            logger.info(
                f"生成预签名URL: {signed_url}，有效期: {signer_url_expire_hours}小时"
            )
            return signed_url
        
        except Exception as e:
            logger.error(f"生成预签名URL失败: {e}")
            raise RuntimeError(f"生成预签名URL失败: {e}")

    def parse_url(self, url: str) -> Tuple[str, str]:
        """解析阿里云OSS URL"""
        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        # 阿里云OSS URL格式: https://bucket.oss-region.aliyuncs.com/path/file
        if ".aliyuncs.com" in hostname:
            parts = hostname.split(".")
            if len(parts) >= 3:
                bucket = parts[0]
                object_key = unquote(parsed.path.lstrip("/"))
                return bucket, object_key

        raise ValueError(f"无法解析阿里云OSS URL: {url}")


def test_client():
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv())

    client = AliyunOSSClient(
        endpoint=os.getenv("S3_ENDPOINT"),
        access_key=os.getenv("S3_ACCESS_KEY"),
        secret_key=os.getenv("S3_SECRET_KEY"),
        bucket_name=os.getenv("S3_BUCKET"),
        region=os.getenv("S3_REGION")
    )

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
