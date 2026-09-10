#!/usr/bin/env bash
# Turn the Terraform platform contract into a Helm values file.
#
# This ~30-line script is the entire seam between "infrastructure" and
# "delivery". Terraform emits one JSON object; this maps it to values keys;
# Helm consumes them. Nothing else in the pipeline knows which cloud it is on.
#
#   usage: scripts/platform-values.sh <cloud> <env> [out]
set -euo pipefail

CLOUD="${1:?usage: platform-values.sh <cloud> <env> [out]}"
ENVIRONMENT="${2:?usage: platform-values.sh <cloud> <env> [out]}"
OUT="${3:-/dev/stdout}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK="${ROOT}/infra/terraform/stacks/${CLOUD}"

command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

PLATFORM="$(terraform -chdir="${STACK}" output -json platform)"

schema="$(jq -r '.schema_version' <<<"${PLATFORM}")"
if [[ "${schema}" != "1.0" ]]; then
  echo "unsupported platform contract schema '${schema}'; this script speaks 1.0" >&2
  exit 1
fi

actual_env="$(jq -r '.environment' <<<"${PLATFORM}")"
if [[ "${actual_env}" != "${ENVIRONMENT}" ]]; then
  echo "refusing to render: stack holds env '${actual_env}', you asked for '${ENVIRONMENT}'" >&2
  exit 1
fi

# The mapping. `gcpProjectId` is the one derived key: GCP's secret store needs
# the project explicitly, and in the contract that lives under account_id.
jq '{
  platform: {
    cloud: .cloud,
    environment: .environment,
    region: .region,
    accountId: .account_id,
    gcpProjectId: (if .cloud == "gcp" then .account_id else "" end),
    cluster: {
      name: .cluster.name,
      ingressClass: .cluster.ingress_class,
      storageClass: .cluster.storage_class,
    },
    registry: {
      host: .registry.host,
      repositoryPrefix: .registry.repository_prefix,
    },
    database: {
      host: .database.host,
      port: .database.port,
      name: .database.name,
      username: .database.username,
      secretRef: .database.secret_ref,
      secretBackend: .database.secret_backend,
    },
    serviceAccountAnnotations: .service_account_annotations,
    appHostname: .app_hostname,
  }
}' <<<"${PLATFORM}" > "${OUT}"
