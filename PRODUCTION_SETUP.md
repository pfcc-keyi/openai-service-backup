# OpenAI Service - 本地生产模式启动指南

## 🚀 快速启动步骤

### 1. **配置 API Key**

有三种方式配置你的 OpenAI API Key：

#### 方法 1: 环境变量 (推荐)
```bash
export PRIMARY_OPENAI_API_KEY=sk-your-actual-openai-api-key-here
python3 start_production.py
```

#### 方法 2: 创建 .env 文件
```bash
# 复制模板
cp env.example .env

# 编辑 .env 文件，设置你的 API Key
# PRIMARY_OPENAI_API_KEY=sk-your-actual-openai-api-key-here
```

#### 方法 3: 内联设置
```bash
PRIMARY_OPENAI_API_KEY=sk-your-key python3 start_production.py
```

### 2. **启动 Redis (必需)**

OpenAI Service 需要 Redis 来实现分布式锁：

```bash
# macOS with Homebrew
brew install redis
brew services start redis

# 或使用 Docker
docker run -d -p 6379:6379 --name redis redis:alpine

# 验证 Redis 运行
redis-cli ping  # 应该返回 PONG
```

### 3. **安装依赖**

```bash
cd openai-service

# 创建虚拟环境 (如果还没有)
python3 -m venv openai-env
source openai-env/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 4. **启动 OpenAI Service**

```bash
# 确保在虚拟环境中
source openai-env/bin/activate

# 设置 API Key 并启动
export PRIMARY_OPENAI_API_KEY=sk-your-actual-openai-api-key-here
python3 start_production.py
```

## 🎯 完整示例

```bash
# 1. 进入目录
cd openai-service

# 2. 激活虚拟环境
source openai-env/bin/activate

# 3. 启动 Redis (如果没运行)
brew services start redis

# 4. 设置 API Key 并启动服务
export PRIMARY_OPENAI_API_KEY=sk-proj-your-actual-openai-api-key-here
python3 start_production.py
```

## 📍 启动后验证

服务启动后，你会看到类似输出：

```
🚀 Starting OpenAI Service in Production Mode
==================================================
🔑 CENTRAL API KEY MANAGER for the entire system

✅ Redis connection verified

🎯 Production Configuration:
   - Service: openai-service
   - Version: 1.0.0
   - Mode: Production (DEV_MODE=false)
   - Port: 8004
   - Redis: redis://localhost:6379
   - Primary API Key: sk-proj-AB...xyz ✅

🌐 Service Endpoints:
   - Main API: http://localhost:8004
   - Health Check: http://localhost:8004/health
   - System Info: http://localhost:8004/system/info
   - Metrics: http://localhost:8004/metrics

🔒 Authentication:
   - Service Token: openai-service-production-token
   - Use as Authorization: Bearer <token>
```

### 验证服务运行：

```bash
# 健康检查
curl http://localhost:8004/health

# 系统信息 (需要认证)
curl -H "Authorization: Bearer openai-service-production-token" \
     http://localhost:8004/system/info

# 查看活跃锁 (需要认证)
curl -H "Authorization: Bearer openai-service-production-token" \
     http://localhost:8004/v1/locks/active
```

## 🔧 其他服务集成

启动 OpenAI Service 后，需要配置其他服务使用它：

### labeling-service 配置

```bash
# labeling-service/.env
DEV_MODE=false
OPENAI_SERVICE_URL=http://localhost:8004
# 移除或注释掉 OPENAI_API_KEY
```

### json-service 配置

```bash
# json-service/.env  
DEV_MODE=false
OPENAI_SERVICE_URL=http://localhost:8004
# 移除或注释掉 OPENAI_API_KEY
```

## 🔐 多 API Key 配置 (可选)

如果你有多个 OpenAI API Key，可以配置负载均衡：

```bash
export PRIMARY_OPENAI_API_KEY=sk-your-primary-key
export OPENAI_API_KEYS=sk-additional-key1,sk-additional-key2,sk-additional-key3
```

或在 `.env` 文件中：

```bash
PRIMARY_OPENAI_API_KEY=sk-your-primary-key
OPENAI_API_KEYS=sk-additional-key1,sk-additional-key2,sk-additional-key3
```

## 🛠️ 故障排除

### 问题 1: API Key 未设置
```
❌ Error: PRIMARY_OPENAI_API_KEY environment variable is required
```
**解决方案**: 确保设置了正确的 OpenAI API Key

### 问题 2: Redis 连接失败
```
❌ Redis connection failed: [Errno 61] Connection refused
```
**解决方案**: 启动 Redis 服务
```bash
brew services start redis
# 或
docker run -d -p 6379:6379 redis:alpine
```

### 问题 3: 端口已被占用
```
❌ [Errno 48] Address already in use
```
**解决方案**: 更改端口或停止占用服务
```bash
export PORT=8005  # 使用不同端口
python3 start_production.py
```

### 问题 4: 依赖缺失
```
ModuleNotFoundError: No module named 'xxx'
```
**解决方案**: 确保在虚拟环境中并安装依赖
```bash
source openai-env/bin/activate
pip install -r requirements.txt
```

## 💡 安全建议

1. **不要提交 API Key**: 确保 `.env` 文件在 `.gitignore` 中
2. **使用环境变量**: 生产环境推荐使用环境变量而非文件
3. **定期轮换 Key**: 定期更换 OpenAI API Key
4. **监控使用量**: 通过 `/metrics` 端点监控 API 使用情况

## 📊 监控和运维

- **健康检查**: `GET /health`
- **系统信息**: `GET /system/info` 
- **Prometheus 指标**: `GET /metrics`
- **活跃锁列表**: `GET /v1/locks/active`
- **强制释放锁**: `DELETE /v1/locks/{lock_id}/force-release`
- **清理过期锁**: `POST /v1/maintenance/cleanup-expired`

所有管理端点都需要 `Authorization: Bearer openai-service-production-token` 认证。 