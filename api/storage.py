import ipaddress
import logging
import os
import re
from typing import Tuple
from urllib.parse import urlparse

import requests
from fastapi import HTTPException
from minio import Minio
from minio.error import S3Error

from .config import config

logger = logging.getLogger(__name__)


class StorageManager:
    def __init__(self):
        self.s3_endpoint = config.S3_ENDPOINT
        self.s3_access_key = config.S3_ACCESS_KEY
        self.s3_secret_key = config.S3_SECRET_KEY
        self.s3_secure = config.S3_SECURE
        self.s3_region = config.S3_REGION

        self.client = self._create_client()

    def _create_client(self):
        """创建S3兼容的对象存储客户端"""
        import urllib3

        # 如果使用HTTPS但需要禁用SSL验证（例如自签名证书）
        if (
            self.s3_secure
            and os.getenv("S3_DISABLE_SSL_VERIFY", "false").lower() == "true"
        ):
            # 禁用SSL警告
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            # 创建不验证SSL的HTTP适配器
            import requests
            from urllib3.util.ssl_ import create_urllib3_context

            http_client = urllib3.PoolManager(
                cert_reqs="CERT_NONE",
                ssl_context=create_urllib3_context(),
                assert_hostname=False,
            )

            return Minio(
                self.s3_endpoint,
                access_key=self.s3_access_key,
                secret_key=self.s3_secret_key,
                secure=self.s3_secure,
                region=self.s3_region,
                http_client=http_client,
            )
        else:
            return Minio(
                self.s3_endpoint,
                access_key=self.s3_access_key,
                secret_key=self.s3_secret_key,
                secure=self.s3_secure,
                region=self.s3_region,
            )

    def _is_ip_address(self, hostname: str) -> bool:
        """检查hostname是否是IP地址"""
        try:
            ipaddress.ip_address(hostname)
            return True
        except ValueError:
            return False

    def parse_object_storage_url(self, url: str) -> Tuple[str, str]:
        """
        通用对象存储URL解析器
        支持两种常见模式：
        1. Virtual Hosted-Style: https://bucket.domain.com/path/file.ext
        2. Path-Style: https://domain.com/bucket/path/file.ext

        返回: (bucket, object_key)
        """
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        path = parsed.path.lstrip("/")

        # 移除查询参数
        if "?" in path:
            path = path.split("?")[0]

        # 检测URL模式
        hostname_parts = hostname.split(".")

        # 如果hostname是IP地址，直接使用Path-Style解析
        if self._is_ip_address(hostname):
            path_parts = path.split("/", 1) if path else ["", ""]
            if len(path_parts) >= 2 and self._is_bucket_name(path_parts[0]):
                bucket = path_parts[0]
                object_key = path_parts[1] if len(path_parts) > 1 else ""
                return bucket, object_key
            else:
                raise ValueError(
                    f"无法解析IP地址格式的URL: {url}。Path-Style格式应为: http://ip:port/bucket/path/file.ext"
                )

        # Virtual Hosted-Style 判断：
        # 如果hostname有多个部分，且第一部分看起来像bucket名称
        if len(hostname_parts) >= 2 and self._is_bucket_name(hostname_parts[0]):
            # Virtual Hosted-Style: bucket.domain.com/path/file.ext
            bucket = hostname_parts[0]
            object_key = path
            return bucket, object_key

        # Path-Style: domain.com/bucket/path/file.ext
        path_parts = path.split("/", 1) if path else ["", ""]

        if len(path_parts) >= 2 and self._is_bucket_name(path_parts[0]):
            bucket = path_parts[0]
            object_key = path_parts[1] if len(path_parts) > 1 else ""
            return bucket, object_key

        # 如果无法明确解析，使用启发式方法
        # 优先尝试Virtual Hosted-Style
        if len(hostname_parts) >= 2:
            bucket = hostname_parts[0]
            object_key = path
            logger.warning(
                f"使用启发式解析 Virtual Hosted-Style: bucket={bucket}, key={object_key}"
            )
            return bucket, object_key

        # 最后尝试Path-Style
        if path_parts and path_parts[0]:
            bucket = path_parts[0]
            object_key = path_parts[1] if len(path_parts) > 1 else ""
            logger.warning(
                f"使用启发式解析 Path-Style: bucket={bucket}, key={object_key}"
            )
            return bucket, object_key

        raise ValueError(
            f"无法解析URL: {url}。请确保URL遵循 Virtual Hosted-Style (bucket.domain.com/file) 或 Path-Style (domain.com/bucket/file) 格式"
        )

    def _is_bucket_name(self, name: str) -> bool:
        """
        判断是否是有效的bucket名称
        基于S3命名规则的简化版本
        """
        if not name or len(name) < 3 or len(name) > 63:
            return False

        # 基本规则：小写字母、数字、连字符
        if not re.match(r"^[a-z0-9\-]+$", name):
            return False

        # 不能以连字符开头或结尾
        if name.startswith("-") or name.endswith("-"):
            return False

        # 不能包含连续的连字符
        if "--" in name:
            return False

        return True

    def build_storage_url(self, bucket: str, object_key: str) -> str:
        """
        通用对象存储URL构建器
        根据配置的endpoint自动选择合适的URL格式
        """
        protocol = "https" if self.s3_secure else "http"

        # 检测当前配置的endpoint类型
        if self._should_use_virtual_hosted_style():
            # Virtual Hosted-Style: bucket.endpoint/object_key
            return f"{protocol}://{bucket}.{self.s3_endpoint}/{object_key}"
        else:
            # Path-Style: endpoint/bucket/object_key
            return f"{protocol}://{self.s3_endpoint}/{bucket}/{object_key}"

    def _should_use_virtual_hosted_style(self) -> bool:
        """
        判断是否应该使用Virtual Hosted-Style
        基于endpoint的特征进行判断
        """
        # 如果endpoint包含已知的云服务域名，使用Virtual Hosted-Style
        virtual_hosted_domains = [
            "aliyuncs.com",
            "amazonaws.com",
            "myqcloud.com",
            "myhuaweicloud.com",
            "bcebos.com",
        ]

        for domain in virtual_hosted_domains:
            if domain in self.s3_endpoint:
                return True

        # 提取hostname部分（去除端口）
        hostname = self.s3_endpoint.split(':')[0]
        
        # 如果是IP地址，一律使用Path-Style
        if self._is_ip_address(hostname):
            return False

        # 如果endpoint看起来像是自定义域名（包含多个点），使用Virtual Hosted-Style
        if self.s3_endpoint.count(".") >= 2:
            return True

        # 默认使用Path-Style（MinIO等自托管服务）
        return False

    def ensure_bucket_exists(self, bucket: str):
        """确保指定桶存在"""
        if not self.client.bucket_exists(bucket):
            try:
                self.client.make_bucket(bucket, location=self.s3_region)
                logger.info(f"创建桶: {bucket}")
            except Exception as e:
                logger.warning(f"创建桶失败 {bucket}: {e} (可能桶已存在)")

    def download_file_from_url(self, url: str, local_path: str):
        """从对象存储URL下载文件"""
        try:
            bucket, object_key = self.parse_object_storage_url(url)

            # 创建目录
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            logger.info(f"开始下载: {url} -> bucket={bucket}, key={object_key}")
            self.client.fget_object(bucket, object_key, local_path)
            logger.info(f"下载成功: {url} -> {local_path}")

        except S3Error as e:
            logger.error(f"S3下载失败: {e}")
            raise HTTPException(status_code=404, detail=f"文件未找到: {url}")
        except ValueError as e:
            logger.error(f"URL解析失败: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"下载失败: {e}")
            raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")

    def upload_file_to_bucket(
        self, local_path: str, bucket: str, object_key: str
    ) -> str:
        """上传文件到指定的bucket和object key，返回对象存储URL"""
        try:
            # 确保桶存在
            self.ensure_bucket_exists(bucket)

            # 上传文件
            self.client.fput_object(bucket, object_key, local_path)
            logger.info(f"上传成功: {local_path} -> {bucket}/{object_key}")

            # 构建返回URL
            return self.build_storage_url(bucket, object_key)

        except S3Error as e:
            logger.error(f"上传失败: {e}")
            raise HTTPException(status_code=500, detail=f"上传失败: {e}")
        except Exception as e:
            logger.error(f"上传失败: {e}")
            raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")

    # 保留向后兼容的方法
    def build_s3_url(self, bucket: str, key: str) -> str:
        """构建对象存储URL（保持向后兼容）"""
        return self.build_storage_url(bucket, key)

    def upload_file_to_s3_url(self, local_path: str, s3_url: str):
        """上传文件到指定的对象存储URL（保持向后兼容）"""
        bucket, object_key = self.parse_object_storage_url(s3_url)
        self.upload_file_to_bucket(local_path, bucket, object_key)

    def upload_file(self, bucket: str, object_key: str, local_path: str):
        """上传文件到S3兼容存储（保持向后兼容）"""
        self.upload_file_to_bucket(local_path, bucket, object_key)


# 全局存储管理器实例
storage_manager = None


def get_storage_manager():
    """获取存储管理器实例"""
    global storage_manager
    if storage_manager is None:
        storage_manager = StorageManager()
    return storage_manager
