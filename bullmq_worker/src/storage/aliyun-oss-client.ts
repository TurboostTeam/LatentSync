import OSS from 'ali-oss';
import * as fs from 'fs';
import * as path from 'path';
import { URL } from 'url';
import { BaseStorageClient, StorageConfig } from './base-client';
import logger from '../utils/logger';

/**
 * Aliyun OSS storage client implementation
 */
export class AliyunOSSClient extends BaseStorageClient {
  private client: OSS;
  
  // 上传优化配置（可根据网络环境调整）
  private readonly MULTIPART_THRESHOLD = 10 * 1024 * 1024; // 10MB，超过此大小启用分片
  private readonly PART_SIZE = 10 * 1024 * 1024; // 10MB，每个分片大小（建议5-20MB）
  private readonly MAX_CONCURRENT_PARTS = 3; // 最大并行分片数（建议2-5，网络好可增加到8）
  
  constructor(config: StorageConfig) {
    super(config);
    
    // Create Aliyun OSS client
    this.client = new OSS({
      region: this.region,
      accessKeyId: this.accessKey,
      accessKeySecret: this.secretKey,
      bucket: this.bucketName,
      endpoint: this.endpoint,
      secure: this.endpoint.includes('https'),
      // 增加超时配置，解决大文件上传超时问题
      timeout: 1800000, // 30分钟超时时间
      requestTimeout: 1800000, // 请求超时时间
      responseTimeout: 1800000, // 响应超时时间
    });
    
    // 检查桶是否存在
    this.ensureBucketExists().catch(error => {
      logger.error(error.message || error);
    });
  }
  
  /**
   * 确保存储桶存在 (阿里云OSS的桶需要在控制台创建)
   */
  protected async ensureBucketExists(): Promise<void> {
    try {
      await this.client.getBucketInfo(this.bucketName);
      logger.info(`📦 桶 ${this.bucketName} 存在`);
    } catch (error: any) {
      if (error.code === 'NoSuchBucket') {
        throw new Error(`桶 ${this.bucketName} 不存在`);
      } else {
        throw new Error(`检查桶状态失败: ${error}`);
      }
    }
  }
  
  /**
   * 从阿里云OSS下载文件
   */
  async downloadFile(objectKey: string, localPath: string): Promise<void> {
    try {
      // 创建本地目录
      const dir = path.dirname(localPath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      
      // 下载文件
      const result = await this.client.get(objectKey);
      
      // 写入本地文件
      if (result.content) {
        fs.writeFileSync(localPath, result.content);
        logger.info(`✅ 下载成功: ${this.bucketName}/${objectKey} -> ${localPath}`);
      } else {
        throw new Error('❌ 未收到OSS内容');
      }
    } catch (error: any) {
      if (error.code === 'NoSuchKey') {
        logger.error(`❌ 文件不存在: ${this.bucketName}/${objectKey}`);
        throw new Error(`文件不存在: ${this.bucketName}/${objectKey}`);
      } else {
        logger.error(`❌ 阿里云OSS下载失败: ${error}`);
        throw new Error(`阿里云OSS下载失败: ${error}`);
      }
    }
  }
  
  /**
   * 上传文件到阿里云OSS（带重试机制）
   */
  async uploadFile(objectKey: string, localPath: string, maxRetries: number = 3): Promise<string> {
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        // 检查本地文件是否存在
        if (!fs.existsSync(localPath)) {
          throw new Error(`❌ 本地文件不存在: ${localPath}`);
        }
        
        // 获取文件大小
        const stats = fs.statSync(localPath);
        const fileSizeInMB = stats.size / (1024 * 1024);
        
        logger.info(`📤 开始上传文件 (第${attempt}/${maxRetries}次尝试): ${localPath}, 大小: ${fileSizeInMB.toFixed(2)}MB`);
        
        // 对于超过阈值的文件使用分片上传
        if (stats.size > this.MULTIPART_THRESHOLD) {
          logger.info(`📤 使用分片上传处理大文件: ${fileSizeInMB.toFixed(2)}MB (阈值: ${this.MULTIPART_THRESHOLD / (1024 * 1024)}MB)`);
          await this.multipartUpload(objectKey, localPath, stats.size);
        } else {
          // 小文件使用普通上传
          await this.client.put(objectKey, localPath);
        }
        
        logger.info(`✅ 上传成功: ${localPath} -> ${this.bucketName}/${objectKey}`);
        
        // 生成预签名URL
        const outputUrl = await this.buildUrl(objectKey);
        return outputUrl;
        
      } catch (error: any) {
        const isLastAttempt = attempt === maxRetries;
        const errorMessage = error?.message || error?.toString() || '未知错误';
        
        if (isLastAttempt) {
          logger.error(`❌ Aliyun OSS 上传失败 (${maxRetries}次重试后): ${errorMessage}`);
          throw new Error(`Aliyun OSS 上传失败: ${errorMessage}`);
        } else {
          const waitTime = Math.min(1000 * Math.pow(2, attempt - 1), 30000); // 指数退避，最大30秒
          logger.warn(`⚠️ 上传失败，${waitTime/1000}秒后重试 (第${attempt}/${maxRetries}次): ${errorMessage}`);
          
          // 等待后重试
          await new Promise(resolve => setTimeout(resolve, waitTime));
        }
      }
    }
    
    throw new Error('上传失败：所有重试都已用完');
  }
  
  /**
   * 分片上传大文件（并行）
   */
  private async multipartUpload(objectKey: string, localPath: string, fileSize: number): Promise<void> {
    const partSize = this.PART_SIZE;
    const totalParts = Math.ceil(fileSize / partSize);
    const maxConcurrent = this.MAX_CONCURRENT_PARTS;
    
    logger.info(`📤 分片上传开始: ${totalParts} 个分片，每个分片 ${partSize / (1024 * 1024)}MB，并行数为 ${maxConcurrent}`);
    
    try {
      // 初始化分片上传
      const uploadId = await this.client.initMultipartUpload(objectKey);
      
      const parts: Array<{ number: number; etag: string }> = [];
      const startTime = Date.now();
      let uploadedBytes = 0;
      
      // 准备所有分片任务
      const uploadTasks = [];
      for (let i = 0; i < totalParts; i++) {
        const partNumber = i + 1;
        const start = i * partSize;
        const end = Math.min(start + partSize, fileSize);
        const partLength = end - start;
        
        uploadTasks.push({
          partNumber,
          start,
          partLength,
        });
      }
      
      // 并行上传分片
      const uploadPart = async (task: { partNumber: number; start: number; partLength: number }) => {
        const { partNumber, start, partLength } = task;
        
        // 读取分片数据
        const buffer = Buffer.allocUnsafe(partLength);
        const fileHandle = fs.openSync(localPath, 'r');
        fs.readSync(fileHandle, buffer, 0, partLength, start);
        fs.closeSync(fileHandle);
        
        const partStartTime = Date.now();
        logger.info(`📤 上传分片 ${partNumber}/${totalParts} - 大小: ${(partLength / (1024 * 1024)).toFixed(2)}MB`);
        
        try {
          const partResult = await this.client.uploadPart(
            objectKey,
            uploadId.uploadId,
            partNumber,
            buffer
          );
          
          const partElapsed = Date.now() - partStartTime;
          const speed = (partLength / (1024 * 1024)) / (partElapsed / 1000); // MB/s
          
          uploadedBytes += partLength;
          
          logger.info(`✅ 分片 ${partNumber} 上传完成 - 耗时: ${(partElapsed/1000).toFixed(1)}s, 平均速度: ${speed.toFixed(2)}MB/s`);
          
          return {
            number: partNumber,
            etag: partResult.etag
          };
        } catch (error) {
          logger.error(`❌ 分片 ${partNumber} 上传失败: ${error}`);
          throw error;
        }
      };
      
      // 使用Promise并发控制
      for (let i = 0; i < uploadTasks.length; i += maxConcurrent) {
        const batch = uploadTasks.slice(i, i + maxConcurrent);
        const batchResults = await Promise.all(batch.map(uploadPart));
        parts.push(...batchResults);
        
        const totalElapsed = Date.now() - startTime;
        const avgSpeed = uploadedBytes / (totalElapsed / 1000) / (1024 * 1024); // MB/s
        logger.info(`📊 批次完成 - 平均速度: ${avgSpeed.toFixed(2)}MB/s`);
      }
      
      // 按分片号排序
      parts.sort((a, b) => a.number - b.number);
      
      // 完成分片上传
      await this.client.completeMultipartUpload(objectKey, uploadId.uploadId, parts);
      
      const totalElapsed = Date.now() - startTime;
      const avgSpeed = fileSize / (1024 * 1024) / (totalElapsed / 1000);
      logger.info(`✅ 分片全部上传完成: ${totalParts} 个分片，总耗时: ${(totalElapsed/1000/60).toFixed(1)}分钟，平均速度: ${avgSpeed.toFixed(2)}MB/s`);
      
    } catch (error) {
      logger.error(`❌ 分片上传失败: ${error}`);
      throw error;
    }
  }
  
  /**
   * 生成预签名URL
   */
  async buildUrl(objectKey: string, expiresInHours: number = 24): Promise<string> {
    try {
      const expireSeconds = expiresInHours * 3600;
      
      // Generate presigned URL
      const signedUrl = this.client.signatureUrl(objectKey, {
        expires: expireSeconds,
        method: 'GET',
      });
      
      logger.info(`✅ 生成预签名URL: ${signedUrl}, 有效期: ${expiresInHours} 小时`);
      return signedUrl;
    } catch (error) {
      logger.error(`❌ 生成预签名URL失败: ${error}`);
      throw new Error(`生成预签名URL失败: ${error}`);
    }
  }
  
  /**
   * 解析阿里云OSS URL
   */
  parseUrl(url: string): { bucket: string; objectKey: string } {
    try {
      const parsed = new URL(url);
      const hostname = parsed.hostname || '';
      
      // Aliyun OSS URL format: https://bucket.oss-region.aliyuncs.com/path/file
      if (hostname.includes('.aliyuncs.com')) {
        const hostParts = hostname.split('.');
        if (hostParts.length >= 3) {
          const bucket = hostParts[0];
          const objectKey = decodeURIComponent(parsed.pathname.substring(1));
          return { bucket, objectKey };
        }
      }
      
      throw new Error(`无法解析阿里云OSS URL: ${url}`);
    } catch (error) {
      logger.error(`解析URL失败: ${error}`);
      throw new Error(`解析URL失败: ${error}`);
    }
  }
}
