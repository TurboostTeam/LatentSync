import ipaddress
import logging
import os
import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import unquote, urlparse

import requests
from fastapi import HTTPException

from .config import config

logger = logging.getLogger(__name__)


class BaseStorageClient:
    """存储客户端基类"""

    def upload_file(self, local_path: str, bucket: str, object_key: str) -> str:
        raise NotImplementedError

    def download_file(self, bucket: str, object_key: str, local_path: str):
        raise NotImplementedError

    def ensure_bucket_exists(self, bucket: str):
        raise NotImplementedError

    def build_url(self, bucket: str, object_key: str) -> str:
        raise NotImplementedError

    def parse_url(self, url: str) -> Tuple[str, str]:
        raise NotImplementedError


class S3CompatibleClient(BaseStorageClient):
    """S3兼容存储客户端（支持MinIO等）"""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool,
        region: str,
    ):
        from minio import Minio
        from minio.error import S3Error

        self.endpoint = endpoint
        self.secure = secure
        self.region = region
        self.S3Error = S3Error

        self.client = self._create_client(
            endpoint, access_key, secret_key, secure, region
        )

    def _create_client(
        self, endpoint: str, access_key: str, secret_key: str, secure: bool, region: str
    ):
        """创建S3兼容的对象存储客户端"""
        import urllib3
        from minio import Minio

        # 如果使用HTTPS但需要禁用SSL验证（例如自签名证书）
        if secure and os.getenv("S3_DISABLE_SSL_VERIFY", "false").lower() == "true":
            # 禁用SSL警告
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            # 创建不验证SSL的HTTP适配器
            from urllib3.util.ssl_ import create_urllib3_context

            http_client = urllib3.PoolManager(
                cert_reqs="CERT_NONE",
                ssl_context=create_urllib3_context(),
                assert_hostname=False,
            )

            return Minio(
                endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure,
                region=region,
                http_client=http_client,
            )
        else:
            return Minio(
                endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure,
                region=region,
            )

    def ensure_bucket_exists(self, bucket: str):
        """确保指定桶存在"""
        if not self.client.bucket_exists(bucket):
            try:
                self.client.make_bucket(bucket, location=self.region)
                logger.info(f"创建桶: {bucket}")
            except Exception as e:
                logger.warning(f"创建桶失败 {bucket}: {e} (可能桶已存在)")

    def upload_file(self, local_path: str, bucket: str, object_key: str) -> str:
        """上传文件到S3兼容存储"""
        try:
            self.ensure_bucket_exists(bucket)
            self.client.fput_object(bucket, object_key, local_path)
            logger.info(f"上传成功: {local_path} -> {bucket}/{object_key}")
            return self.build_url(bucket, object_key)
        except self.S3Error as e:
            logger.error(f"上传失败: {e}")
            raise HTTPException(status_code=500, detail=f"上传失败: {e}")
        except Exception as e:
            logger.error(f"上传失败: {e}")
            raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")

    def download_file(self, bucket: str, object_key: str, local_path: str):
        """从S3兼容存储下载文件"""
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            self.client.fget_object(bucket, object_key, local_path)
            logger.info(f"下载成功: {bucket}/{object_key} -> {local_path}")
        except self.S3Error as e:
            logger.error(f"对象存储下载失败: {e}")
            raise HTTPException(
                status_code=404, detail=f"文件未找到: {bucket}/{object_key}"
            )
        except Exception as e:
            logger.error(f"下载失败: {e}")
            raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")

    def build_url(self, bucket: str, object_key: str) -> str:
        """构建S3兼容存储URL"""
        protocol = "https" if self.secure else "http"

        if self._should_use_virtual_hosted_style():
            return f"{protocol}://{bucket}.{self.endpoint}/{object_key}"
        else:
            return f"{protocol}://{self.endpoint}/{bucket}/{object_key}"

    def parse_url(self, url: str) -> Tuple[str, str]:
        """解析S3兼容存储URL"""
        return self._parse_object_storage_url(url)

    def _should_use_virtual_hosted_style(self) -> bool:
        """判断是否应该使用Virtual Hosted-Style"""
        virtual_hosted_domains = [
            "aliyuncs.com",
            "amazonaws.com",
            "myqcloud.com",
            "myhuaweicloud.com",
            "bcebos.com",
        ]

        for domain in virtual_hosted_domains:
            if domain in self.endpoint:
                return True

        hostname = self.endpoint.split(":")[0]
        if self._is_ip_address(hostname):
            return False

        if self.endpoint.count(".") >= 2:
            return True

        return False

    def _is_ip_address(self, hostname: str) -> bool:
        """检查hostname是否是IP地址"""
        try:
            ipaddress.ip_address(hostname)
            return True
        except ValueError:
            return False

    def _parse_object_storage_url(self, url: str) -> Tuple[str, str]:
        """解析对象存储URL"""
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        path = parsed.path.lstrip("/")

        if "?" in path:
            path = path.split("?")[0]

        path = unquote(path)
        hostname_parts = hostname.split(".")

        if self._is_ip_address(hostname):
            path_parts = path.split("/", 1) if path else ["", ""]
            if len(path_parts) >= 2 and self._is_bucket_name(path_parts[0]):
                bucket = path_parts[0]
                object_key = path_parts[1] if len(path_parts) > 1 else ""
                return bucket, object_key
            else:
                raise ValueError(f"无法解析IP地址格式的URL: {url}")

        if len(hostname_parts) >= 2 and self._is_bucket_name(hostname_parts[0]):
            bucket = hostname_parts[0]
            object_key = path
            return bucket, object_key

        path_parts = path.split("/", 1) if path else ["", ""]
        if len(path_parts) >= 2 and self._is_bucket_name(path_parts[0]):
            bucket = path_parts[0]
            object_key = path_parts[1] if len(path_parts) > 1 else ""
            return bucket, object_key

        raise ValueError(f"无法解析URL: {url}")

    def _is_bucket_name(self, name: str) -> bool:
        """判断是否是有效的bucket名称"""
        if not name or len(name) < 3 or len(name) > 63:
            return False

        if not re.match(r"^[a-z0-9\-]+$", name):
            return False

        if name.startswith("-") or name.endswith("-"):
            return False

        if "--" in name:
            return False

        return True


class AliyunOSSClient(BaseStorageClient):
    """阿里云OSS客户端"""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        secure: bool = True,
        region: str = None,
    ):
        try:
            import oss2

            self.oss2 = oss2
        except ImportError:
            raise ImportError("请安装阿里云OSS SDK: pip install oss2")

        self.endpoint = endpoint
        self.bucket_name = bucket_name
        self.secure = secure
        self.region = region

        # 创建认证对象
        auth = oss2.Auth(access_key, secret_key)

        # 创建Bucket对象
        self.bucket = oss2.Bucket(auth, endpoint, bucket_name)

    def ensure_bucket_exists(self, bucket: str):
        """阿里云OSS的桶需要在控制台创建，这里只检查是否存在"""
        try:
            self.bucket.get_bucket_info()
            logger.info(f"桶 {bucket} 存在")
        except self.oss2.exceptions.NoSuchBucket:
            logger.warning(f"桶 {bucket} 不存在，请在阿里云控制台创建")
            raise HTTPException(status_code=404, detail=f"桶不存在: {bucket}")
        except Exception as e:
            logger.warning(f"检查桶状态失败: {e}")

    def upload_file(self, local_path: str, bucket: str, object_key: str) -> str:
        """上传文件到阿里云OSS"""
        try:
            # 阿里云OSS客户端已经绑定了特定的bucket，这里的bucket参数用于验证
            if bucket != self.bucket_name:
                logger.warning(
                    f"请求的桶 {bucket} 与配置的桶 {self.bucket_name} 不匹配"
                )

            self.ensure_bucket_exists(self.bucket_name)

            with open(local_path, "rb") as file_obj:
                self.bucket.put_object(object_key, file_obj)

            logger.info(f"上传成功: {local_path} -> {self.bucket_name}/{object_key}")
            return self.build_url(self.bucket_name, object_key)

        except self.oss2.exceptions.OssError as e:
            logger.error(f"阿里云OSS上传失败: {e}")
            raise HTTPException(status_code=500, detail=f"上传失败: {e}")
        except Exception as e:
            logger.error(f"上传失败: {e}")
            raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")

    def download_file(self, bucket: str, object_key: str, local_path: str):
        """从阿里云OSS下载文件"""
        try:
            if bucket != self.bucket_name:
                logger.warning(
                    f"请求的桶 {bucket} 与配置的桶 {self.bucket_name} 不匹配"
                )

            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            self.bucket.get_object_to_file(object_key, local_path)
            logger.info(f"下载成功: {self.bucket_name}/{object_key} -> {local_path}")

        except self.oss2.exceptions.NoSuchKey:
            logger.error(f"文件不存在: {self.bucket_name}/{object_key}")
            raise HTTPException(status_code=404, detail=f"文件未找到: {object_key}")
        except self.oss2.exceptions.OssError as e:
            logger.error(f"阿里云OSS下载失败: {e}")
            raise HTTPException(status_code=500, detail=f"下载失败: {e}")
        except Exception as e:
            logger.error(f"下载失败: {e}")
            raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")

    def build_url(self, bucket: str, object_key: str) -> str:
        """构建阿里云OSS URL - 生成预签名URL以支持私有文件访问"""
        try:
            from .config import config

            # 生成预签名URL，有效期可配置（默认24小时）
            expire_seconds = config.SIGNED_URL_EXPIRE_HOURS * 3600
            signed_url = self.bucket.sign_url("GET", object_key, expire_seconds)
            logger.info(
                f"生成预签名URL: {bucket}/{object_key}，有效期: {config.SIGNED_URL_EXPIRE_HOURS}小时"
            )
            return signed_url
        except Exception as e:
            logger.warning(f"生成预签名URL失败: {e}，回退到直接URL")
            # 如果生成预签名URL失败，回退到直接URL（适用于公共读bucket）
            protocol = "https" if self.secure else "http"
            return f"{protocol}://{bucket}.{self.endpoint}/{object_key}"

    def parse_url(self, url: str) -> Tuple[str, str]:
        """解析阿里云OSS URL"""
        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        # 阿里云OSS URL格式: https://bucket.oss-region.aliyuncs.com/path/file
        if ".aliyuncs.com" in hostname:
            parts = hostname.split(".")
            if len(parts) >= 3:
                bucket = parts[0]
                object_key = parsed.path.lstrip("/")
                object_key = unquote(object_key)
                return bucket, object_key

        raise ValueError(f"无法解析阿里云OSS URL: {url}")


class StorageManager:
    """统一存储管理器"""

    def __init__(self):
        self.storage_config = config.get_effective_storage_config()
        self.client = self._create_client()

        logger.info(f"初始化存储后端: {self.storage_config['backend']}")

    def _create_client(self) -> BaseStorageClient:
        """根据配置创建相应的存储客户端"""
        backend = self.storage_config["backend"]

        if backend == "ALIYUN_OSS":
            if not self.storage_config.get("bucket"):
                raise ValueError("使用阿里云OSS时，必须配置 S3_BUCKET 环境变量")

            return AliyunOSSClient(
                endpoint=self.storage_config["endpoint"],
                access_key=self.storage_config["access_key"],
                secret_key=self.storage_config["secret_key"],
                bucket_name=self.storage_config["bucket"],
                secure=self.storage_config.get("secure", True),
                region=self.storage_config.get("region"),
            )

        elif backend == "S3_COMPATIBLE":
            return S3CompatibleClient(
                endpoint=self.storage_config["endpoint"],
                access_key=self.storage_config["access_key"],
                secret_key=self.storage_config["secret_key"],
                secure=self.storage_config.get("secure", False),
                region=self.storage_config.get("region", "us-east-1"),
            )

        else:
            raise ValueError(f"不支持的存储后端: {backend}")

    def get_backend_type(self) -> str:
        """获取当前存储后端类型"""
        return self.storage_config["backend"]

    def ensure_bucket_exists(self, bucket: str):
        """确保指定桶存在"""
        self.client.ensure_bucket_exists(bucket)

    def download_file_from_url(self, url: str, local_path: str):
        """从对象存储URL下载文件"""
        try:
            bucket, object_key = self.client.parse_url(url)
            logger.info(f"开始下载: {url} -> bucket={bucket}, key={object_key}")
            self.client.download_file(bucket, object_key, local_path)
        except ValueError as e:
            logger.error(f"URL解析失败: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"下载失败: {e}")
            raise

    def upload_file_to_bucket(
        self, local_path: str, bucket: str, object_key: str
    ) -> str:
        """上传文件到指定的bucket和object key，返回对象存储URL"""
        return self.client.upload_file(local_path, bucket, object_key)

    def build_storage_url(self, bucket: str, object_key: str) -> str:
        """构建对象存储URL"""
        return self.client.build_url(bucket, object_key)

    def parse_object_storage_url(self, url: str) -> Tuple[str, str]:
        """解析对象存储URL"""
        return self.client.parse_url(url)

    # 保留向后兼容的方法
    def build_s3_url(self, bucket: str, key: str) -> str:
        """构建对象存储URL（保持向后兼容）"""
        return self.build_storage_url(bucket, key)

    def upload_file_to_s3_url(self, local_path: str, s3_url: str):
        """上传文件到指定的对象存储URL（保持向后兼容）"""
        bucket, object_key = self.parse_object_storage_url(s3_url)
        self.upload_file_to_bucket(local_path, bucket, object_key)

    def upload_file(self, bucket: str, object_key: str, local_path: str):
        """上传文件到对象存储（保持向后兼容）"""
        self.upload_file_to_bucket(local_path, bucket, object_key)


# 全局存储管理器实例
storage_manager = None


def get_storage_manager():
    """获取存储管理器实例"""
    global storage_manager
    if storage_manager is None:
        storage_manager = StorageManager()
    return storage_manager
