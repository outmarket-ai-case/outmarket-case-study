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

capture 09-tests "cd ai && python -m pytest -q" -- \
  bash -c "cd '${ROOT}/ai' && python -m pytest -q 2>&1 | tail -3"

capture 10-ingress "helm template ... --values ci/\$cloud-dev-values.yaml | grep ingressClassName" -- \
  bash -c "for c in aws gcp; do printf '%-4s -> ' \$c; helm template idea-board '${ROOT}/deploy/helm/idea-board' --values '${ROOT}/deploy/helm/idea-board/ci/'\$c'-dev-values.yaml' 2>/dev/null | grep -m1 'ingressClassName:' | sed 's/^ *//'; done"

capture 11-registry "helm template ... | grep -m1 'image:'" -- \
  bash -c "for c in aws gcp; do printf '%-4s -> ' \$c; helm template idea-board '${ROOT}/deploy/helm/idea-board' --values '${ROOT}/deploy/helm/idea-board/ci/'\$c'-dev-values.yaml' 2>/dev/null | grep -m1 'image:' | sed 's/^ *//'; done"

echo "done"
