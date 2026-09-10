#!/usr/bin/env bash
# Bring the whole stack up on a local Kubernetes cluster.
#
#   scripts/minikube-up.sh
#
# This is the same Helm chart, the same images and the same application that
# ship to EKS and GKE. Only the platform-contract values differ
# (deploy/helm/idea-board/ci/minikube-values.yaml) -- which is the point:
# adding a third target required a values file, not a chart change.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${NAMESPACE:-idea-board-local}"
RELEASE="${RELEASE_NAME:-idea-board}"
VALUES="${ROOT}/deploy/helm/idea-board/ci/minikube-values.yaml"
CPUS="${MINIKUBE_CPUS:-2}"
MEMORY="${MINIKUBE_MEMORY:-3000mb}"

log() { printf '\n==> %s\n' "$*"; }

for tool in minikube kubectl helm docker; do
  command -v "$tool" >/dev/null || { echo "$tool is required" >&2; exit 1; }
done

log "ensuring the minikube cluster is running"
if [ "$(minikube status --format='{{.Host}}' 2>/dev/null || true)" != "Running" ]; then
  minikube start --driver=docker --cpus="${CPUS}" --memory="${MEMORY}" --wait=all
fi
minikube addons enable ingress >/dev/null
kubectl -n ingress-nginx rollout status deploy/ingress-nginx-controller --timeout=5m

log "building images inside the cluster's docker daemon"
# No registry involved: the images are built where the kubelet can already see
# them, which is why the values file sets pullPolicy=Never.
eval "$(minikube docker-env)"
docker build -t idea-board-backend:local "${ROOT}/backend"
docker build -t idea-board-frontend:local "${ROOT}/frontend"

log "creating namespace ${NAMESPACE}"
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

log "starting the in-cluster database"
kubectl apply -n "${NAMESPACE}" -f "${ROOT}/deploy/local/postgres.yaml"
kubectl -n "${NAMESPACE}" rollout status statefulset/idea-board-postgres --timeout=5m

log "deploying ${RELEASE}"
# --atomic rolls the release back automatically if the migration hook or a
# readiness probe fails, so a broken deploy never leaves a half-applied state.
helm upgrade --install "${RELEASE}" "${ROOT}/deploy/helm/idea-board" \
  --namespace "${NAMESPACE}" \
  --values "${VALUES}" \
  --wait --timeout 10m --atomic

# The local tag is mutable, so a rebuilt image leaves the Deployment spec
# unchanged and Helm has nothing to roll. Cloud deploys use an immutable
# sha-based tag and never need this.
log "restarting pods to pick up freshly built images"
kubectl -n "${NAMESPACE}" rollout restart deploy/"${RELEASE}"-backend deploy/"${RELEASE}"-frontend
kubectl -n "${NAMESPACE}" rollout status deploy/"${RELEASE}"-backend --timeout=5m
kubectl -n "${NAMESPACE}" rollout status deploy/"${RELEASE}"-frontend --timeout=5m

log "cluster state"
kubectl -n "${NAMESPACE}" get pods,svc,ingress

cat <<EOF

==> The stack is up in namespace ${NAMESPACE}.

Reach it either way:

  1. Port-forward (works everywhere, no sudo):
       kubectl -n ${NAMESPACE} port-forward svc/${RELEASE}-frontend 8081:80
       open http://localhost:8081

  2. Through the ingress (needs a hosts entry and, on the docker driver, a tunnel):
       minikube tunnel                # in a second terminal, asks for sudo
       echo "127.0.0.1 idea-board.local" | sudo tee -a /etc/hosts
       open http://idea-board.local

Judge the release the way CI does:
  cd ai && python -m aiops gate --namespace ${NAMESPACE} --release ${RELEASE}

Tear it down:
  scripts/minikube-down.sh
EOF
