#!/bin/sh
# Migrations run here, once, before the server starts — not inside application
# startup code, where every replica would race every other replica.
# RUN_MIGRATIONS=0 in Kubernetes, where a Job owns this instead.
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo '{"level":"INFO","logger":"entrypoint","message":"running migrations"}'
  alembic upgrade head
fi

if [ "${RUN_SEED:-0}" = "1" ]; then
  echo '{"level":"INFO","logger":"entrypoint","message":"seeding database"}'
  python -m app.seed
fi

exec "$@"
