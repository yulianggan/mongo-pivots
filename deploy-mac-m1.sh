#!/bin/bash

# Mac M1/M2 一键Docker部署脚本
# 适用于Apple Silicon芯片的MacBook

set -e

echo "🚀 Mac M1/M2 Docker 一键部署脚本"
echo "=================================="

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker Desktop for Mac"
    echo "下载链接: https://docs.docker.com/desktop/mac/install/"
    exit 1
fi

# 检查Docker是否运行
if ! docker info &> /dev/null; then
    echo "❌ Docker 未运行，请启动 Docker Desktop"
    exit 1
fi

echo "✅ Docker 环境检查通过"

# 启用Docker BuildKit（ARM64优化）
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

echo "🔧 配置Docker BuildKit for ARM64..."

# 检查是否存在旧容器并停止
echo "🧹 清理旧容器..."
docker-compose -f docker-compose.mac-m1.yml down 2>/dev/null || true

# 清理旧镜像（可选）
if [[ "${1}" == "--clean" ]]; then
    echo "🗑️ 清理旧镜像..."
    docker system prune -f
else
    echo "ℹ️ 跳过清理旧镜像（使用 --clean 参数来清理）"
fi

# 构建并启动服务
echo "🏗️ 构建Docker镜像（针对ARM64优化）..."

# 尝试轻量级构建
if docker-compose -f docker-compose.mac-m1.yml build --no-cache; then
    echo "✅ 轻量级构建成功"
else
    echo "⚠️ 轻量级构建失败，尝试标准构建..."
    # 切换回标准Dockerfile
    sed -i '' 's/Dockerfile.mac-backend-lite/Dockerfile.mac-backend/g' docker-compose.mac-m1.yml
    
    if docker-compose -f docker-compose.mac-m1.yml build --no-cache; then
        echo "✅ 标准构建成功"
    else
        echo "❌ 构建失败，请检查网络连接并重试"
        echo "建议："
        echo "1. 检查Docker Desktop是否有足够内存（推荐8GB+）"
        echo "2. 重启Docker Desktop"
        echo "3. 检查网络连接"
        exit 1
    fi
fi

echo "🚀 启动服务..."
docker-compose -f docker-compose.mac-m1.yml up -d

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 10

# 检查服务状态
echo "🔍 检查服务状态..."
if curl -s http://localhost:8000/api/health > /dev/null; then
    echo "✅ 后端服务正常"
else
    echo "❌ 后端服务启动失败"
fi

if curl -s http://localhost:3000 > /dev/null; then
    echo "✅ 前端服务正常"
else
    echo "❌ 前端服务启动失败"
fi

# 显示服务信息
echo ""
echo "🎉 部署完成！"
echo "=================================="
echo "前端地址: http://localhost:3000"
echo "后端API: http://localhost:8000"
echo "API文档: http://localhost:8000/docs"
echo ""
echo "📋 常用命令:"
echo "查看日志: docker-compose -f docker-compose.mac-m1.yml logs -f"
echo "停止服务: docker-compose -f docker-compose.mac-m1.yml down"
echo "重启服务: docker-compose -f docker-compose.mac-m1.yml restart"
echo ""
echo "🔧 如果遇到问题，请查看故障排除指南："
echo "cat MAC_M1_TROUBLESHOOTING.md"