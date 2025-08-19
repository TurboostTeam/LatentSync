/**
 * Base interface for storage clients
 */
export interface IStorageClient {
  /**
   * Download a file from storage
   * @param objectKey - The key/path of the object in storage
   * @param localPath - The local file path to save the downloaded file
   */
  downloadFile(objectKey: string, localPath: string): Promise<void>;
  
  /**
   * Upload a file to storage
   * @param objectKey - The key/path where the object will be stored
   * @param localPath - The local file path to upload
   * @returns The URL of the uploaded file
   */
  uploadFile(objectKey: string, localPath: string): Promise<string>;
  
  /**
   * Build a presigned URL for accessing the object
   * @param objectKey - The key/path of the object
   * @param expiresInHours - URL expiration time in hours (default: 24)
   * @returns The presigned URL
   */
  buildUrl(objectKey: string, expiresInHours?: number): Promise<string>;
  
  /**
   * Parse a storage URL to extract bucket and object key
   * @param url - The storage URL to parse
   * @returns A tuple of [bucket, objectKey]
   */
  parseUrl(url: string): { bucket: string; objectKey: string };
}

/**
 * Base storage client configuration
 */
export interface StorageConfig {
  endpoint: string;
  accessKey: string;
  secretKey: string;
  region: string;
  bucketName: string;
}

/**
 * Abstract base class for storage clients
 */
export abstract class BaseStorageClient implements IStorageClient {
  protected endpoint: string;
  protected accessKey: string;
  protected secretKey: string;
  protected region: string;
  protected bucketName: string;
  
  constructor(config: StorageConfig) {
    this.endpoint = config.endpoint;
    this.accessKey = config.accessKey;
    this.secretKey = config.secretKey;
    this.region = config.region;
    this.bucketName = config.bucketName;
  }
  
  abstract downloadFile(objectKey: string, localPath: string): Promise<void>;
  abstract uploadFile(objectKey: string, localPath: string): Promise<string>;
  abstract buildUrl(objectKey: string, expiresInHours?: number): Promise<string>;
  abstract parseUrl(url: string): { bucket: string; objectKey: string };
  
  /**
   * Ensure the bucket exists (implementation varies by provider)
   */
  protected abstract ensureBucketExists(): Promise<void>;
}
