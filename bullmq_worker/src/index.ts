/**
 * Worker服务主入口文件
 */

import { Worker } from 'bullmq';
import { createWorker, gracefulShutdown } from './worker';
import logger from './utils/logger';


async function main(): Promise<void> {
	let worker: Worker | null = null;
	let isShuttingDown = false; // 防止重复关闭
	
	// 优雅关闭处理函数
	const handleShutdown = async (signal: string) => {
		if (isShuttingDown) {
			logger.warn(`🚨 收到${signal}信号，但关闭流程已在进行中，忽略此次信号`);
			return;
		}
		
		isShuttingDown = true;
		logger.info(`🛑 接收到${signal}信号，开始优雅关闭...`);
		
		if (worker) {
			await gracefulShutdown(worker);
		}
		
		logger.info('👋 Worker服务已关闭');
		process.exit(0); // 以成功状态码退出
	};
	
	try {
		logger.info('🚀 正在启动Worker服务...');
		worker = await createWorker();
		
		// 注册SIGINT信号处理器 (通常是Ctrl+C)
		// 当用户按下Ctrl+C时，会触发优雅关闭流程
		process.on('SIGINT', () => handleShutdown('SIGINT'));
		
		// 注册SIGTERM信号处理器 (终止信号)
		// 通常由进程管理器（如PM2、Docker、Kubernetes）发送
		process.on('SIGTERM', () => handleShutdown('SIGTERM'));
		
		// Worker启动成功，记录运行状态
		// 此时服务已经开始监听队列并处理任务
		logger.info('🚀 Worker服务启动成功，正在监听任务队列...');
		logger.info('👉 按 Ctrl+C 可优雅停止服务');
		
	} catch (e) {
		// 捕获启动过程中的所有异常
		// 这可能包括：Redis连接失败、Python环境不可用、配置错误等
		logger.error('🚨 Worker启动失败', { 
			error: e instanceof Error ? e.message : String(e),
			stack: e instanceof Error ? e.stack : undefined
		});
		
		// 以错误状态码退出，通知外部系统启动失败
		// 状态码1表示一般性错误
		process.exit(1);
	}
}


if (require.main === module) {
	// 启动主函数
	main();
}


