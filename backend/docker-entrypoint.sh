#!/bin/sh
# Runs migrations then serves. In Kubernetes migrations run as a separate Job
# (RUN_MIGRATIONS=false on the Deployment) so N replicas do not race.
set -e

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  echo "running alembic migrations..."
  alembic upgrade head
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}"
