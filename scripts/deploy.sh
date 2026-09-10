#!/usr/bin/env bash
# One deploy path for every cloud.
#
#   scripts/deploy.sh aws dev sha-abc1234
#   scripts/deploy.sh gcp dev sha-abc1234
#
# Note what is NOT here: no `if aws then ... elif gcp then ...`. The two
# cloud-specific steps (kubeconfig, registry login) are strings read out of the
# Terraform contract and executed verbatim.
set -euo pipefail

CLOUD="${1:?usage: deploy.sh <cloud> <env> <image-tag> [extra helm values file...]}"
ENVIRONMENT="${2:?usage: deploy.sh <cloud> <env> <image-tag> [extra helm values file...]}"
IMAGE_TAG="${3:?usage: deploy.sh <cloud> <env> <image-tag> [extra helm values file...]}"
shift 3

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK="${ROOT}/infra/terraform/stacks/${CLOUD}"
RELEASE="${RELEASE_NAME:-idea-board}"
NAMESPACE="${NAMESPACE:-idea-board-${ENVIRONMENT}}"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT

PLATFORM="$(terraform -chdir="${STACK}" output -json platform)"

echo "==> authenticating to the ${CLOUD} cluster"
eval "$(jq -r '.cluster.kubeconfig_command' <<<"${PLATFORM}")"

echo "==> rendering the platform contract into Helm values"
"${ROOT}/scripts/platform-values.sh" "${CLOUD}" "${ENVIRONMENT}" "${WORKDIR}/platform-values.yaml"

VALUE_ARGS=(--values "${WORKDIR}/platform-values.yaml")
for extra in "$@"; do
  VALUE_ARGS+=(--values "${extra}")
done

echo "==> deploying ${RELEASE} @ ${IMAGE_TAG} to ${NAMESPACE}"
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install "${RELEASE}" "${ROOT}/deploy/helm/idea-board" \
  --namespace "${NAMESPACE}" \
  "${VALUE_ARGS[@]}" \
  --set "image.tag=${IMAGE_TAG}" \
  --wait --timeout 10m \
  --atomic

echo "==> deployed. address:"
kubectl -n "${NAMESPACE}" get ingress "${RELEASE}" \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}{.status.loadBalancer.ingress[0].ip}{"\n"}' || true
