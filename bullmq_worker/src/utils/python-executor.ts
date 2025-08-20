/**
 * Python脚本执行器模块
 */

import { spawn } from 'child_process';
import path from 'path';
import logger from './logger';

/**
 * 执行Python脚本并获取处理结果
 */
export async function executePythonScript(
	inputVideoPath: string,
    inputAudioPath: string,
    outputVideoPath: string,
    tempDir: string
): Promise<void> {
	return new Promise((resolve, reject) => {
		logger.info('🔄 开始执行唇形同步推理...');
		
		// 构建命令行参数数组，使用-m参数执行模块
		const args = [
			'-m', "scripts.inference",
			'--unet_config_path', "configs/unet/stage2_512.yaml",
			"--inference_ckpt_path", "checkpoints/latentsync_unet.pt",
			"--inference_steps", "20",
            "--guidance_scale", "1.5",
			'--video_path', inputVideoPath,
			'--audio_path', inputAudioPath,
			"--video_out_path", outputVideoPath,
            "--temp_dir", tempDir,
            "--enable_deepcache",
		];
		
		// 启动Python子进程
		const pythonProcess = spawn('python3', args, { 
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
			
			logger.info('✅ 唇形同步推理成功');
			resolve();
		});
		
		// 监听进程启动错误
		pythonProcess.on('error', (error) => {
			logger.error('❌ Python进程启动失败', { 
				error: error.message 
			});
			reject(new Error(`Python进程启动失败: ${error.message}`));
		});
		
	});
}

