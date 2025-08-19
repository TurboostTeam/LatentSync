import { IStorageClient, StorageConfig } from './base-client';
import { MinIOClient } from './minio-client';
import { AliyunOSSClient } from './aliyun-oss-client';
import { s3Config } from '../config';
import logger from '../utils/logger';

/**
 * 存储后端类型
 */
export enum StorageBackend {
  MINIO = 'minio',
  ALIYUN_OSS = 'aliyun_oss',
}

/**
 * 存储客户端注册表
 */
const CLIENT_REGISTRY: Record<StorageBackend, new (config: StorageConfig) => IStorageClient> = {
  [StorageBackend.MINIO]: MinIOClient,
  [StorageBackend.ALIYUN_OSS]: AliyunOSSClient,
};

/**
 * 存储客户端工厂类
 */
export class StorageFactory {
  private backendType: StorageBackend;
  private client: IStorageClient;
  
  constructor() {
    const storageConfig: StorageConfig = {
      endpoint: s3Config.endpoint,
      accessKey: s3Config.accessKey,
      secretKey: s3Config.secretKey,
      region: s3Config.region,
      bucketName: s3Config.bucket,
    };
    
    this.backendType = this.detectStorageBackend(storageConfig.endpoint);
    this.client = this.createClient(storageConfig);
  }
  
  /**
   * 检测存储后端类型
   */
  private detectStorageBackend(endpoint: string): StorageBackend {
    const endpointLower = endpoint.toLowerCase();
    
    // 检查endpoint是否指向阿里云OSS
    const aliyunIndicators = [
      'aliyuncs.com',
      'oss-cn-',
      'oss-us-',
      'oss-eu-',
      'oss-ap-',
      '.oss.',
    ];
    
    if (aliyunIndicators.some(indicator => endpointLower.includes(indicator))) {
      logger.info('📦 检测到存储后端: Aliyun OSS');
      return StorageBackend.ALIYUN_OSS;
    } else {
      logger.info('📦 检测到存储后端: MinIO/S3');
      return StorageBackend.MINIO;
    }
  }
  
  /**
   * 根据后端类型创建存储客户端
   */
  private createClient(storageConfig: StorageConfig): IStorageClient {
    const ClientClass = CLIENT_REGISTRY[this.backendType];
    
    if (!ClientClass) {
      throw new Error(`❌ 不支持的存储后端: ${this.backendType}`);
    }
    
    return new ClientClass(storageConfig);
  }
  
  /**
   * 获取存储客户端实例
   */
  getClient(): IStorageClient {
    return this.client;
  }
  
  /**
   * 获取检测到的后端类型
   */
  getBackendType(): StorageBackend {
    return this.backendType;
  }
}

// 单例模式
let storageFactory: StorageFactory | null = null;

export function getStorageClient(): IStorageClient {
  if (!storageFactory) {
    storageFactory = new StorageFactory();
  }
  return storageFactory.getClient();
}
