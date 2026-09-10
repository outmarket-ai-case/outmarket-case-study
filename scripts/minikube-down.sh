#!/usr/bin/env bash
# Remove the release and its namespace. Leaves the cluster itself running --
# `minikube delete` if you want that gone too.
set -euo pipefail

NAMESPACE="${NAMESPACE:-idea-board-local}"
RELEASE="${RELEASE_NAME:-idea-board}"

helm uninstall "${RELEASE}" -n "${NAMESPACE}" 2>/dev/null || true
kubectl delete namespace "${NAMESPACE}" --ignore-not-found
echo "removed ${RELEASE} and namespace ${NAMESPACE} (cluster left running)"
