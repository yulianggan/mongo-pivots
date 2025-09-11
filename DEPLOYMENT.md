# 🚀 Mongo Join Pivot - 一键部署指南

## 快速部署

### 🎯 30秒快速启动

```bash
# 1. 克隆项目
git clone <repository-url>
cd mongo_join_pivot

# 2. 配置环境变量
cp .env.example .env
# 可选：编辑 .env 文件自定义配置

# 3. 一键部署
./deploy.sh prod
```

**访问地址：**
- 前端应用：http://localhost:3000
- 后端API：http://localhost:8000
- API文档：http://localhost:8000/api/docs

## 📋 部署选项

### 开发模式 (前台运行，实时日志)
```bash
./deploy.sh dev
```

### 生产模式 (后台运行)
```bash
./deploy.sh prod
```

### 包含MongoDB数据库
```bash
./deploy.sh with-db
```

## ⚙️ 环境配置说明

### 基础配置
```bash
# 服务端口
BACKEND_PORT=8000    # 后端API端口
FRONTEND_PORT=3000   # 前端应用端口
```

### 数据库配置 (可选)
```bash
# MongoDB连接 - 用于配置持久化存储
MONGO_URI=mongodb://host.docker.internal:27017
MONGO_DB=mongo_pivot_db
ALLOWED_COLLECTIONS=*
```

### 性能调优
```bash
# 文件上传限制
MAX_FILE_SIZE_MB=500
MAX_DATASET_ROWS=10000000

# 处理性能
CHUNK_SIZE=10000
MAX_WORKERS=4
CACHE_TTL=3600
```

### 安全配置
```bash
# CORS设置
CORS_ORIGINS=http://localhost:3000,http://localhost:3001

# 生产环境密钥 (重要!)
SECRET_KEY=your-secret-key-change-in-production
```

## 🛠️ 管理命令

### 服务管理
```bash
# 查看服务状态
docker-compose ps

# 查看实时日志
docker-compose logs -f

# 重启服务
docker-compose restart

# 停止服务
docker-compose down

# 健康检查
./deploy.sh health
```

### 数据管理
```bash
# 查看数据目录
ls -la data/

# 清理临时文件
rm -rf temp/*

# 备份数据 (如使用内置MongoDB)
docker exec mongo-pivot-db mongodump --out /data/db/backup
```

### 系统维护
```bash
# 清理Docker资源
./deploy.sh cleanup

# 更新应用
git pull
./deploy.sh prod

# 查看系统资源使用
docker stats
```

## 📊 服务监控

### 健康检查端点
```bash
# 后端健康检查
curl http://localhost:8000/api/health

# 系统状态
curl http://localhost:8000/api/stats
```

### 日志查看
```bash
# 应用日志
docker-compose logs backend
docker-compose logs frontend

# 错误日志
docker-compose logs --tail=100 backend | grep ERROR
```

## 🚨 故障排除

### 常见问题

**1. 端口被占用**
```bash
# 检查端口占用
lsof -i :8000
lsof -i :3000

# 修改端口配置
vim .env
# 修改 BACKEND_PORT 和 FRONTEND_PORT
```

**2. 服务启动失败**
```bash
# 查看详细日志
docker-compose logs backend
docker-compose logs frontend

# 重新构建
docker-compose build --no-cache
./deploy.sh prod
```

**3. API连接失败**
```bash
# 检查网络连接
curl http://localhost:8000/api/health

# 检查CORS配置
# 确认 .env 中 CORS_ORIGINS 包含前端地址
```

**4. 内存不足**
```bash
# 调整处理参数
vim .env
# 减少 MAX_WORKERS 和 CHUNK_SIZE

# 清理Docker缓存
docker system prune -a
```

### 性能优化建议

**生产环境优化**
```bash
# 在 .env 中设置
APP_MODE=production
LOG_LEVEL=WARNING
ENABLE_DOCS=false
```

**大数据处理优化**
```bash
# 调整处理参数
CHUNK_SIZE=5000      # 减少内存使用
MAX_WORKERS=2        # 限制并发数
CACHE_TTL=7200       # 延长缓存时间
```

## 🔒 安全建议

### 生产环境安全检查
```bash
# 1. 更改默认密钥
SECRET_KEY=生成复杂密钥

# 2. 限制CORS源
CORS_ORIGINS=https://yourdomain.com

# 3. 禁用调试模式
APP_MODE=production
ENABLE_DOCS=false

# 4. 设置文件大小限制
MAX_FILE_SIZE_MB=100
```

### 网络安全
```bash
# 使用反向代理 (推荐)
# Nginx配置示例在 nginx.conf 中

# 启用HTTPS (生产环境必需)
# 使用 Let's Encrypt 或其他SSL证书
```

## 🔧 高级配置

### 自定义域名部署
```bash
# 1. 修改 .env
API_BASE=https://api.yourdomain.com
CORS_ORIGINS=https://yourdomain.com

# 2. 配置反向代理
# 参考 nginx.conf 模板

# 3. 启用HTTPS
# 配置SSL证书
```

### 多实例部署
```bash
# 使用不同端口部署多个实例
cp .env .env.instance2
# 修改端口配置
# 使用 docker-compose -f docker-compose.yml --env-file .env.instance2 up -d
```

### 监控和日志
```bash
# 集成Prometheus监控
ENABLE_MONITORING=true

# 日志聚合
# 配置ELK stack或其他日志系统
```

---

## 📞 支持

如果遇到部署问题：

1. 查看本文档的故障排除部分
2. 检查 GitHub Issues
3. 查看应用日志: `docker-compose logs -f`

**部署成功标志：**
- ✅ 前端应用正常访问
- ✅ 后端API健康检查通过  
- ✅ 可以上传文件和执行连接操作
- ✅ 透视分析功能正常工作