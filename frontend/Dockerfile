# ---- build the static bundle
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
# `npm ci` when a lockfile exists (reproducible); fall back for a fresh clone.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
RUN npm run build

# ---- serve it
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
# Default points at the compose service; Helm overrides it per environment.
ENV BACKEND_HOST=backend:8000
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
USER 101
EXPOSE 8080
# 127.0.0.1, not localhost: nginx listens on IPv4 only, and in this image
# `localhost` resolves to ::1 first -- which makes the healthcheck fail with
# "connection refused" while the service is serving traffic perfectly well.
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/nginx-health >/dev/null || exit 1
