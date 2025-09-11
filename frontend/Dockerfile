# 多阶段构建 - 最简单有效的方案
FROM node:18-alpine as builder

WORKDIR /app

# 只复制package文件，避免平台兼容问题
COPY package.json ./

# 强制重新生成package-lock并安装
RUN npm install --force --no-optional

# 复制源代码
COPY . .

# 构建项目（跳过类型检查）
RUN npm run build:no-check

# 生产阶段
FROM nginx:alpine

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制nginx配置
COPY nginx.conf /etc/nginx/nginx.conf

# 设置环境变量
ENV API_BASE=http://localhost:8000

# 创建配置脚本
COPY docker-entrypoint.sh /docker-entrypoint.d/40-gen-config.sh
RUN chmod +x /docker-entrypoint.d/40-gen-config.sh

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]