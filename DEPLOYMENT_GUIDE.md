# OpenAI Service 部署指南

## 🚀 快速部署到免费平台

### Railway 部署 (推荐)

#### 1. 准备工作
1. 注册Railway账号: https://railway.app
2. 连接GitHub账号
3. 准备OpenAI API密钥

#### 2. 部署步骤
1. 在Railway控制台点击 "New Project"
2. 选择 "Deploy from GitHub repo"
3. 选择 `openai-service` 仓库
4. Railway会自动检测并部署

#### 3. 配置环境变量
在Railway项目设置中添加以下环境变量：

```
SERVICE_NAME=openai-service
DEV_MODE=false
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8004
SERVICE_TOKEN=your-secure-token-here
PRIMARY_OPENAI_API_KEY=sk-your-openai-api-key-here
REDIS_URL=redis://redis:6379
```

#### 4. 添加Redis服务
1. 在Railway项目中点击 "Add Service"
2. 选择 "Redis"
3. Railway会自动配置连接

### Render 部署

#### 1. 创建Web Service
1. 访问 https://render.com
2. 连接GitHub仓库
3. 配置服务：
   - **Name**: openai-service
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python start_production.py`

#### 2. 添加Redis
1. 在Render控制台创建Redis实例
2. 复制Redis URL到环境变量

### Fly.io 部署

#### 1. 安装Fly CLI
```bash
curl -L https://fly.io/install.sh | sh
```

#### 2. 初始化和部署
```bash
fly auth login
fly launch
fly deploy
```

## 🧪 本地Docker测试

### 使用docker-compose
```bash
# 1. 配置环境变量
cp deployment.env.example .env
# 编辑 .env 文件，设置正确的API密钥

# 2. 启动服务
docker-compose up -d

# 3. 检查健康状态
curl http://localhost:8004/health

# 4. 查看日志
docker-compose logs -f openai-service
```

### 单独构建和运行
```bash
# 构建镜像
docker build -t openai-service:latest .

# 运行Redis
docker run -d --name redis -p 6379:6379 redis:7-alpine

# 运行OpenAI Service
docker run -d --name openai-service \
  -p 8004:8004 \
  --link redis:redis \
  --env-file .env \
  openai-service:latest
```

## 🔧 配置说明

### 必需环境变量
- `PRIMARY_OPENAI_API_KEY`: OpenAI API密钥
- `SERVICE_TOKEN`: 服务认证令牌
- `REDIS_URL`: Redis连接URL

### 可选环境变量
- `OPENAI_API_KEYS`: 多个API密钥（逗号分隔）
- `LOG_LEVEL`: 日志级别 (DEBUG/INFO/WARNING/ERROR)
- `DEFAULT_LOCK_TIMEOUT`: 默认锁超时时间（秒）

## 🔍 健康检查

### 检查服务状态
```bash
curl http://your-domain/health
```

预期响应：
```json
{
  "status": "healthy",
  "service": "openai-service",
  "version": "1.0.0",
  "redis_connected": true,
  "api_keys_available": 1
}
```

### 检查API密钥状态
```bash
curl -H "Authorization: Bearer your-service-token" \
     http://your-domain/api-keys/status
```

## 🐛 故障排除

### 常见问题

#### 1. Redis连接失败
- 检查REDIS_URL环境变量
- 确保Redis服务正在运行
- 验证网络连接

#### 2. OpenAI API密钥无效
- 检查API密钥格式（以sk-开头）
- 验证API密钥有效性
- 检查API配额和余额

#### 3. 服务启动失败
- 查看启动日志
- 检查端口是否被占用
- 验证环境变量配置

### 日志查看
```bash
# Docker Compose
docker-compose logs -f openai-service

# Docker
docker logs -f openai-service

# Railway
railway logs

# Render
# 在Render控制台查看日志
```

## 📊 监控和指标

### Prometheus指标端点
```
GET /metrics
```

### 关键指标
- `openai_api_requests_total`: API请求总数
- `openai_lock_acquisitions_total`: 锁获取总数
- `openai_api_key_health`: API密钥健康状态
- `redis_connection_status`: Redis连接状态

## 🔐 安全建议

1. **API密钥安全**
   - 使用环境变量存储API密钥
   - 定期轮换API密钥
   - 监控API使用情况

2. **服务认证**
   - 使用强SERVICE_TOKEN
   - 启用HTTPS（生产环境）
   - 限制网络访问

3. **Redis安全**
   - 使用密码保护
   - 限制网络访问
   - 启用持久化备份 