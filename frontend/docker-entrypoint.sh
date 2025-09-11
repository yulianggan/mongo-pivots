#!/bin/sh

# 替换环境变量
envsubst '${API_BASE}' < /etc/nginx/nginx.conf > /tmp/nginx.conf
mv /tmp/nginx.conf /etc/nginx/nginx.conf

# 生成前端配置文件
cat > /usr/share/nginx/html/config.js << EOF
window.APP_CONFIG = {
  API_BASE_URL: "${API_BASE}"
};
EOF

echo "Frontend configuration generated with API_BASE=${API_BASE}"