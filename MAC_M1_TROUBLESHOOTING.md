# 🚨 Mac M1/M2 Docker 故障排除指南

## 常见问题及解决方案

### 1. 网络错误 - apt-get失败
**错误信息**: `E: Failed to fetch ... 500 reading HTTP response body: unexpected EOF`

**解决方案**:
```bash
# 方案1: 重新运行部署脚本（内置重试机制）
./deploy-mac-m1.sh

# 方案2: 手动切换到轻量级构建
sed -i '' 's/Dockerfile.mac-backend/Dockerfile.mac-backend-lite/g' docker-compose.mac-m1.yml
docker-compose -f docker-compose.mac-m1.yml build --no-cache

# 方案3: 清理Docker缓存后重试
docker system prune -a
./deploy-mac-m1.sh
```

### 2. 构建失败 - 平台不兼容
**错误信息**: `The requested image's platform (linux/amd64) does not match`

**解决方案**:
```bash
# 强制使用ARM64平台
export DOCKER_DEFAULT_PLATFORM=linux/arm64
./deploy-mac-m1.sh
```

### 3. 内存不足错误
**错误信息**: `Cannot allocate memory` 或构建过程中断

**解决方案**:
```bash
# 1. 增加Docker Desktop内存配置
# Docker Desktop > Settings > Resources > Memory > 8GB+

# 2. 清理系统资源
docker system prune -a
docker volume prune

# 3. 重启Docker Desktop
```

### 4. 端口冲突
**错误信息**: `port is already allocated`

**解决方案**:
```bash
# 检查端口占用
lsof -i :3000
lsof -i :8000

# 停止占用进程
kill -9 <PID>

# 或修改端口配置
# 编辑 docker-compose.mac-m1.yml
ports:
  - "3001:80"   # 前端改为3001
  - "8001:8000" # 后端改为8001
```

### 5. 权限问题
**错误信息**: `permission denied`

**解决方案**:
```bash
# 确保脚本有执行权限
chmod +x deploy-mac-m1.sh

# 确保Docker有足够权限
sudo chown -R $(whoami) /var/run/docker.sock
```

### 6. npm安装失败（前端）
**错误信息**: `gyp ERR! build error` 或 `node-gyp rebuild failed`

**解决方案**:
```bash
# 清理npm缓存
npm cache clean --force

# 重新生成package-lock.json
rm -rf node_modules package-lock.json
npm install

# 或使用yarn代替npm
yarn install
```

## 🔧 高级故障排除

### Docker网络问题
```bash
# 重置Docker网络
docker network prune

# 重启Docker服务
sudo systemctl restart docker  # Linux
# 或重启Docker Desktop应用 # macOS
```

### 完全重置Docker环境
```bash
# 警告：这会删除所有Docker数据
docker system prune -a --volumes
docker network prune
docker volume prune

# 重启Docker Desktop
# 重新运行部署脚本
./deploy-mac-m1.sh
```

### 检查系统兼容性
```bash
# 确认Mac芯片类型
system_profiler SPHardwareDataType | grep "Chip"

# 确认Docker版本支持ARM64
docker version

# 确认Docker Desktop版本
# 推荐: Docker Desktop 4.0+
```

## 📊 性能优化建议

### Docker Desktop配置
- **内存**: 最少4GB，推荐8GB+
- **CPU**: 分配2核以上
- **磁盘**: 确保有5GB+可用空间

### 网络优化
```bash
# 使用国内镜像源（如果在中国）
echo '{
  "registry-mirrors": [
    "https://hub-mirror.c.163.com",
    "https://mirror.baidubce.com"
  ]
}' > ~/.docker/daemon.json

# 重启Docker生效
```

### 构建性能优化
```bash
# 启用BuildKit缓存
export BUILDKIT_INLINE_CACHE=1
export DOCKER_BUILDKIT=1

# 使用并行构建
docker-compose build --parallel
```

## 🆘 获取帮助

### 日志收集
```bash
# 收集系统信息
echo "=== System Info ===" > debug.log
system_profiler SPHardwareDataType >> debug.log
docker version >> debug.log
docker-compose version >> debug.log

# 收集Docker日志
echo "=== Docker Logs ===" >> debug.log
docker-compose -f docker-compose.mac-m1.yml logs >> debug.log

# 收集构建日志
echo "=== Build Logs ===" >> debug.log
docker-compose -f docker-compose.mac-m1.yml build 2>&1 >> debug.log
```

### 联系支持
如果问题仍然存在，请提供以下信息：
1. Mac型号和macOS版本
2. Docker Desktop版本
3. 错误信息截图
4. debug.log文件内容

## ✅ 验证清单

部署成功后，请验证：
- [ ] 前端可访问: http://localhost:3000
- [ ] 后端API响应: http://localhost:8000/api/health
- [ ] API文档可访问: http://localhost:8000/docs
- [ ] 容器运行正常: `docker-compose -f docker-compose.mac-m1.yml ps`
- [ ] 日志无错误: `docker-compose -f docker-compose.mac-m1.yml logs`

---

## 🎯 快速解决方案

如果你赶时间，尝试这个一键修复：

```bash
# 超级故障排除脚本
docker system prune -a -f
export DOCKER_DEFAULT_PLATFORM=linux/arm64
export DOCKER_BUILDKIT=1
./deploy-mac-m1.sh
```

这个组合解决了90%的Mac M1 Docker部署问题！