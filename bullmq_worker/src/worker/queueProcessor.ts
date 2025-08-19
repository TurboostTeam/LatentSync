import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { promisify } from 'util';
import { getStorageClient } from '../storage/storage-factory';
import logger from '../utils/logger';
import { executePythonScript } from '../utils/pythonExecutor';

const mkdtemp = promisify(fs.mkdtemp);
const rm = promisify(fs.rm);


/**
 * 队列处理器，用于处理唇形同步任务
 */
export class QueueProcessor {
  private storageClient = getStorageClient();
  
  async processTask(videoUrl: string, audioUrl: string): Promise<string> {
    // 在系统临时目录下创建一个唯一的临时文件夹
    const tempDir = await mkdtemp(path.join(os.tmpdir(), 'lipsync-'));
    
    try {
      // 准备文件路径
      const videoPath = path.join(tempDir, 'input_video.mp4');
      const audioPath = path.join(tempDir, 'input_audio.wav');
      const outputPath = path.join(tempDir, 'output_video.mp4');
      
      // 下载输入文件
      logger.info(`🔄 开始下载视频: ${videoUrl}`);
      await this.downloadInputFile(videoUrl, videoPath);
      
      logger.info(`🔄 开始下载音频: ${audioUrl}`);
      await this.downloadInputFile(audioUrl, audioPath);
      
      // 运行推理子进程
      await this.runInferenceSubprocess(videoPath, audioPath, outputPath, tempDir);
      
      // 上传结果
      const outputUrl = await this.uploadResult(videoUrl, outputPath);
      
      return outputUrl;
    } finally {
      // 清理临时目录
      try {
        await this.cleanupTempDir(tempDir);
      } catch (error) {
        logger.warn(`清理临时目录失败: ${tempDir}: ${error}`);
      }
    }
  }
  
  /**
   * 从S3下载输入文件
   */
  private async downloadInputFile(url: string, localPath: string): Promise<void> {
    const { objectKey } = this.storageClient.parseUrl(url);
    await this.storageClient.downloadFile(objectKey, localPath);
  }
  
  /**
   * 运行推理子进程
   */
  private async runInferenceSubprocess(
    videoPath: string,
    audioPath: string,
    outputPath: string,
    tempDir: string
  ): Promise<void> {
    // 调用executePythonScript执行推理
    await executePythonScript(videoPath, audioPath, outputPath, path.join(tempDir, 'temp'));
  }
  
  /**
   * 上传结果到S3
   */
  private async uploadResult(inputVideoUrl: string, outputVideoLocalPath: string): Promise<string> {
    // 从输入视频URL中解析bucket和object key信息
    const { objectKey: inputVideoObjectKey } = this.storageClient.parseUrl(inputVideoUrl);
    
    // 构建输出视频的object key
    // 从视频object key中提取目录路径
    const targetVideoDir = path.dirname(inputVideoObjectKey);
    // 从原视频文件名中提取基础名称（去掉扩展名）
    const inputVideoBasename = path.basename(inputVideoObjectKey, path.extname(inputVideoObjectKey));
    
    // 生成输出文件的object key，放在与输入文件相同的目录下
    const timestamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '').replace(/(\d{8})(\d{6})/, '$1_$2');
    const targetVideoName = `${inputVideoBasename}_latentsync_${timestamp}.mp4`;
    const outputObjectKey = path.join(targetVideoDir, targetVideoName).replace(/\\/g, '/');
    
    // 上传输出视频
    logger.info(`🔄 上传输出视频: ${outputVideoLocalPath} -> ${outputObjectKey}`);
    const outputUrl = await this.storageClient.uploadFile(outputObjectKey, outputVideoLocalPath);
    
    return outputUrl;
  }
  
  /**
   * Clean up temporary directory
   */
  private async cleanupTempDir(tempDir: string): Promise<void> {
    // Recursively remove directory and its contents
    await rm(tempDir, { recursive: true, force: true });
    logger.info(`🗑️ 清理临时目录: ${tempDir}`);
  }
}
