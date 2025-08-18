/**
 * Worker核心逻辑模块
 */

import { Worker, Job } from 'bullmq';
import os from 'os';
import { redisConnection, queueConfig } from '../config';
import logger from '../utils/logger';
import { executePythonScript, validatePythonEnvironment, TaskData, TaskResult } from '../utils/pythonExecutor';

// 处理单个任务的核心函数
async function processTask(job: Job<TaskData>): Promise<TaskResult> {
	const startTime = Date.now();
	
	logger.info(`🔄 开始处理唇形同步任务`, { 
		jobId: job.id, 
		data: job.data 
	});
	
	try {
		const result = await executePythonScript(job.data);
		
		// 更新任务进度到90%：Python脚本执行完成，准备返回结果
		await job.updateProgress(90);
		
		const totalTimeMinutes = parseFloat(((Date.now() - startTime) / 1000 / 60).toFixed(2));
		
		logger.info(`✅ 任务处理完成`, { 
			jobId: job.id,
			totalProcessingTimeMinutes: totalTimeMinutes,
		});
		
		// 在结果中添加Worker信息和总处理时间
		return { 
			...result, 
			total_processing_time_minutes: totalTimeMinutes 
		} as TaskResult;
		
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
	// 验证Python运行环境
	logger.info('🔍 验证Python运行环境...');
	const isPythonAvailable = await validatePythonEnvironment();
	
	if (!isPythonAvailable) {
		throw new Error('Python环境不可用，请检查Python安装和配置');
	}
	
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
			
			// 自动开始处理任务
			autorun: true,
			
			// 检查停滞任务的间隔时间（毫秒）
			// 停滞任务是指长时间没有更新进度的任务
			stalledInterval: 60000, // 1分钟
			
			// 最大停滞次数
			// 超过这个次数的任务会被标记为失败
			maxStalledCount: 1,
		}
	);
	
	// 注册任务失败事件监听器 - 记录最终失败状态
	worker.on('failed', (job, err) => {
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
	worker.on('error', (err) => {
		logger.error('❌ Worker系统错误', { 
			error: err.message,
			stack: err.stack,
			timestamp: new Date().toISOString()
		});
	});
	
	// 注册Worker停滞任务事件监听器 - 检测长时间无进度的任务
	worker.on('stalled', (jobId) => {
		logger.warn('⚠️ 检测到停滞任务', { 
			jobId,
			message: '任务可能由于Worker崩溃或网络问题而停滞'
		});
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


