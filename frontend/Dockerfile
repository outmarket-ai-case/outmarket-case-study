# Build context is the REPOSITORY ROOT, not frontend/ -- the image ships the
# project documentation, which lives outside this directory. Docker cannot read
# above its context, so the context is widened and trimmed by /.dockerignore
# instead of duplicating the markdown into frontend/.

# ---- build the static bundle
FROM node:22-alpine AS builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
# `npm ci` when a lockfile exists (reproducible); fall back for a fresh clone.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY frontend/tsconfig.json frontend/vite.config.ts frontend/index.html ./
COPY frontend/src ./src
RUN npm run build

# ---- serve it
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
# Default points at the compose service; Helm overrides it per environment.
ENV BACKEND_HOST=backend:8000
COPY --from=builder /app/dist /usr/share/nginx/html

# Ship the docs with the running system, not just with the repository: the app
# serves them at /docs and renders them in the UI.
COPY docs/ /usr/share/nginx/html/docs/
COPY README.md /usr/share/nginx/html/docs/README.md

COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
USER 101
EXPOSE 8080
# 127.0.0.1, not localhost: nginx listens on IPv4 only, and in this image
# `localhost` resolves to ::1 first -- which makes the healthcheck fail with
# "connection refused" while the service is serving traffic perfectly well.
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/nginx-health >/dev/null || exit 1
