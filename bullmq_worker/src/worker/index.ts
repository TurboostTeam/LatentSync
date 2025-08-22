/**
 * Worker核心逻辑模块
 */

import { Worker, Job, Queue } from 'bullmq';
import { redisConnection, queueConfig } from '../config';
import logger from '../utils/logger';
import { QueueProcessor } from './queue-processor';

/**
 * 任务输入数据类型定义
 */
export type TaskData = { video_url: string; audio_url: string };

/**
 * 任务返回结果类型定义
 */
export type TaskResult = string;

const queueProcessor = new QueueProcessor();

/**
 * 记录当前队列状态的辅助函数
 */
async function logQueueStatus(): Promise<void> {
	try {
		// 创建Queue实例以获取状态信息
		const queue = new Queue(queueConfig.name, { connection: redisConnection });
		
		// 检查队列中是否有任务（包括等待、活动、延迟、停滞等状态的任务）
		const [waitingJobs, activeJobs, delayedJobs, prioritizedJobs] = await Promise.all([
			queue.getWaiting(),
			queue.getActive(),
			queue.getDelayed(),
			queue.getPrioritized(),
		]);
		
		const waitingCount = waitingJobs.length;
		const activeCount = activeJobs.length;
		const delayedCount = delayedJobs.length;
		const prioritizedCount = prioritizedJobs.length;
		
		const totalPending = waitingCount + activeCount + delayedCount + prioritizedCount;
		
		if (totalPending === 0) {
			logger.info('📋 队列状态: 全部任务已处理完毕');
		} else {
			logger.info('📋 队列状态', {
				waiting: waitingCount,
				active: activeCount,
				delayed: delayedCount,
				prioritized: prioritizedCount,
				totalPending
			});
		}
		
		await queue.close();
	} catch (error) {
		logger.error('❌ 获取队列状态失败', {
			error: error instanceof Error ? error.message : String(error)
		});
	}
}


// 处理单个任务的核心函数
async function processTask(job: Job<TaskData>): Promise<string> {
	const startTime = Date.now();
	
	logger.info(`🔄 --- 开始处理唇形同步任务，任务ID: ${job.id} ---`);
	
	try {
		const { video_url: videoUrl, audio_url: audioUrl } = job.data;

		// 更新进度：开始处理
		await job.updateProgress(1);

		const output_video_url = await queueProcessor.processTask(videoUrl, audioUrl, async (progressPercentage: number, message: string) => {
			// QueueProcessor已经将进度映射到了合适的范围，直接使用
			const actualProgress = Math.round(progressPercentage);
			await job.updateProgress(actualProgress);
			
			logger.info(`📊 任务进度更新: ${actualProgress}% - ${message}`);
		});
		
		const totalTimeMinutes = parseFloat(((Date.now() - startTime) / 1000 / 60).toFixed(2));
		
		logger.info(`🎉 任务处理完成`, { 
			jobId: job.id,
			outputVideoUrl: output_video_url,
			totalProcessingTimeMinutes: totalTimeMinutes,
		});

		// 最终完成，进度更新到100%
		await job.updateProgress(100);
		logger.info(`📊 任务进度更新: 100%`);
		
		return output_video_url;
		
	} catch (error) {
		// 任务处理失败，记录详细的错误信息
		const errorMessage = error instanceof Error ? error.message : String(error);
		
		logger.error(`❌ 任务处理失败`, { 
			jobId: job.id,
			error: errorMessage,
			processingTimeMinutes: parseFloat(((Date.now() - startTime) / 1000 / 60).toFixed(2))
		});
		
		// 重新抛出异常，让BullMQ处理重试逻辑
		throw error;
	}
}

// 创建并配置Worker实例
export async function createWorker(): Promise<Worker> {
	// 创建BullMQ Worker实例
	logger.info('🔨 创建Worker实例...');
	
	const worker = new Worker<TaskData, TaskResult>(
		queueConfig.name,
		processTask,
		{
			// Redis连接配置
			connection: redisConnection,
			
			// 并发处理任务数量
			concurrency: queueConfig.concurrency,

			// 任务被锁定的最大时间
			// 防止其他 Worker 重复处理同一任务，任务完成后立即释放，不需要等待
			lockDuration: 5 * 60 * 1000,

			// 定期更新锁，将锁的有效期重置为 lockDuration
            lockRenewTime: 2 * 60 * 1000,

			//检查停滞任务的间隔时间（毫秒）
			// 30秒检查一次，将停滞任务重新放回队列
			stalledInterval: 30000,

			// 最大停滞次数
			// 超过这个次数的任务会被标记为失败
			maxStalledCount: 1,

			// 自动开始处理任务
			autorun: true,
		}
	);
	
	// 注册任务失败事件监听器 - 记录最终失败状态
	worker.on('failed', (job: Job<TaskData> | undefined, err: Error) => {
		// 仅在重试次数达到上限时记录，避免与processTask中的错误日志重复
		if (job && job.attemptsMade >= (job.opts?.attempts || 1)) {
			logger.error('❌ 任务最终失败', { 
				jobId: job.id,
				attemptsMade: job.attemptsMade,
				maxAttempts: job.opts?.attempts || 1,
				failedReason: job?.failedReason
			});
		}
	});
	
	// 注册Worker错误事件监听器 - 捕获系统级错误
	worker.on('error', (err: Error) => {
		logger.error('❌ Worker系统错误', { 
			error: err.message,
			stack: err.stack,
			timestamp: new Date().toISOString()
		});
	});
	
	// 注册Worker停滞任务事件监听器 - 检测长时间无进度的任务
	worker.on('stalled', (jobId: string) => {
		logger.warn('⚠️ 检测到停滞任务，即将重试', { 
			jobId,
		});
	});

	// 注册任务完成事件监听器 - 任务成功完成时触发
	// worker.on('completed', async () => {
	// 	// 任务完成后检查队列状态是否为空
	// 	await logQueueStatus();
	// });

	// 注册Worker空闲事件监听器 - 当没有更多任务需要处理时触发
	worker.on('drained', async () => {
		logger.info('🏁 Worker空闲，检查队列状态');

		await logQueueStatus();
	});
	
	// 记录Worker启动成功日志
	logger.info('✅ Worker创建成功', { 
		queueName: queueConfig.name,
		concurrency: queueConfig.concurrency,
		processId: process.pid,
	});
	
	return worker;
}

// 优雅关闭Worker
export async function gracefulShutdown(worker: Worker): Promise<void> {
	logger.info('🔉 开始执行Worker优雅关闭流程...');
	
	try {
		// 检查Worker是否已经关闭
		if (worker.isRunning()) {
			logger.info('🔉 暂停Worker，停止接受新任务...');
			await worker.pause();
			
			logger.info('🔉 等待当前任务完成并关闭连接...');
			await worker.close();
		} else {
			logger.info('🔉 Worker已经关闭，跳过关闭步骤');
		}
		
		logger.info('✅ Worker优雅关闭完成');
		
	} catch (error) {
		// 记录关闭过程中的错误，但不重新抛出
		// 因为在关闭过程中，我们希望尽最大努力清理资源
		const errorMessage = error instanceof Error ? error.message : String(error);
		
		// 特殊处理预期的连接关闭错误
		if (errorMessage.includes('Connection is closed') || errorMessage.includes('Redis connection is closed')) {
			logger.info('连接已经关闭，Worker关闭流程完成');
		} else {
			logger.error('Worker关闭过程中发生非预期错误', { 
				error: errorMessage
			});
		}
	}
}


