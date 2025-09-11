#!/bin/bash

# =============================================================================
# Mongo Join Pivot - 一键部署脚本
# =============================================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查依赖
check_dependencies() {
    log_info "检查系统依赖..."
    
    # 检查Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi
    
    # 检查Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose 未安装，请先安装 Docker Compose"
        exit 1
    fi
    
    log_success "系统依赖检查完成"
}

# 环境配置
setup_environment() {
    log_info "设置环境配置..."
    
    if [ ! -f .env ]; then
        log_info "创建 .env 配置文件..."
        cp .env.example .env
        log_warning "请编辑 .env 文件配置您的环境变量"
        log_warning "特别注意配置端口和数据库连接信息"
    else
        log_info ".env 文件已存在"
    fi
}

# 创建必要目录
create_directories() {
    log_info "创建必要的目录..."
    
    mkdir -p data
    mkdir -p temp
    mkdir -p logs
    
    log_success "目录创建完成"
}

# 部署服务
deploy_services() {
    local mode=$1
    
    log_info "开始部署服务 (模式: $mode)..."
    
    case $mode in
        "dev")
            log_info "以开发模式部署..."
            docker-compose up --build
            ;;
        "prod")
            log_info "以生产模式部署..."
            docker-compose up -d --build
            ;;
        "with-db")
            log_info "部署包含MongoDB数据库..."
            docker-compose --profile with-db up -d --build
            ;;
        *)
            log_error "未知的部署模式: $mode"
            exit 1
            ;;
    esac
}

# 健康检查
health_check() {
    log_info "执行服务健康检查..."
    
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        log_info "健康检查尝试 $attempt/$max_attempts..."
        
        # 检查后端服务
        if curl -f http://localhost:${BACKEND_PORT:-8000}/api/health &> /dev/null; then
            log_success "后端服务健康检查通过"
            break
        fi
        
        if [ $attempt -eq $max_attempts ]; then
            log_error "服务健康检查失败，请检查日志"
            docker-compose logs
            exit 1
        fi
        
        sleep 10
        ((attempt++))
    done
}

# 显示部署信息
show_deployment_info() {
    log_success "=========================================="
    log_success "🎉 部署完成！"
    log_success "=========================================="
    log_info "服务访问地址："
    log_info "  前端应用: http://localhost:${FRONTEND_PORT:-3000}"
    log_info "  后端API:  http://localhost:${BACKEND_PORT:-8000}"
    log_info "  API文档:  http://localhost:${BACKEND_PORT:-8000}/api/docs"
    log_success "=========================================="
    log_info "常用命令："
    log_info "  查看日志: docker-compose logs -f"
    log_info "  停止服务: docker-compose down"
    log_info "  重启服务: docker-compose restart"
    log_success "=========================================="
}

# 清理函数
cleanup() {
    log_info "执行清理操作..."
    docker-compose down
    docker system prune -f
    log_success "清理完成"
}

# 帮助信息
show_help() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  dev      开发模式部署 (前台运行)"
    echo "  prod     生产模式部署 (后台运行)"
    echo "  with-db  部署包含MongoDB数据库"
    echo "  health   执行健康检查"
    echo "  cleanup  清理Docker资源"
    echo "  help     显示帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 dev      # 开发模式部署"
    echo "  $0 prod     # 生产模式部署"
    echo "  $0 with-db  # 包含数据库部署"
}

# 主函数
main() {
    local command=${1:-prod}
    
    case $command in
        "dev"|"prod"|"with-db")
            check_dependencies
            setup_environment
            create_directories
            
            # 读取环境变量
            source .env 2>/dev/null || true
            
            deploy_services $command
            
            if [ "$command" != "dev" ]; then
                sleep 5
                health_check
                show_deployment_info
            fi
            ;;
        "health")
            source .env 2>/dev/null || true
            health_check
            ;;
        "cleanup")
            cleanup
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            log_error "未知命令: $command"
            show_help
            exit 1
            ;;
    esac
}

# 捕获退出信号
trap 'log_info "部署脚本被中断"' INT TERM

# 执行主函数
main "$@"