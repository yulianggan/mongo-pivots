# 简化后端的Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制简化后端文件
COPY simple_backend.py /app/

# 安装Python依赖
RUN pip install fastapi uvicorn[standard] pydantic

# 设置环境变量
ENV PORT=8000
ENV PYTHONPATH=/app

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "simple_backend.py"]