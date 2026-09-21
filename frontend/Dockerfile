# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Build stage: Node compiles TypeScript and bundles. Nothing from this stage
# survives into the image that runs in production.
# ---------------------------------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /build

# Lockfile first: dependency installs are cached until the lockfile changes.
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY tsconfig.json vite.config.ts index.html ./
COPY public ./public
COPY src ./src

# Type errors fail the build here rather than surfacing as a blank page later.
RUN npx tsc --noEmit && npm run build -- --mode production

# ---------------------------------------------------------------------------
# Runtime: nginx and 200 kB of static files. No Node, no node_modules, no
# source — which is both a size win and a much smaller attack surface.
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

RUN apk add --no-cache gettext curl \
 && addgroup -g 10001 -S civic \
 && adduser -u 10001 -S civic -G civic

COPY --from=build /build/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Port 8080, not 80: a non-root process cannot bind a privileged port.
RUN sed -i 's|^user .*|# user directive removed: the container runs as civic|' /etc/nginx/nginx.conf \
 && sed -i 's|/var/run/nginx.pid|/tmp/nginx.pid|' /etc/nginx/nginx.conf \
 && chmod +x /usr/local/bin/docker-entrypoint.sh \
 && mkdir -p /var/cache/nginx /tmp \
 && chown -R civic:civic /var/cache/nginx /usr/share/nginx/html /etc/nginx/conf.d

USER civic
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/healthz || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
