# syntax=docker/dockerfile:1
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# The unprivileged nginx image runs as a non-root user on port 8080, so the
# container needs no Linux capabilities and works with a read-only root.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget --quiet --spider http://127.0.0.1:8080/ || exit 1
