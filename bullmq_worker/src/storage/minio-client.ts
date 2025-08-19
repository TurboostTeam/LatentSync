import * as Minio from 'minio';
import * as fs from 'fs';
import * as path from 'path';
import { URL } from 'url';
import { BaseStorageClient, StorageConfig } from './base-client';
import logger from '../utils/logger';

/**
 * MinIO 存储客户端实现
 */
export class MinIOClient extends BaseStorageClient {
  private client: Minio.Client;
  private secure: boolean;
  
  constructor(config: StorageConfig) {
    super(config);
    
    // 检测并设置安全模式
    const { endpoint, secure } = this.detectSecureMode(config.endpoint);
    this.secure = secure;
    
    // 提取端口和主机名
    const { hostname, port } = this.parseEndpoint(endpoint);
    this.endpoint = hostname;
    
    // 创建 MinIO 客户端
    this.client = new Minio.Client(
      {
        endPoint: hostname,
        ...(port && { port: port }),
        useSSL: this.secure,
        accessKey: this.accessKey,
        secretKey: this.secretKey,
        ...(this.region && { region: this.region }),
      }
    );
    
    const protocol = this.secure ? 'HTTPS' : 'HTTP';
    const displayEndpoint = port ? `${hostname}:${port}` : hostname;
    logger.info(`✅ MinIO客户端初始化成功 - 服务器: ${protocol}://${displayEndpoint}, 桶: ${this.bucketName}`);
    
    // 检查桶是否存在
    this.ensureBucketExists().catch(error => {
      logger.error(error.message || error);
    });
  }

  /**
   * 检测并设置secure模式
   */
  private detectSecureMode(endpoint: string): { endpoint: string; secure: boolean } {
    // 如果有协议前缀，根据协议确定安全模式
    if (endpoint.startsWith('https://')) {
      return { endpoint: endpoint.replace('https://', ''), secure: true };
    } else if (endpoint.startsWith('http://')) {
      return { endpoint: endpoint.replace('http://', ''), secure: false };
    }
    
    // 没有协议前缀的情况
    // localhost 和 127.0.0.1 默认使用 HTTP
    if (endpoint.includes('localhost') || endpoint.includes('127.0.0.1')) {
      return { endpoint, secure: false };
    }
    
    // 其他情况默认使用 HTTP（适用于内网和自建服务）
    return { endpoint, secure: false };
  }
  
  /**
   * 解析端点，提取主机名和端口（不会修改实例属性）
   */
  private parseEndpoint(endpoint: string): { hostname: string; port?: number } {
    const parts = endpoint.split(':');
    if (parts.length > 1) {
      const port = parseInt(parts[parts.length - 1], 10);
      if (!isNaN(port)) {
        const hostname = parts.slice(0, -1).join(':');
        return { hostname, port };
      }
    }
    return { hostname: endpoint };
  }
  
  /**
   * 确保桶存在
   */
  protected async ensureBucketExists(): Promise<void> {
    try {
      const exists = await this.client.bucketExists(this.bucketName);
      if (!exists) {
        await this.client.makeBucket(this.bucketName, this.region);
        logger.info(`🔧 创建桶: ${this.bucketName}`);
      } else {
        logger.info(`📦 桶 ${this.bucketName} 存在`);
      }
    } catch (error) {
      throw new Error(`检查桶状态失败: ${error}`);
    }
  }
  
  /**
   * 从MinIO下载文件
   */
  async downloadFile(objectKey: string, localPath: string): Promise<void> {
    try {
      // 创建本地目录
      const dir = path.dirname(localPath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      
      // 下载文件
      await this.client.fGetObject(this.bucketName, objectKey, localPath);
      logger.info(`✅ 下载成功: ${this.bucketName}/${objectKey} -> ${localPath}`);
    } catch (error: any) {
      if (error.code === 'NoSuchKey') {
        logger.error(`❌ 文件不存在: ${this.bucketName}/${objectKey}`);
        throw new Error(`文件不存在: ${this.bucketName}/${objectKey}`);
      } else {
        logger.error(`❌ MinIO下载失败: ${error}`);
        throw new Error(`MinIO下载失败: ${error}`);
      }
    }
  }
  
  /**
   * 上传文件到MinIO
   */
  async uploadFile(objectKey: string, localPath: string): Promise<string> {
    try {
      // 检查本地文件是否存在
      if (!fs.existsSync(localPath)) {
        throw new Error(`❌ 本地文件不存在: ${localPath}`);
      }
      
      // 上传文件
      await this.client.fPutObject(this.bucketName, objectKey, localPath);
      logger.info(`✅ 上传成功: ${localPath} -> ${this.bucketName}/${objectKey}`);
      
      // 生成预签名URL
      const outputUrl = await this.buildUrl(objectKey);
      return outputUrl;
    } catch (error) {
      logger.error(`❌ MinIO 上传失败: ${error}`);
      throw new Error(`MinIO 上传失败: ${error}`);
    }
  }
  
  /**
   * 生成预签名URL
   */
  async buildUrl(objectKey: string, expiresInHours: number = 24): Promise<string> {
    try {
      const expireSeconds = expiresInHours * 3600;
      const signedUrl = await this.client.presignedGetObject(
        this.bucketName,
        objectKey,
        expireSeconds
      );
      
      logger.info(`✅ 生成预签名URL: ${signedUrl}, 有效期: ${expiresInHours} 小时`);
      return signedUrl;
    } catch (error) {
      logger.error(`❌ 生成预签名URL失败: ${error}`);
      throw new Error(`生成预签名URL失败: ${error}`);
    }
  }
  
  /**
   * 解析 MinIO URL
   */
  parseUrl(url: string): { bucket: string; objectKey: string } {
    try {
      const parsed = new URL(url);
      const hostname = parsed.hostname || '';
      const port = parsed.port;
      
      // 构建完整的endpoint用于比较
      const endpointToCheck = port ? `${hostname}:${port}` : hostname;
      
      // # MinIO URL格式: http://127.0.0.1:9000/bucket/path/file
      // 检查hostname是否匹配（忽略协议）
      const cleanEndpoint = this.endpoint.replace('http://', '').replace('https://', '');
      
      if (hostname === cleanEndpoint || endpointToCheck === cleanEndpoint || 
          hostname.includes(cleanEndpoint) || cleanEndpoint.includes(hostname)) {
        
        const pathParts = parsed.pathname.substring(1).split('/', 2);
        if (pathParts.length >= 2) {
          const bucket = pathParts[0];
          const objectKey = decodeURIComponent(pathParts[1]);
          return { bucket, objectKey };
        } else if (pathParts.length === 1) {
          // 如果只有一个路径部分，可能是bucket.endpoint格式
          const hostParts = hostname.split('.');
          if (hostParts.length >= 2) {
            const bucket = hostParts[0];
            const objectKey = decodeURIComponent(pathParts[0]);
            return { bucket, objectKey };
          }
        }
      }
      
      throw new Error(`无法解析 MinIO URL: ${url}`);
    } catch (error) {
      logger.error(`解析URL失败: ${error}`);
      throw new Error(`解析URL失败: ${error}`);
    }
  }
}
