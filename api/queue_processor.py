import asyncio
import logging
import os
import signal
import subprocess
import tempfile
from datetime import datetime
from typing import Dict, Optional

from .models import LipSyncRequest
from .storage import get_storage_manager
from .task_manager import get_task_manager

logger = logging.getLogger(__name__)


class QueueProcessor:
    def __init__(self):
        self.storage_manager = get_storage_manager()
        self.task_manager = get_task_manager()
        self.task_queue = asyncio.Queue()
        self.running_processes: Dict[str, asyncio.subprocess.Process] = {}
        self.process_locks: Dict[str, asyncio.Lock] = {}  # 添加进程锁
        self.is_processing = False
        self.current_task = None
        self._processing_task = None

    async def add_task(self, task_id: str, request: LipSyncRequest):
        """将任务添加到队列"""
        await self.task_queue.put((task_id, request))
        logger.info(
            f"任务 {task_id} 已添加到队列，当前队列大小: {self.task_queue.qsize()}"
        )

    async def start_processing(self):
        """启动队列处理（只允许单例）"""
        if self._processing_task is None:
            self._processing_task = asyncio.create_task(self._process_queue())
            logger.info("队列处理器已启动")

    async def cancel_task(self, task_id: str) -> bool:
        """取消并中断指定任务"""
        # 获取或创建任务锁
        if task_id not in self.process_locks:
            self.process_locks[task_id] = asyncio.Lock()

        async with self.process_locks[task_id]:
            try:
                # 检查任务是否在运行中
                if task_id in self.running_processes:
                    process = self.running_processes[task_id]
                    logger.info(f"正在中断任务 {task_id} 的进程 (PID: {process.pid})")

                    # 尝试优雅终止
                    try:
                        if process.returncode is None:  # 进程仍在运行
                            process.terminate()
                            await asyncio.wait_for(process.wait(), timeout=10.0)
                            logger.info(f"任务 {task_id} 进程已优雅终止")
                        else:
                            logger.info(
                                f"任务 {task_id} 进程已经结束 (返回码: {process.returncode})"
                            )
                    except asyncio.TimeoutError:
                        # 强制杀掉进程
                        if process.returncode is None:
                            logger.warning(
                                f"任务 {task_id} 进程无法优雅终止，使用强制终止"
                            )
                            process.kill()
                            await process.wait()
                            logger.info(f"任务 {task_id} 进程已强制终止")

                    # 从跟踪字典中移除
                    if task_id in self.running_processes:
                        del self.running_processes[task_id]

                    # 更新任务状态
                    self.task_manager.update_task_status(
                        task_id, "cancelled", "任务已被用户取消"
                    )

                    return True
                else:
                    # 任务可能在队列中等待，更新状态即可
                    task_data = self.task_manager.get_task_status_data(task_id)
                    if task_data and task_data.get("status") == "pending":
                        self.task_manager.update_task_status(
                            task_id, "cancelled", "任务已被用户取消"
                        )
                        logger.info(f"队列中的任务 {task_id} 已标记为取消")
                        return True

                    # 任务不存在或已完成
                    task_status = task_data.get("status") if task_data else "不存在"
                    logger.info(f"任务 {task_id} 当前状态为 {task_status}，无需取消")
                    return False

            except KeyError as e:
                # 任务ID不存在的情况，这是预期的
                logger.info(f"任务 {task_id} 不在运行进程列表中，可能已经完成或取消")
                return False
            except Exception as e:
                # 只有真正意外的错误才记录为ERROR
                logger.error(
                    f"取消任务 {task_id} 时发生意外错误: {type(e).__name__}: {e}"
                )
                return False
            finally:
                # 清理锁
                if task_id in self.process_locks:
                    del self.process_locks[task_id]

    async def _process_queue(self):
        """处理队列中的任务（串行处理，确保并发量=1）"""
        while True:
            try:
                # 获取下一个任务（如果队列为空则等待）
                task_id, request = await self.task_queue.get()

                # 检查任务是否已被取消
                task_data = self.task_manager.get_task_status_data(task_id)
                if task_data and task_data.get("status") == "cancelled":
                    logger.info(f"跳过已取消的任务 {task_id}")
                    self.task_queue.task_done()
                    continue

                self.is_processing = True
                self.current_task = task_id
                logger.info(f"开始处理任务 {task_id}")

                # 使用子进程处理任务
                await self._process_task_with_subprocess(task_id, request)

                # 标记任务完成
                self.task_queue.task_done()
                self.is_processing = False
                self.current_task = None

            except Exception as e:
                logger.error(f"队列处理出错: {e}")
                self.is_processing = False
                self.current_task = None

    async def _process_task_with_subprocess(
        self, task_id: str, request: LipSyncRequest
    ):
        """使用子进程处理单个任务"""
        try:
            # 更新任务状态
            self.task_manager.update_task_status(
                task_id, "processing", "正在处理唇形同步..."
            )

            # 创建临时目录 tmp，仅在任务处理期间存在
            with tempfile.TemporaryDirectory() as temp_dir:
                # 准备文件路径
                video_path = os.path.join(temp_dir, "input_video.mp4")
                audio_path = os.path.join(temp_dir, "input_audio.wav")
                output_path = os.path.join(temp_dir, "output_video.mp4")

                # 下载输入文件
                await self._download_input_files(
                    task_id, request, video_path, audio_path
                )

                # 使用子进程调用推理脚本
                await self._run_inference_subprocess(
                    task_id, request, video_path, audio_path, output_path, temp_dir
                )

                # 上传结果
                output_s3_url = await self._upload_result(task_id, request, output_path)

                # 更新任务状态
                self.task_manager.update_task_status(
                    task_id, "completed", "唇形同步完成", output_s3_url=output_s3_url
                )

                logger.info(f"任务 {task_id} 完成")

        except Exception as e:
            # 检查任务是否已被标记为取消
            task_data = self.task_manager.get_task_status_data(task_id)

            if task_data and task_data.get("status") == "cancelled":
                # 任务被取消是预期的，不记录为错误
                logger.info(f"任务 {task_id} 已被取消")
            else:
                # 检查是否是进程被终止的情况
                if "返回码: -15" in str(e) or "返回码: -2" in str(e):
                    # SIGTERM (-15) 或 SIGINT (-2) 是预期的终止信号
                    logger.info(f"任务 {task_id} 进程被正常终止: {str(e)}")
                else:
                    # 其他错误才记录为ERROR
                    logger.error(f"任务 {task_id} 失败: {str(e)}")

                # 安全地清理进程记录
                await self._safe_cleanup_process(task_id)

                # 只有在任务未被取消的情况下才标记为失败
                if task_data and task_data.get("status") != "cancelled":
                    self.task_manager.update_task_status(
                        task_id, "failed", f"处理失败: {str(e)}"
                    )

    async def _download_input_files(
        self, task_id: str, request: LipSyncRequest, video_path: str, audio_path: str
    ):
        """下载输入文件"""
        self.task_manager.update_task_status(
            task_id, "processing", "正在下载输入文件..."
        )

        # 使用asyncio.to_thread将同步操作转为异步，支持MinIO和阿里云OSS
        await asyncio.to_thread(
            self.storage_manager.download_file_from_url,
            request.video_url,
            video_path,
        )
        await asyncio.to_thread(
            self.storage_manager.download_file_from_url,
            request.audio_url,
            audio_path,
        )

    async def _run_inference_subprocess(
        self,
        task_id: str,
        request: LipSyncRequest,
        video_path: str,
        audio_path: str,
        output_path: str,
        temp_dir: str,
    ):
        """使用子进程运行推理"""
        self.task_manager.update_task_status(
            task_id, "processing", "正在执行唇形同步..."
        )

        # 构建命令行参数
        cmd = [
            "python3",
            "-m",
            "scripts.inference",
            "--unet_config_path",
            "configs/unet/stage2_512.yaml",
            "--inference_ckpt_path",
            "checkpoints/latentsync_unet.pt",
            "--inference_steps",
            "20",
            "--guidance_scale",
            "1.5",
            "--enable_deepcache",
            "--video_path",
            video_path,
            "--audio_path",
            audio_path,
            "--video_out_path",
            output_path,
            "--temp_dir",
            os.path.join(temp_dir, "temp"),
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

        # 获取或创建任务锁
        if task_id not in self.process_locks:
            self.process_locks[task_id] = asyncio.Lock()

        # 线程安全地将进程添加到跟踪字典
        async with self.process_locks[task_id]:
            self.running_processes[task_id] = process
            logger.info(f"任务 {task_id} 进程已启动 (PID: {process.pid})")

        try:
            stdout, stderr = await process.communicate()

            # 检查进程是否被外部终止
            if process.returncode == -15:  # SIGTERM
                raise RuntimeError(f"推理进程被终止，返回码: {process.returncode}")
            elif process.returncode == -2:  # SIGINT
                raise RuntimeError(f"推理进程被中断，返回码: {process.returncode}")
            elif process.returncode != 0:
                error_msg = f"推理进程失败，返回码: {process.returncode}\n标准错误: {stderr.decode()}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            logger.info(f"推理完成，标准输出: {stdout.decode()}")

        finally:
            # 安全地从跟踪字典中移除进程
            await self._safe_cleanup_process(task_id)

    async def _upload_result(
        self, task_id: str, request: LipSyncRequest, output_path: str
    ) -> str:
        """上传结果文件"""
        # 从输入视频URL中解析bucket和object key信息
        video_bucket, video_object_key = self.storage_manager.parse_object_storage_url(
            request.video_url
        )

        # 从视频object key中提取目录路径
        video_dir = ""
        if "/" in video_object_key:
            # 获取文件所在的目录路径
            video_dir = "/".join(video_object_key.split("/")[:-1]) + "/"

        # 从原视频文件名中提取基础名称（去掉扩展名）
        video_filename = video_object_key.split("/")[-1]  # 获取文件名部分
        video_basename = os.path.splitext(video_filename)[0]  # 去掉扩展名

        # 生成输出文件的object key，放在与输入文件相同的目录下
        output_key = f"{video_dir}{video_basename}_lip_sync_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"

        self.task_manager.update_task_status(task_id, "processing", "正在上传结果...")

        # 使用asyncio.to_thread将同步操作转为异步
        output_url = await asyncio.to_thread(
            self.storage_manager.upload_file_to_bucket,
            output_path,
            video_bucket,
            output_key,
        )

        return output_url

    async def _safe_cleanup_process(self, task_id: str):
        """安全地清理进程记录，避免竞争条件"""
        # 获取或创建任务锁
        if task_id not in self.process_locks:
            self.process_locks[task_id] = asyncio.Lock()

        try:
            async with self.process_locks[task_id]:
                if task_id in self.running_processes:
                    del self.running_processes[task_id]
                    logger.debug(f"任务 {task_id} 进程记录已清理")
        except Exception as e:
            logger.debug(f"清理任务 {task_id} 进程记录时发生错误: {e}")
        finally:
            # 清理锁
            if task_id in self.process_locks:
                del self.process_locks[task_id]

    def get_queue_status(self):
        """获取队列状态"""
        return {
            "queue_size": self.task_queue.qsize(),
            "is_processing": self.is_processing,
            "current_task": self.current_task,
            "running_processes": list(self.running_processes.keys()),
        }


# 全局队列处理器实例
queue_processor = None


def get_queue_processor():
    """获取队列处理器实例"""
    global queue_processor
    if queue_processor is None:
        queue_processor = QueueProcessor()
    return queue_processor
