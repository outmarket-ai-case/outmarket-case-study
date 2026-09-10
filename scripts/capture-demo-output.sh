#!/usr/bin/env bash
# Capture the real command output that the demo video replays.
#
# Run this against a live cluster before scripts/record-demo.mjs. Every panel in
# the video comes from a file written here, so the video can never drift from
# what the tools actually print -- re-run it and the video re-records itself
# from fresh output.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/demo/captures"
APP="${APP:-http://localhost:8081}"
NAMESPACE="${NAMESPACE:-idea-board-local}"
RELEASE="${RELEASE:-idea-board}"

# Put the project's virtualenv on PATH so the captured command lines read as a
# developer would actually type them, not as an absolute interpreter path.
export PATH="${ROOT}/backend/.venv/bin:${PATH}"

mkdir -p "${OUT}"

# capture <name> <displayed command> -- <command to actually run>
capture() {
  local name="$1" shown="$2"; shift 2
  [ "${1:-}" = "--" ] && shift
  {
    echo "\$ ${shown}"
    "$@" 2>&1 || true
  } | sed -e 's/\x1b\[[0-9;]*m//g' > "${OUT}/${name}.txt"
  printf "  %-22s %3s lines\n" "${name}" "$(wc -l < "${OUT}/${name}.txt" | tr -d ' ')"
}

echo "capturing into ${OUT}"

capture 01-pods "kubectl -n ${NAMESPACE} get pods" -- \
  kubectl -n "${NAMESPACE}" get pods

capture 02-ideas "curl -s ${APP}/api/ideas | python -m json.tool" -- \
  bash -c "curl -s '${APP}/api/ideas' | python -m json.tool"

capture 03-tfvars "diff infra/terraform/envs/aws-dev.tfvars infra/terraform/envs/gcp-dev.tfvars" -- \
  bash -c "diff '${ROOT}/infra/terraform/envs/aws-dev.tfvars' '${ROOT}/infra/terraform/envs/gcp-dev.tfvars'"

capture 04-contract "sed -n '/^jq/,/^}/p' scripts/platform-values.sh" -- \
  bash -c "sed -n \"/^jq '{/,/^}'/p\" '${ROOT}/scripts/platform-values.sh' | head -26"

capture 05-gate-healthy "python -m aiops gate --namespace ${NAMESPACE} --format text" -- \
  bash -c "cd '${ROOT}/ai' && env -u ANTHROPIC_API_KEY python -m aiops gate --namespace '${NAMESPACE}' --release '${RELEASE}' --format text 2>/dev/null"

capture 06-gate-crash "python -m aiops gate --fixture tests/fixtures/crash_loop.json --format text" -- \
  bash -c "cd '${ROOT}/ai' && env -u ANTHROPIC_API_KEY python -m aiops gate --namespace demo --release idea-board --fixture tests/fixtures/crash_loop.json --format text 2>/dev/null"

capture 07-gate-inject "python -m aiops gate --fixture tests/fixtures/prompt_injection.json --format text" -- \
  bash -c "cd '${ROOT}/ai' && env -u ANTHROPIC_API_KEY python -m aiops gate --namespace demo --release idea-board --fixture tests/fixtures/prompt_injection.json --format text 2>/dev/null"

capture 08-planenv "python -m aiops plan-env --spec platform.yaml --env prod --cloud aws" -- \
  bash -c "cd '${ROOT}/ai' && env -u ANTHROPIC_API_KEY python -m aiops plan-env --spec ../platform.yaml --env prod --cloud aws 2>/dev/null | head -18"

capture 23-cost "python -m aiops cost --spec platform.yaml" -- \
  bash -c "cd '${ROOT}/ai' && python -m aiops cost --spec ../platform.yaml 2>/dev/null | head -20"

capture 09-tests "cd ai && python -m pytest -q" -- \
  bash -c "cd '${ROOT}/ai' && python -m pytest -q 2>&1 | tail -3"

capture 10-ingress "helm template ... --values ci/\$cloud-dev-values.yaml | grep ingressClassName" -- \
  bash -c "for c in aws gcp; do printf '%-4s -> ' \$c; helm template idea-board '${ROOT}/deploy/helm/idea-board' --values '${ROOT}/deploy/helm/idea-board/ci/'\$c'-dev-values.yaml' 2>/dev/null | grep -m1 'ingressClassName:' | sed 's/^ *//'; done"

capture 11-registry "helm template ... | grep -m1 'image:'" -- \
  bash -c "for c in aws gcp; do printf '%-4s -> ' \$c; helm template idea-board '${ROOT}/deploy/helm/idea-board' --values '${ROOT}/deploy/helm/idea-board/ci/'\$c'-dev-values.yaml' 2>/dev/null | grep -m1 'image:' | sed 's/^ *//'; done"

echo "done"

# ---------------------------------------------------------------------------
# Rollout sequence: trigger a real deploy and sample the pods as they come up,
# so the video can replay an actual rollout rather than a staged screenshot.
# Set ROLLOUT=1 to include it (it restarts the running deployment).
# ---------------------------------------------------------------------------
if [ "${ROLLOUT:-0}" = "1" ]; then
  echo "triggering a real rollout and sampling pods"

  # Sequential, deliberately. An earlier version ran `helm upgrade --atomic`
  # and `rollout restart` concurrently and the two fought each other -- helm
  # timed out waiting for a rollout that a second controller kept restarting.
  {
    echo "\$ helm upgrade --install idea-board deploy/helm/idea-board --atomic --wait"
    helm upgrade --install "${RELEASE}" "${ROOT}/deploy/helm/idea-board" \
      -n "${NAMESPACE}" --values "${ROOT}/deploy/helm/idea-board/ci/minikube-values.yaml" \
      --wait --timeout 5m 2>&1 | sed -n '1,10p'
  } > "${OUT}/20-helm-upgrade.txt"

  # The local image tag is mutable, so an unchanged release leaves the pod spec
  # identical and nothing rolls. A restart is what picks up the rebuilt image --
  # cloud environments use an immutable sha tag and never need this.
  kubectl -n "${NAMESPACE}" rollout restart deploy/"${RELEASE}"-backend deploy/"${RELEASE}"-frontend >/dev/null 2>&1 || true

  # Sample in the background while `rollout status` blocks in the foreground,
  # so the snapshots cover the whole rollout however long it takes. On a
  # memory-constrained local node a pod can take 90s just to bind its port, so
  # a fixed short window would stop sampling before the rollout finished.
  (
    for i in $(seq 1 ${ROLLOUT_FRAMES:-20}); do
      {
        echo "\$ kubectl -n ${NAMESPACE} get pods            # t+$(( (i-1) * 4 ))s"
        kubectl -n "${NAMESPACE}" get pods 2>&1
      } | sed -e 's/\x1b\[[0-9;]*m//g' > "$(printf '%s/21-rollout-%02d.txt' "${OUT}" "${i}")"
      sleep 4
    done
  ) &
  SAMPLER_PID=$!

  {
    echo "\$ kubectl -n ${NAMESPACE} rollout status deploy/${RELEASE}-backend"
    kubectl -n "${NAMESPACE}" rollout status deploy/"${RELEASE}"-backend --timeout=8m 2>&1 | tail -3
    echo "\$ kubectl -n ${NAMESPACE} rollout status deploy/${RELEASE}-frontend"
    kubectl -n "${NAMESPACE}" rollout status deploy/"${RELEASE}"-frontend --timeout=8m 2>&1 | tail -2
  } > "${OUT}/22-rollout-status.txt"

  wait "${SAMPLER_PID}" 2>/dev/null || true

  printf "  %-22s %s snapshots\n" "21-rollout" "$(ls "${OUT}"/21-rollout-*.txt | wc -l | tr -d ' ')"
fi
