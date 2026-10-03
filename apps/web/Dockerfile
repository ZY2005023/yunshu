# =============================================================================
# 云舒 · 前端镜像
#
# 阶段 1 用 Node 打包出静态文件，阶段 2 用 nginx 托管并反代后端。
# =============================================================================

# ---------- 阶段 1：构建 ----------
FROM node:22-alpine AS builder
WORKDIR /build

COPY package.json package-lock.json* ./
# 有 lock 文件走 ci（可复现），没有就退回 install
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .
RUN npm run build

# ---------- 阶段 2：运行 ----------
FROM nginx:1.27-alpine

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
