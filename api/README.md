# Lip Sync API

基于队列的唇形同步API服务，使用子进程处理每个请求以确保模型隔离和资源管理。

## 特性

- **队列处理**: 所有请求通过队列串行处理，确保并发量=1
- **子进程隔离**: 每个任务使用独立的子进程，避免模型初始化冲突
- **无模型预加载**: API启动时不加载模型，每次推理时动态加载
- **异步处理**: 支持异步任务处理和状态监控
- **Redis存储**: 使用Redis存储任务状态和元数据

## API端点

### 基础端点

- `GET /` - API信息
- `GET /health` - 健康检查
- `GET /queue/status` - 队列状态

### 任务管理

- `POST /lipsync` - 创建唇形同步任务
- `GET /tasks/{task_id}` - 获取任务状态  
- `GET /tasks` - 列出所有任务
- `DELETE /tasks/{task_id}` - 删除任务

## 🚀 快速开始

### 配置环境
1. 安装所需的软件包并下载检查点：
```bash
source setup_env.sh
```

如果下载成功，检查点应显示如下：
```
./checkpoints/
|-- latentsync_unet.pt
|-- whisper
|   `-- tiny.pt
```

2. 启动 MinIO 和 Redis
本地测试时，使用 MinIO 模拟 S3 存储，Redis 模拟生产使用的 Redis 存储和跟踪所有唇形同步任务的状态。
```bash
./api_test/local-env/start_all.sh
```

3. 设置环境变量
所有配置通过环境变量设置，根据 `.env.example` 创建 `.env`

### 启动 API 服务
```bash
chmod +x start_api.sh
./start_api.sh
```

### API 文档
```
127.0.0.1:8000/docs
```

### 任务状态

| 状态 | 说明 |
|------|------|
| pending | 任务已创建，等待处理 |
| processing | 正在处理中 |
| completed | 处理完成 |
| failed | 处理失败 |

## 测试

使用测试客户端：

```bash
python ./api_test/test_client.py
```
