/**
 * 日志工具模块
 */

import winston from 'winston';

const { combine, timestamp, printf, colorize, errors } = winston.format;

const customFormat = printf(({ level, message, timestamp, ...metadata }) => {
	let msg = `${timestamp} [${level}]: ${message}`;
	
	if (Object.keys(metadata).length > 0) {
		msg += ` ${JSON.stringify(metadata)}`;
	}
	
	return msg;
});


const logger = winston.createLogger({
	level: process.env.LOG_LEVEL || 'info',

	format: combine(
		errors({ stack: true }),
		
		timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
		
		customFormat
	),
	
	transports: [
		new winston.transports.Console({ 
			format: combine(colorize(), customFormat) 
		})
	],
});

export default logger;


