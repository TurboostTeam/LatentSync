/**
 * Worker配置模块
 */

import dotenv from 'dotenv';
import { ConnectionOptions } from 'bullmq';

dotenv.config({ path: process.env.ENV_PATH || '../.env' });


export const redisConnection: ConnectionOptions = {
	host: process.env.REDIS_HOST || 'localhost',
	port: parseInt(process.env.REDIS_PORT || '6379'),
	username: process.env.REDIS_USERNAME || 'default',
	password: process.env.REDIS_PASSWORD,
	db: parseInt(process.env.REDIS_DB || '0'),
	...(process.env.REDIS_SSL === 'true' || process.env.REDIS_SSL === 'True' ? { 
		tls: {
			rejectUnauthorized: false
		}
	} : {}),
	
	maxRetriesPerRequest: null,
};


export const queueConfig = {
	name: process.env.QUEUE_NAME || 'lip_sync_queue',
	concurrency: parseInt(process.env.WORKER_CONCURRENCY || '1'),
};

