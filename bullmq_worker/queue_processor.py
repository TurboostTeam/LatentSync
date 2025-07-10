import asyncio
from datetime import datetime
import os
import tempfile

from bullmq_worker.storage.storage_manager import StorageFactory
from bullmq_worker.utils.config import config
from bullmq_worker.utils.logging import logger


class QueueProcessor:
    """队列处理器"""
    def __init__(self):
        self.storage_client = StorageFactory().client
    
    async def _download_input_files(self, s3_url: str, local_path: str):
        """下载输入文件"""
        bucket, object_key = self.storage_client.parse_url(s3_url)
        self.storage_client.download_file(object_key, local_path)

        return object_key

    async def _upload_result(self, input_video_url: str, output_video_local_path: str) -> str:
        # 从输入视频URL中解析bucket和object key信息
        input_video_bucket, input_video_object_key = self.storage_client.parse_url(input_video_url)

        # 构建输出视频的object key
        # 从视频object key中提取目录路径
        target_video_dir = os.path.dirname(input_video_object_key)

        # 从原视频文件名中提取基础名称（去掉扩展名）
        input_video_basename = os.path.splitext(os.path.basename(input_video_object_key))[0]  # 去掉扩展名

        # 生成输出文件的object key，放在与输入文件相同的目录下
        target_video_name = f"{input_video_basename}_latentsync_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        output_object_key = os.path.join(target_video_dir, target_video_name)

        # 上传输出视频
        logger.info(f"开始上传输出视频: {output_video_local_path} -> {output_object_key}")
        output_url = self.storage_client.upload_file(
            object_key=output_object_key,
            local_path=output_video_local_path
        )

        return output_url

    async def _run_inference_subprocess(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
        temp_dir: str,
    ):
        """使用子进程运行推理"""
        logger.info(f"🔄 开始执行唇形同步...")

        # 构建命令行参数
        cmd = [
            "python3",
            "-m",
            "scripts.inference",
            "--unet_config_path",
            config.MODEL_CONFIG_PATH,
            "--inference_ckpt_path",
            config.MODEL_CHECKPOINT_PATH,
            "--inference_steps",
            "20",
            "--guidance_scale",
            "1.5",
            "--video_path",
            video_path,
            "--audio_path",
            audio_path,
            "--video_out_path",
            output_path,
            "--temp_dir",
            os.path.join(temp_dir, "temp"),
            "--enable_deepcache",
        ]

        # 使用固定的参数，完全按照inference.sh配置
        # inference_steps: 20
        # guidance_scale: 1.5
        # enable_deepcache: 启用
        # seed: 使用默认值0（不设置）

        logger.info(f"执行命令: {' '.join(cmd)}")

        # 运行子进程
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.getcwd(),
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = f"推理进程失败，返回码: {process.returncode}\n标准错误: {stderr.decode()}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info(f"推理完成，标准输出: {stdout.decode()}")

    async def process_task(self, video_url, audio_url):
        """处理视频和音频，实现唇形同步，并返回处理后的视频URL"""
        
        # 创建临时目录 tmp，仅在任务处理期间存在
        with tempfile.TemporaryDirectory() as temp_dir:
            # 准备文件路径
            video_path = os.path.join(temp_dir, "input_video.mp4")
            audio_path = os.path.join(temp_dir, "input_audio.wav")
            output_path = os.path.join(temp_dir, "output_video.mp4")

            # 下载输入文件
            logger.info(f"🔄 开始下载视频: {video_url}")
            await self._download_input_files(video_url, video_path)
            logger.info(f"🔄 开始下载音频: {audio_url}")
            await self._download_input_files(audio_url, audio_path)

            # 使用子进程调用推理脚本
            await self._run_inference_subprocess(
                video_path, audio_path, output_path, temp_dir
            )

            # 上传结果
            output_s3_url = await self._upload_result(video_url, output_path)
            
            return output_s3_url







        