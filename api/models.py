import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, validator


class LipSyncRequest(BaseModel):
    video_url: str  # 视频文件URL，支持各种对象存储格式
    audio_url: str  # 音频文件URL，支持各种对象存储格式

    @validator("video_url", "audio_url")
    def validate_url(cls, v):
        # 检查是否为HTTP/HTTPS URL
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("URL必须以 http:// 或 https:// 开头")

        # 通用的URL格式验证：确保有效的域名和文件扩展名
        url_pattern = (
            r"^https?://[^\s/$.?#].[^\s]*\.(mp4|wav|mp3|m4a|webm|avi|mov)(\?.*)?$"
        )

        if not re.match(url_pattern, v, re.IGNORECASE):
            raise ValueError(
                "URL格式不正确，必须是有效的音视频文件URL (支持格式: mp4, wav, mp3, m4a, webm, avi, mov)"
            )

        return v


class LipSyncResponse(BaseModel):
    task_id: str
    status: str
    message: str
    output_s3_url: Optional[str] = None


class TaskStatus(BaseModel):
    task_id: str
    status: str
    message: str
    output_s3_url: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
