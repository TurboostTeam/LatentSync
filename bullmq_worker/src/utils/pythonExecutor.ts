/**
 * Python脚本执行器模块
 */

import { spawn } from 'child_process';
import path from 'path';
import logger from './logger';

/**
 * 任务输入数据类型定义
 */
export type TaskData = { video_url: string; audio_url: string };

/**
 * 任务输出数据类型定义
 */
export interface TaskResult {
	success: boolean;
	output_video_url?: string;
	error?: string;
	inference_time_minutes?: number;
	total_processing_time_minutes?: number;
}

/**
 * 执行Python脚本并获取处理结果
 */
export async function executePythonScript(taskData: TaskData): Promise<TaskResult> {
	return new Promise((resolve, reject) => {
		const startTime = Date.now();

		const moduleName = "scripts.inference";
		
		logger.info(`🔄 开始执行Python模块: ${moduleName}`);
		
		// 构建命令行参数数组，使用-m参数执行模块
		const args = [
			'-m', moduleName,
			'--unet_config_path', "configs/unet/stage2_512.yaml",
			"--inference_ckpt_path", "checkpoints/latentsync_unet.pt",
			"--inference_steps", "20",
            "--guidance_scale", "1.5",
			'--video_path', "assets/demo1_video.mp4",
			'--audio_path', "assets/demo1_audio.wav",
			"--video_out_path", "video_out.mp4",
            "--temp_dir", "temp",
            "--enable_deepcache",
		];
		
		// 启动Python子进程，使用-m参数执行模块
		const pythonProcess = spawn('python', args, { 
			cwd: "../", 		// 设置工作目录为项目根目录
			env: process.env    // 继承当前进程的环境变量
		});
		
		// 初始化数据收集变量
		let outputData = '';
		let errorData = '';
		
		// 监听Python脚本的标准输出
		// data事件会多次触发，需要累积所有数据
		pythonProcess.stdout.on('data', (data) => {
			outputData += data.toString();
		});
		
		// 监听Python脚本的标准错误输出
		// 用于收集Python脚本的错误信息和日志
		pythonProcess.stderr.on('data', (data) => {
			errorData += data.toString();
		});
		
		// 监听子进程结束事件
		pythonProcess.on('close', (code) => {
			// 检查退出码，非零表示执行失败
			if (code !== 0) {
				logger.error('❌ Python脚本执行失败', { 
					code, 
					stderr: errorData,
					stdout: outputData,
				});
				return reject(new Error(`Python脚本执行失败，错误信息: ${errorData}`));
			}
			
			// 执行成功，返回成功结果
			const inferenceTimeMinutes = parseFloat(((Date.now() - startTime) / 1000 / 60).toFixed(2));
			logger.info('✅ 唇形同步推理成功, 推理时间: ', inferenceTimeMinutes, '分钟');
			const result: TaskResult = {
				success: true,
				output_video_url: "xxx.mp4",
				inference_time_minutes: inferenceTimeMinutes
			};
			
			return resolve(result);
		});
		
		// 监听子进程启动错误（如Python不存在、脚本文件不存在等）
		pythonProcess.on('error', (err) => {
			logger.error('启动Python进程失败', { 
				moduleName,
				error: err.message 
			});
			reject(err);
		});
	});
}

/**
 * 验证 Python 运行环境
 * 
 * 在系统启动时，通过执行'python --version'命令来验证 Python 的可用性。
 */
export async function validatePythonEnvironment(): Promise<boolean> {
	return new Promise((resolve) => {
		logger.info('🔍 正在验证Python环境...');
		
		// 启动Python进程执行版本检查
		const pythonProcess = spawn('python', ['--version']);
		
		// 监听进程结束事件
		pythonProcess.on('close', (code) => {
			const isValid = code === 0;
			
			if (isValid) {
				logger.info('✅ Python环境验证成功');
			} else {
				logger.error('❌ Python环境验证失败', { exitCode: code });
			}
			
			resolve(isValid);
		});
		
		// 监听进程启动错误
		pythonProcess.on('error', (error) => {
			logger.error('❌ Python环境验证过程中发生错误', { 
				error: error.message 
			});
			// 发生错误说明Python不可用
			resolve(false);
		});
	});
}


