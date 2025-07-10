import os
from typing import Tuple
from urllib.parse import urlparse, unquote
from datetime import timedelta
from minio import Minio
from minio.error import S3Error

from bullmq_worker.utils.logging import logger
from bullmq_worker.storage.base_storage_client import BaseStorageClient


class MinIOClient(BaseStorageClient):
    """MinIO客户端"""

    def __init__(self, endpoint: str, access_key: str, secret_key: str, region: str, bucket_name: str):
        super().__init__(endpoint, access_key, secret_key, region, bucket_name)
        
        # 检测并设置secure模式和endpoint
        self.endpoint, self.secure = self._detect_secure_mode(endpoint)

        # 创建MinIO客户端
        self.client = Minio(
            endpoint=self.endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=self.secure,
            region=region,
        )

        protocol = "HTTPS" if self.secure else "HTTP"
        logger.info(f"MinIO客户端初始化成功 - 服务器: {protocol}://{self.endpoint}, 桶: {bucket_name}")

        # 确保桶存在
        self.ensure_bucket_exists(bucket_name)

    def _detect_secure_mode(self, endpoint: str) -> Tuple[str, bool]:
        """检测并设置secure模式
        
        Args:
            endpoint: 原始endpoint
            
        Returns:
            tuple: (处理后的endpoint, secure模式)
        """
        
        # 自动检测secure模式
        if endpoint.startswith('https://'):
            return endpoint.replace('https://', ''), True
        elif endpoint.startswith('http://'):
            return endpoint.replace('http://', ''), False
        # 如果是localhost或127.0.0.1，默认使用HTTP
        elif 'localhost' in endpoint or '127.0.0.1' in endpoint:
            return endpoint, False
        else:
            # 其他情况默认使用HTTPS
            return endpoint, True

    def ensure_bucket_exists(self, bucket: str):
        """确保指定桶存在"""
        if not self.client.bucket_exists(bucket):
            try:
                self.client.make_bucket(bucket, location=self.region)
                logger.info(f"创建桶: {bucket}")
            except Exception as e:
                logger.warning(f"创建桶失败 {bucket}: {e}")
                raise RuntimeError(f"创建桶失败 {bucket}: {e}")
        else:
            logger.info(f"桶 {bucket} 存在")

    def download_file(self, object_key: str, local_path: str):
        """从MinIO下载文件"""
        try:
            # 创建本地目录
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            # 下载文件
            self.client.fget_object(
                bucket_name=self.bucket_name,
                object_name=object_key,
                file_path=local_path,
            )

            logger.info(f"下载成功: {self.bucket_name}/{object_key} -> {local_path}")

        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.error(f"文件不存在: {self.bucket_name}/{object_key}")
                raise RuntimeError(f"文件不存在: {self.bucket_name}/{object_key}")
            else:
                logger.error(f"MinIO下载失败: {e}")
                raise RuntimeError(f"MinIO下载失败: {e}")
        except Exception as e:
            logger.error(f"下载文件时发生错误: {e}")
            raise RuntimeError(f"下载文件时发生错误: {e}")
    
    def upload_file(self, object_key: str, local_path: str, **kwargs) -> str:
        """上传文件到MinIO"""
        try:
            # 检查本地文件是否存在
            if not os.path.exists(local_path):
                raise FileNotFoundError(f"本地文件不存在: {local_path}")

            # 上传文件
            self.client.fput_object(
                bucket_name=self.bucket_name,
                object_name=object_key,
                file_path=local_path,
            )
            logger.info(f"上传成功: {local_path} -> {self.bucket_name}/{object_key}")

            # 生成预签名URL
            output_url = self.build_url(self.bucket_name, object_key)
            logger.info(f"输出URL: {output_url}")

            return output_url

        except S3Error as e:
            logger.error(f"MinIO上传失败: {e}")
            raise RuntimeError(f"MinIO上传失败: {e}")
        except Exception as e:
            logger.error(f"上传文件时发生错误: {e}")
            raise RuntimeError(f"上传文件时发生错误: {e}")

    def build_url(self, bucket: str, object_key: str, signer_url_expire_hours: int = 24) -> str:
        """构建MinIO URL - 生成预签名URL"""
        try:
            # 生成预签名URL
            expire_seconds = timedelta(hours=signer_url_expire_hours)
            signed_url = self.client.presigned_get_object(
                bucket_name=bucket,
                object_name=object_key,
                expires=expire_seconds,
            )

            logger.info(f"生成预签名URL: {signed_url}，有效期: {signer_url_expire_hours}小时")
            return signed_url
        
        except Exception as e:
            logger.error(f"生成预签名URL失败: {e}")
            raise RuntimeError(f"生成预签名URL失败: {e}")

    def parse_url(self, url: str) -> Tuple[str, str]:
        """解析MinIO URL"""
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        port = parsed.port

        # 构建完整的endpoint用于比较
        endpoint_to_check = f"{hostname}:{port}" if port else hostname
        
        # MinIO URL格式: http://127.0.0.1:9000/bucket/path/file
        # 检查hostname是否匹配（忽略协议）
        if (hostname in self.endpoint or 
            endpoint_to_check in self.endpoint or 
            self.endpoint.replace('http://', '').replace('https://', '') == endpoint_to_check):
            
            path_parts = parsed.path.strip("/").split("/", 1)
            if len(path_parts) >= 2:
                bucket = path_parts[0]
                object_key = unquote(path_parts[1])
                return bucket, object_key
            elif len(path_parts) == 1:
                # 如果只有一个路径部分，可能是bucket.endpoint格式
                parts = hostname.split(".")
                if len(parts) >= 2:
                    bucket = parts[0]
                    object_key = unquote(path_parts[0])
                    return bucket, object_key

        raise ValueError(f"无法解析MinIO URL: {url}")


def test_client():
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv())

    client = MinIOClient(
        endpoint=os.getenv("S3_ENDPOINT"),
        access_key=os.getenv("S3_ACCESS_KEY"),
        secret_key=os.getenv("S3_SECRET_KEY"),
        bucket_name=os.getenv("S3_BUCKET"),
        region=os.getenv("S3_REGION"),
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
    