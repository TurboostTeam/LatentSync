from typing import Tuple


class BaseStorageClient:
    """存储客户端基类"""

    def __init__(self, endpoint: str, access_key: str, secret_key: str, region: str, bucket_name: str):
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.bucket_name = bucket_name

    def _ensure_bucket_exists(self):
        """确保存储桶存在"""
        raise NotImplementedError
    
    def download_file(self, object_key: str, local_path: str):
        """从存储桶下载文件"""
        raise NotImplementedError

    def upload_file(self, object_key: str, local_path: str) -> str:
        """上传文件到存储桶"""
        raise NotImplementedError

    def build_url(self, object_key: str, signer_url_expire_hours: int = 24) -> str:
        """构建存储桶URL"""
        raise NotImplementedError

    def parse_url(self, url: str) -> Tuple[str, str]:
        """解析URL"""
        raise NotImplementedError