declare module 'ali-oss' {
  interface OSSOptions {
    region?: string;
    accessKeyId: string;
    accessKeySecret: string;
    bucket?: string;
    endpoint?: string;
    secure?: boolean;
    timeout?: number;
    requestTimeout?: number;
    responseTimeout?: number;
  }

  interface GetResult {
    content?: Buffer;
    res?: any;
  }

  interface PutResult {
    name: string;
    url: string;
    res?: any;
  }

  interface SignatureUrlOptions {
    expires?: number;
    method?: string;
    'Content-Type'?: string;
    response?: any;
  }

  interface BucketInfo {
    bucket: string;
    owner?: string;
    creationDate?: string;
    location?: string;
  }

  class OSS {
    constructor(options: OSSOptions);
    
    // Bucket operations
    getBucketInfo(bucketName: string): Promise<BucketInfo>;
    
    // Object operations
    get(objectKey: string): Promise<GetResult>;
    put(objectKey: string, localPath: string | Buffer): Promise<PutResult>;
    
    // URL operations
    signatureUrl(objectKey: string, options?: SignatureUrlOptions): string;
    
    // Other methods as needed
    [key: string]: any;
  }

  export = OSS;
}
