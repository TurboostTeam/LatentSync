import asyncio
import signal
from bullmq import Worker

from bullmq_worker.utils.config import config
from bullmq_worker.utils.logging import logger
from bullmq_worker.queue_processor import QueueProcessor

queue_processor = QueueProcessor()

async def process(job, job_token):
    """处理唇形同步任务"""
    job_id = job.id
    logger.info(f"------ 开始处理唇形同步任务，job_id={job_id} ------")
    
    try:
        # 从任务数据中获取数据
        data = job.data
        video_url = data["video_url"]
        audio_url = data["audio_url"]
        
        # 处理任务（处理时间根据视频长度而定）
        output_video_url = await queue_processor.process_task(video_url, audio_url)

        logger.info(f"✅ 唇形同步任务处理完成：job_id={job_id}, output_video_url={output_video_url}")

        # 返回结果
        return output_video_url

    except Exception as e:
        logger.error(f"❌ 处理唇形同步任务时发生错误 job_id={job_id}: {e}")
        raise


async def main():
    """主函数"""
    # 创建一个关闭事件
    shutdown_event = asyncio.Event()

    def signal_handler(signum, frame):
        logger.info("🛑 接收到关闭信号，正在关闭...")
        shutdown_event.set()

    # 注册信号处理器
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    worker = None
    try:
        # 从环境变量构建Redis连接字符串
        redis_host = config.REDIS_HOST
        redis_port = config.REDIS_PORT
        redis_password = config.REDIS_PASSWORD
        redis_db = config.REDIS_DB
        redis_ssl = config.REDIS_SSL

        # 构建Redis连接字符串
        if redis_ssl:
            redis_url = (
                f"rediss://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
            )
        else:
            redis_url = (
                f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
            )

        logger.info(
            f"🔗 连接到Redis: {redis_host}:{redis_port} (SSL: {redis_ssl}, DB: {redis_db})"
        )

        # 创建Worker，处理指定队列的任务
        # 针对长时间任务的优化配置，时间单位为毫秒
        worker = Worker(
            config.QUEUE_NAME, 
            process, 
            {
                "connection": redis_url,
                "lockDuration": 3600000,  # 任务被锁定的最大时间（防止其他 Worker 重复处理同一任务，任务完成后立即释放，不需要等待）
                "lockRenewTime": 300000,  # 定期更新锁
                "stalledInterval": 60000,  # 60秒检查一次 stalled 任务，将停滞任务重新放回队列
                "maxStalledCount": 1,     # 最大 stalled 次数设为1，避免重复处理
                "concurrency": 1,         # 单任务并发，避免资源竞争
                "drainDelay": 5000,       # 5秒轮询间隔
            }
        )

        logger.info("🚀 BullMQ 唇形同步任务处理器已启动")
        logger.info(f"📊 监听的队列名称: {config.QUEUE_NAME}")
        logger.info("⏳ 等待唇形同步任务...")

        # 等待关闭事件
        await shutdown_event.wait()

    except Exception as e:
        logger.error(f"❌ 启动唇形同步任务处理器时发生错误: {e}")
        raise
    finally:
        # 关闭worker
        if worker:
            logger.info("🔉 正在关闭worker...")
            await worker.close()
            logger.info("✅ Worker已成功关闭\n\n")


if __name__ == "__main__":
    asyncio.run(main())
