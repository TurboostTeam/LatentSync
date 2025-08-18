# 安装Node.js
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install 18
nvm use 18
```


# 启动消费者服务
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

# 或生产模式
npm run build
npm start
```