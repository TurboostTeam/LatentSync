# BullMQ Worker Service

TypeScript 版本的 BullMQ 消费者服务，支持 GPU 加速的唇形同步任务处理。


## 安装Node.js
* 用户级 (仅对当前用户生效)，适用于开发环境
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install 18
nvm use 18
```
* 系统级 (对所有用户生效)，适用于生产环境
```bash
curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
&& apt-get install -y nodejs
```


## 启动消费者服务

### 开发环境

```bash
# 进入消费者目录
cd bullmq_worker

# 安装依赖
npm install

# 配置环境变量
cp env.example .env

# 启动消费者服务（开发模式）
npm run dev

# 如果遇到信号处理问题，使用这个命令代替 npm run dev
npm run dev:no-watch
```

### 生产环境

```bash
# 进入消费者目录
cd bullmq_worker

# 安装所有依赖 (基于 package-lock.json 文件，由`npm install`生成)
npm ci

# 构建项目
npm run build

# 启动服务（生产模式，直接启动构建后的文件）
node dist/index.js

# 或使用npm start（会有额外的npm进程开销）
npm start
```

### 开发环境 vs 生产环境差异说明

#### 依赖安装差异
- **开发环境**: `npm install` - 安装所有依赖包括devDependencies，支持热重载和调试
- **生产环境**: `npm ci` - 更快更精确，基于lock文件确保一致性

#### 启动方式差异
- **开发环境**: `npm run dev` - 使用tsx watch模式，支持热重载和TypeScript直接执行
- **生产环境**: `node dist/index.js` - 直接启动编译后的JavaScript，避免npm进程开销，更适合容器环境


## 进度说明

### 📊 总体进度范围

| 进度范围 | 主要阶段 | 详细说明 |
|---------|----------|----------|
| 0-5% | 下载视频文件 | 从存储服务下载输入视频 |
| 5-10% | 下载音频文件 | 从存储服务下载输入音频 |
| 10-90% | **唇形同步推理** | **核心阶段，包含详细子进度** |
| 90-95% | 上传处理结果 | 将结果视频上传到存储服务 |
| 95-100% | 清理和完成 | 清理临时文件，任务完成 |

### 📊 唇形同步推理阶段详细进度 (10-90%)

> 实时跟踪Python推理子进程内部进度

| 子阶段 | 进度映射 | 具体内容 |
|--------|----------|----------|
| **推理初始化** | 10-20% | 加载模型、准备数据 |
| **分块推理** | 20-70% | 按 chunk 处理视频帧，包括人脸检测、仿射变换、去噪循环|
| **视频恢复** | 70-80% | 将生成结果恢复到原始视频帧 |
| **最终合成** | 80-90% | 合成最终视频文件 |
