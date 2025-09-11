# 🍎 Mac M1/M2 Docker 一键部署指南

## 🚀 一键部署命令

```bash
# 克隆项目（如果还没有）
git clone <repository-url>
cd mongo_join_pivot

# 一键部署
./deploy-mac-m1.sh
```

**就这么简单！** 🎉

## 📋 部署前准备

### 1. 确保Docker Desktop已安装
```bash
# 检查Docker是否安装
docker --version

# 如果没有安装，下载Docker Desktop for Mac (Apple Chip)
# https://docs.docker.com/desktop/mac/install/
```

### 2. 确保Docker Desktop运行中
- 启动Docker Desktop应用
- 等待Docker图标显示绿色状态

## 🔧 专门针对Mac M1/M2优化

### ARM64架构支持
```dockerfile
# 使用ARM64原生镜像
FROM --platform=linux/arm64 node:18-alpine
FROM --platform=linux/arm64 python:3.11-slim
```

### 依赖兼容性优化
```bash
# npm配置优化
npm config set target_platform darwin
npm config set target_arch arm64

# Python依赖ARM64优化
pip install --no-cache-dir
```

### Docker BuildKit启用
```bash
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
```

## 📊 部署后验证

### 服务状态检查
```bash
# 检查容器运行状态
docker-compose -f docker-compose.mac-m1.yml ps

# 检查服务健康
curl http://localhost:8000/api/health
curl http://localhost:3000
```

### 访问地址
- **前端应用**: http://localhost:3000
- **后端API**: http://localhost:8000  
- **API文档**: http://localhost:8000/docs

## 🛠️ 常用操作命令

### 启动/停止服务
```bash
# 启动服务
docker-compose -f docker-compose.mac-m1.yml up -d

# 停止服务  
docker-compose -f docker-compose.mac-m1.yml down

# 重启服务
docker-compose -f docker-compose.mac-m1.yml restart
```

### 查看日志
```bash
# 查看所有服务日志
docker-compose -f docker-compose.mac-m1.yml logs -f

# 查看特定服务日志
docker-compose -f docker-compose.mac-m1.yml logs -f frontend
docker-compose -f docker-compose.mac-m1.yml logs -f backend
```

### 更新服务
```bash
# 重新构建并启动
docker-compose -f docker-compose.mac-m1.yml up --build -d

# 强制重新构建
docker-compose -f docker-compose.mac-m1.yml build --no-cache
```

## 🔍 故障排除

### 常见问题及解决方案

#### 1. 构建失败 - 依赖问题
```bash
# 清理Docker缓存
docker system prune -a

# 重新构建
./deploy-mac-m1.sh
```

#### 2. 端口冲突
```bash
# 检查端口占用
lsof -i :3000
lsof -i :8000

# 修改端口（编辑docker-compose.mac-m1.yml）
ports:
  - "3001:80"  # 前端改为3001
  - "8001:8000"  # 后端改为8001
```

#### 3. 内存不足
```bash
# 为Docker Desktop分配更多内存
# Docker Desktop > Settings > Resources > Memory > 8GB+
```

#### 4. 网络问题
```bash
# 重置Docker网络
docker network prune

# 重启Docker Desktop
```

## 🔧 高级配置

### 自定义环境变量
创建 `.env.mac-m1` 文件：
```bash
# 服务端口
FRONTEND_PORT=3000
BACKEND_PORT=8000

# API配置
API_BASE=http://localhost:8000

# Docker配置
COMPOSE_PROJECT_NAME=mongo-pivot-m1
```

### 数据持久化
```yaml
# 在docker-compose.mac-m1.yml中添加
volumes:
  - ./data:/app/data
  - mongo_data:/data/db
```

### 性能优化
```bash
# 启用Docker BuildKit缓存
export BUILDKIT_INLINE_CACHE=1

# 多阶段并行构建
docker-compose build --parallel
```

## 📈 性能监控

### 资源使用监控
```bash
# 实时监控容器资源使用
docker stats

# 查看具体容器信息
docker inspect mongo-pivot-frontend-m1
docker inspect mongo-pivot-backend-m1
```

### 日志管理
```bash
# 限制日志大小
# 在docker-compose.mac-m1.yml中添加
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

## 🚀 生产环境部署

### 优化配置
```bash
# 使用生产环境配置
docker-compose -f docker-compose.mac-m1.yml -f docker-compose.prod.yml up -d
```

### 安全加固
```bash
# 移除开发工具
RUN npm prune --production

# 使用非root用户
USER node
```

## 🎯 完整示例

### 完整部署流程
```bash
# 1. 克隆项目
git clone <repository-url>
cd mongo_join_pivot

# 2. 一键部署
./deploy-mac-m1.sh

# 3. 验证部署
curl http://localhost:8000/api/health
open http://localhost:3000

# 4. 查看日志
docker-compose -f docker-compose.mac-m1.yml logs -f

# 5. 使用完整功能
# 访问前端，测试数据上传、连接、透视等功能
```

## ✅ 部署清单

- [ ] Docker Desktop已安装并运行
- [ ] 端口3000和8000未被占用
- [ ] 有足够的磁盘空间（2GB+）
- [ ] Docker分配了足够内存（4GB+）
- [ ] 网络连接正常
- [ ] 执行 `./deploy-mac-m1.sh`
- [ ] 验证服务正常运行
- [ ] 测试前端功能

---

## 🎉 总结

现在你有了专门为Mac M1/M2芯片优化的Docker一键部署方案！

**特点：**
- ✅ 完全解决ARM64兼容性问题
- ✅ 一键脚本，简单易用
- ✅ 针对Apple Silicon优化
- ✅ 完整的故障排除指南
- ✅ 生产环境就绪

**只需要一行命令：**
```bash
./deploy-mac-m1.sh
```

就能在Mac M1/M2上完美运行整个多源数据连接和透视分析系统！