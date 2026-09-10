"""Evidence collection for the release gate.

Two collectors behind one interface: `KubectlCollector` talks to a live
cluster, `FixtureCollector` replays a recorded JSON snapshot. The fixture
collector is what makes the gate testable -- every scenario the gate has to
decide (crash loop, slow rollout, elevated 5xx, healthy) is a checked-in file,
so the decision logic is covered without a cluster.

The collectors use only `kubectl`. There is no cloud SDK here, which is why the
gate works unchanged on EKS, GKE, or a local kind cluster.
"""

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("aiops.evidence")


@dataclass
class Evidence:
    """Everything the gate knows about a release.

    `signals` are machine-comparable numbers the deterministic rules use;
    `raw` holds the text an LLM reads when the numbers are inconclusive.
    """

    namespace: str
    release: str
    signals: dict[str, float | int | bool] = field(default_factory=dict)
    raw: dict[str, str] = field(default_factory=dict)
    collection_errors: list[str] = field(default_factory=list)

    def as_prompt(self, max_chars_per_source: int = 3000) -> str:
        parts = [f"Release: {self.release} in namespace {self.namespace}", "", "## Measured signals"]
        for key, value in sorted(self.signals.items()):
            parts.append(f"- {key}: {value}")
        if self.collection_errors:
            parts += ["", "## Evidence that could not be collected"]
            parts += [f"- {err}" for err in self.collection_errors]
        for source, text in sorted(self.raw.items()):
            body = text.strip()[:max_chars_per_source] or "(empty)"
            parts += ["", f"## {source}", "```", body, "```"]
        return "\n".join(parts)


class FixtureCollector:
    """Replays a recorded snapshot: {"signals": {...}, "raw": {...}}."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def collect(self, namespace: str, release: str) -> Evidence:
        data = json.loads(self.path.read_text())
        return Evidence(
            namespace=namespace,
            release=release,
            signals=data.get("signals", {}),
            raw=data.get("raw", {}),
            collection_errors=data.get("collection_errors", []),
        )


class KubectlCollector:
    def __init__(self, timeout: int = 30, event_window_seconds: int = 600) -> None:
        self.timeout = timeout
        self.event_window_seconds = event_window_seconds

    def collect(self, namespace: str, release: str) -> Evidence:
        ev = Evidence(namespace=namespace, release=release)

        if shutil.which("kubectl") is None:
            ev.collection_errors.append("kubectl not found on PATH")
            return ev

        selector = f"app.kubernetes.io/instance={release}"

        pods_json = self._run(["get", "pods", "-n", namespace, "-l", selector, "-o", "json"])
        if pods_json:
            self._read_pods(ev, pods_json)

        events_json = self._run([
            "get", "events", "-n", namespace,
            "--field-selector", "type=Warning", "-o", "json",
        ])
        if events_json:
            recent = _recent_warnings(events_json, self.event_window_seconds)
            # Only warnings from this rollout count. A namespace keeps events for
            # an hour, and judging a fresh release on a failure from the previous
            # one is how a gate earns a reputation for crying wolf.
            ev.raw["warning_events"] = "\n".join(recent[-25:])
            ev.signals["recent_warning_events"] = len(recent)

        for component in ("backend", "frontend"):
            deploy = f"{release}-{component}"
            status = self._run(["rollout", "status", f"deploy/{deploy}", "-n", namespace, "--timeout=1s"])
            ev.raw[f"rollout_{component}"] = status or f"rollout status for {deploy} unavailable"

        logs = self._run([
            "logs", "-n", namespace, "-l", f"{selector},idea-board.io/component=backend",
            "--tail", "80", "--all-containers", "--prefix",
        ])
        if logs:
            ev.raw["backend_logs"] = logs
            ev.signals["log_error_lines"] = sum(
                1 for line in logs.splitlines() if '"level":"ERROR"' in line or "Traceback" in line
            )

        metrics = self._run([
            "exec", "-n", namespace, "-c", "backend",
            f"deploy/{release}-backend", "--", "curl", "-fsS", "http://localhost:8000/metrics",
        ])
        if metrics:
            rate = parse_http_error_rate(metrics)
            if rate is not None:
                ev.signals["http_error_rate"] = rate
            ev.raw["metrics_summary"] = _summarise_metrics(metrics)

        return ev

    def _run(self, args: list[str]) -> str | None:
        try:
            proc = subprocess.run(
                ["kubectl", *args],
                capture_output=True, text=True, timeout=self.timeout, check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            log.warning("kubectl %s failed: %s", args[0], exc)
            return None
        if proc.returncode != 0:
            return proc.stdout.strip() or None
        return proc.stdout

    @staticmethod
    def _read_pods(ev: Evidence, pods_json: str) -> None:
        try:
            pods = json.loads(pods_json).get("items", [])
        except json.JSONDecodeError as exc:
            ev.collection_errors.append(f"could not parse pod JSON: {exc}")
            return

        ready = restarts = 0
        crash_loop = False
        summary: list[str] = []

        for pod in pods:
            name = pod["metadata"]["name"]
            statuses = pod.get("status", {}).get("containerStatuses") or []
            pod_ready = bool(statuses) and all(c.get("ready") for c in statuses)
            ready += int(pod_ready)
            pod_restarts = sum(c.get("restartCount", 0) for c in statuses)
            restarts += pod_restarts

            reasons = [
                (c.get("state", {}).get("waiting") or {}).get("reason", "")
                for c in statuses
            ]
            if "CrashLoopBackOff" in reasons:
                crash_loop = True
            if "ImagePullBackOff" in reasons or "ErrImagePull" in reasons:
                ev.signals["image_pull_failure"] = True

            summary.append(
                f"{name}: phase={pod['status'].get('phase')} ready={pod_ready} "
                f"restarts={pod_restarts} waiting={[r for r in reasons if r] or 'none'}"
            )

        ev.signals["pods_total"] = len(pods)
        ev.signals["pods_ready"] = ready
        ev.signals["restart_count"] = restarts
        ev.signals["crash_loop"] = crash_loop
        ev.raw["pod_status"] = "\n".join(summary) or "(no pods matched the release selector)"


# Event reasons/messages that are expected during a healthy rollout. Filtering
# them is not cosmetic: a startup probe failing while a container boots is the
# probe doing its job, and counting it as a warning makes EVERY deploy triage
# as ambiguous -- which would send every rollout to the model and throw away the
# cost and latency benefit of having deterministic rules at all.
#
# Readiness and liveness failures are deliberately NOT here: those mean a
# container that was serving has gone bad, which is exactly what the gate is for.
_BENIGN_EVENT_SUBSTRINGS = ("startup probe failed",)


def _is_benign(message: str) -> bool:
    lowered = message.lower()
    return any(pattern in lowered for pattern in _BENIGN_EVENT_SUBSTRINGS)


def _recent_warnings(events_json: str, window_seconds: int) -> list[str]:
    """Warning events from this rollout, excluding expected startup noise."""
    from datetime import datetime, timedelta, timezone

    try:
        items = json.loads(events_json).get("items", [])
    except json.JSONDecodeError:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    out: list[tuple[datetime, str]] = []

    for item in items:
        stamp = item.get("lastTimestamp") or item.get("eventTime") or item.get("firstTimestamp")
        if not stamp:
            continue
        try:
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when < cutoff:
            continue
        message = item.get("message", "").strip()
        if _is_benign(message):
            continue
        obj = item.get("involvedObject", {})
        out.append((
            when,
            f"{stamp} {item.get('reason', '?')} "
            f"{obj.get('kind', '?')}/{obj.get('name', '?')}: {message}",
        ))

    return [line for _, line in sorted(out)]


_METRIC_LINE = re.compile(
    r'^http_requests_total\{[^}]*status="(?P<status>[^"]+)"[^}]*\}\s+(?P<value>[0-9.eE+-]+)'
)


def parse_http_error_rate(metrics_text: str) -> float | None:
    """Fraction of requests that returned 5xx, from Prometheus text format.

    Returns None when there is no traffic yet -- an important distinction: zero
    requests is not the same as zero errors, and treating it as healthy is how
    a broken release slips through a quiet window.
    """
    total = errors = 0.0
    for line in metrics_text.splitlines():
        match = _METRIC_LINE.match(line.strip())
        if not match:
            continue
        try:
            value = float(match.group("value"))
        except ValueError:
            continue
        status = match.group("status")
        total += value
        # The instrumentator emits either exact codes or Nxx buckets.
        if status.startswith("5"):
            errors += value

    if total <= 0:
        return None
    return round(errors / total, 5)


def _summarise_metrics(metrics_text: str) -> str:
    keep = [
        line for line in metrics_text.splitlines()
        if line.startswith(("http_requests_total", "http_request_duration_seconds_count",
                            "http_request_duration_seconds_sum", "process_resident_memory_bytes"))
    ]
    return "\n".join(keep[:40]) or "(no relevant metrics)"
