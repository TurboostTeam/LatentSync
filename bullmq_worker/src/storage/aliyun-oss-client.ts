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
      timeout: 600000, // 10分钟超时时间 (600秒)
      requestTimeout: 600000, // 请求超时时间
      responseTimeout: 600000, // 响应超时时间
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
   * 上传文件到阿里云OSS
   */
  async uploadFile(objectKey: string, localPath: string): Promise<string> {
    try {
      // 检查本地文件是否存在
      if (!fs.existsSync(localPath)) {
        throw new Error(`❌ 本地文件不存在: ${localPath}`);
      }
      
      // 上传文件
      await this.client.put(objectKey, localPath);
      logger.info(`✅ 上传成功: ${localPath} -> ${this.bucketName}/${objectKey}`);
      
      // 生成预签名URL
      const outputUrl = await this.buildUrl(objectKey);
      return outputUrl;
    } catch (error) {
      logger.error(`❌ Aliyun OSS 上传失败: ${error}`);
      throw new Error(`Aliyun OSS 上传失败: ${error}`);
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
