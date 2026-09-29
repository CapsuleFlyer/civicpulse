#!/bin/sh
# Build once, deploy many — for the frontend.
#
# Vite inlines import.meta.env at build time, so anything environment-specific
# baked into the bundle would make this image single-environment. Instead the
# image ships with no environment knowledge at all and this script writes the
# two things that vary — the API origin nginx proxies to, and the config the
# browser reads — at container start.
set -eu

: "${BACKEND_ORIGIN:=http://backend:8000}"
: "${API_BASE_URL:=/api}"
: "${APP_ENVIRONMENT:=development}"
: "${APP_VERSION:=dev}"

export BACKEND_ORIGIN

envsubst '${BACKEND_ORIGIN}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf

cat > /usr/share/nginx/html/config.js <<CONFIG
window.__CIVICPULSE__ = {
  apiBaseUrl: "${API_BASE_URL}",
  environment: "${APP_ENVIRONMENT}",
  version: "${APP_VERSION}"
};
CONFIG

echo "civicpulse-frontend: proxying /api to ${BACKEND_ORIGIN}, apiBaseUrl=${API_BASE_URL}"
exec "$@"
