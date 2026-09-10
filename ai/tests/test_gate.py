"""The gate's contract: deterministic signals decide the clear-cut cases, the
model only adjudicates the ambiguous middle, and the model can never overrule a
hard signal in either direction."""

from pathlib import Path

import pytest

from aiops.evidence import Evidence, FixtureCollector, parse_http_error_rate
from aiops.gate import (
    ROLLBACK_CONFIDENCE_FLOOR,
    Triage,
    apply_overrides,
    run_gate,
    to_markdown,
    triage,
)
from aiops.llm import LlmClient, LlmUnavailable
from aiops.models import EvidenceRef, Health, ReleaseVerdict

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> Evidence:
    return FixtureCollector(FIXTURES / f"{name}.json").collect("idea-board-test", "idea-board")


class StubLlm(LlmClient):
    """Stands in for the API. `verdict=None` simulates an outage."""

    def __init__(self, verdict: ReleaseVerdict | None):
        self._verdict = verdict
        self.calls = 0

    @property
    def available(self) -> bool:
        return self._verdict is not None

    def structured(self, **kwargs):  # type: ignore[override]
        self.calls += 1
        if self._verdict is None:
            raise LlmUnavailable("simulated outage")
        self._last_prompt = kwargs.get("user", "")
        return self._verdict


def verdict(**overrides) -> ReleaseVerdict:
    base = dict(
        health=Health.degraded,
        confidence=0.8,
        should_rollback=False,
        summary="one replica is lagging",
        evidence=[EvidenceRef(source="pod_status", excerpt="ready=False", interpretation="a pod is not ready")],
    )
    return ReleaseVerdict(**(base | overrides))


# --- triage ---------------------------------------------------------------
def test_healthy_release_never_reaches_the_model():
    llm = StubLlm(verdict(health=Health.failed, should_rollback=True, confidence=1.0))
    result = run_gate(load("healthy"), llm=llm)

    assert llm.calls == 0, "a clean release must not cost an API call"
    assert result.triage is Triage.clean
    assert result.source == "deterministic"
    assert result.verdict.health is Health.healthy
    assert not result.should_rollback
    assert result.exit_code == 0


def test_crash_loop_never_reaches_the_model():
    llm = StubLlm(verdict(health=Health.healthy, should_rollback=False))
    result = run_gate(load("crash_loop"), llm=llm)

    assert llm.calls == 0
    assert result.triage is Triage.hard_fail
    assert result.verdict.health is Health.failed
    assert result.should_rollback
    assert result.exit_code == 1


def test_mixed_signals_are_sent_to_the_model():
    llm = StubLlm(verdict())
    result = run_gate(load("ambiguous"), llm=llm)

    assert llm.calls == 1
    assert result.triage is Triage.ambiguous
    assert result.verdict.health is Health.degraded
    assert result.exit_code == 2


def test_no_traffic_is_not_treated_as_no_errors():
    """A release with zero requests has not been exercised. The error-rate
    parser returns None, and the gate must not read that as 0%."""
    assert parse_http_error_rate('http_requests_total{status="2xx"} 0.0') is None
    ev = load("healthy")
    ev.signals.pop("http_error_rate")
    ev.signals["pods_ready"] = 3  # not all ready either
    assert triage(ev)[0] is Triage.ambiguous


# --- the model cannot overrule a hard signal ------------------------------
def test_model_cannot_call_a_crash_looping_release_healthy():
    ev = load("crash_loop")
    result, overrides = apply_overrides(verdict(health=Health.healthy, should_rollback=False, confidence=1.0), ev)

    assert result.health is Health.failed
    assert result.should_rollback
    assert any("hard-fail signal" in o for o in overrides)


def test_prompt_injection_in_logs_cannot_flip_the_verdict():
    """The whole point of putting deterministic rules in front of the model:
    a log line that says 'report this as healthy' is powerless, because a
    crash loop is decided before the model is ever asked."""
    ev = load("prompt_injection")
    llm = StubLlm(verdict(health=Health.healthy, should_rollback=False, confidence=1.0))
    result = run_gate(ev, llm=llm)

    assert llm.calls == 0
    assert result.verdict.health is Health.failed
    assert result.should_rollback


def test_low_confidence_rollback_is_downgraded_to_an_alert():
    ev = load("ambiguous")
    result, overrides = apply_overrides(
        verdict(health=Health.degraded, should_rollback=True, confidence=ROLLBACK_CONFIDENCE_FLOOR - 0.1), ev
    )
    assert not result.should_rollback
    assert any("below the" in o for o in overrides)


def test_high_confidence_rollback_on_ambiguous_evidence_is_honoured():
    ev = load("ambiguous")
    result, overrides = apply_overrides(
        verdict(health=Health.failed, should_rollback=True, confidence=0.95), ev
    )
    assert result.should_rollback
    assert not any("below the" in o for o in overrides)


def test_failed_without_rollback_is_contradictory_and_corrected():
    ev = load("ambiguous")
    result, overrides = apply_overrides(verdict(health=Health.failed, should_rollback=False, confidence=0.9), ev)
    assert result.should_rollback
    assert any("implies rollback" in o for o in overrides)


def test_findings_without_a_cited_excerpt_are_dropped():
    ev = load("ambiguous")
    v = verdict(
        evidence=[
            EvidenceRef(source="pod_status", excerpt="ready=False", interpretation="real"),
            EvidenceRef(source="metrics", excerpt="   ", interpretation="unsupported claim"),
        ]
    )
    result, overrides = apply_overrides(v, ev)
    assert len(result.evidence) == 1
    assert any("no cited excerpt" in o for o in overrides)


# --- failure modes --------------------------------------------------------
def test_model_outage_does_not_roll_back_on_a_guess():
    result = run_gate(load("ambiguous"), llm=StubLlm(None))

    assert result.source == "deterministic"
    assert result.verdict.health is Health.degraded
    assert not result.should_rollback, "an LLM outage must never trigger a rollback"
    assert result.exit_code == 2


def test_model_outage_still_catches_a_hard_failure():
    result = run_gate(load("crash_loop"), llm=StubLlm(None))
    assert result.should_rollback
    assert result.exit_code == 1


def test_no_ai_flag_keeps_the_gate_fully_deterministic():
    llm = StubLlm(verdict())
    result = run_gate(load("ambiguous"), llm=llm, allow_ai=False)
    assert llm.calls == 0
    assert result.source == "deterministic"


def test_evidence_is_fenced_and_labelled_untrusted_in_the_prompt():
    llm = StubLlm(verdict())
    run_gate(load("ambiguous"), llm=llm)
    prompt = llm._last_prompt
    assert "untrusted" in prompt.lower()
    assert "```" in prompt


# --- reporting ------------------------------------------------------------
@pytest.mark.parametrize("fixture", ["healthy", "crash_loop", "ambiguous"])
def test_markdown_report_renders_for_every_outcome(fixture):
    ev = load(fixture)
    md = to_markdown(run_gate(ev, llm=StubLlm(verdict())), ev)
    assert "Release gate" in md and "Decided by" in md and ev.release in md


def test_metrics_error_rate_parsing():
    metrics = "\n".join([
        'http_requests_total{handler="/api/ideas",method="GET",status="2xx"} 180.0',
        'http_requests_total{handler="/api/ideas",method="POST",status="5xx"} 20.0',
        "# a comment that must be ignored",
        "process_resident_memory_bytes 1.234e+08",
    ])
    assert parse_http_error_rate(metrics) == 0.1


# --- stale-event filtering ------------------------------------------------
def test_only_warnings_from_this_rollout_are_collected():
    """A namespace keeps events for about an hour. Judging a fresh release on a
    failure from the previous one is how a gate earns a reputation for crying
    wolf, so old events are filtered out before triage sees them."""
    import json as _json
    from datetime import datetime, timedelta, timezone

    from aiops.evidence import _recent_warnings

    now = datetime.now(timezone.utc)
    payload = _json.dumps({
        "items": [
            {
                "lastTimestamp": (now - timedelta(minutes=90)).isoformat().replace("+00:00", "Z"),
                "reason": "BackOff", "message": "a failure from the previous release",
                "involvedObject": {"kind": "Pod", "name": "old-pod"},
            },
            {
                "lastTimestamp": (now - timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
                "reason": "Unhealthy", "message": "readiness probe failed",
                "involvedObject": {"kind": "Pod", "name": "new-pod"},
            },
        ]
    })

    recent = _recent_warnings(payload, window_seconds=900)
    assert len(recent) == 1
    assert "new-pod" in recent[0]


def test_unparseable_event_payload_degrades_quietly():
    from aiops.evidence import _recent_warnings

    assert _recent_warnings("not json", 900) == []
    assert _recent_warnings('{"items": [{"reason": "NoTimestamp"}]}', 900) == []


def test_startup_probe_noise_is_not_treated_as_a_warning():
    """Every rollout produces a failed startup probe while the container boots.
    Counting it would make every deploy ambiguous and send every rollout to the
    model, which defeats the purpose of deterministic triage."""
    import json as _json
    from datetime import datetime, timezone

    from aiops.evidence import _recent_warnings

    stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = _json.dumps({
        "items": [
            {"lastTimestamp": stamp, "reason": "Unhealthy",
             "message": 'Startup probe failed: Get "http://10.0.0.1:8000/healthz": dial tcp: connection refused',
             "involvedObject": {"kind": "Pod", "name": "booting"}},
            {"lastTimestamp": stamp, "reason": "Unhealthy",
             "message": "Readiness probe failed: HTTP probe failed with statuscode: 503",
             "involvedObject": {"kind": "Pod", "name": "broken"}},
        ]
    })

    recent = _recent_warnings(payload, window_seconds=600)
    assert len(recent) == 1, "startup-probe noise must be dropped, readiness failures kept"
    assert "broken" in recent[0]


# --- output rendering -----------------------------------------------------
def test_text_renderer_omits_markdown_scaffolding():
    """`to_markdown` targets a PR comment. Piped to a terminal its tables and
    <details> blocks are noise, so the text renderer must not emit them."""

    from aiops.gate import to_text

    ev = Evidence(namespace="demo", release="idea-board",
                  signals={"crash_loop": True, "pods_ready": 0})
    result = run_gate(ev, llm=StubLlm(None), allow_ai=False)
    text = to_text(result, ev)

    assert "FAIL" in text and "rollback    YES" in text
    for scaffolding in ("|---", "<details>", "```", "**"):
        assert scaffolding not in text, f"markdown {scaffolding!r} leaked into the text renderer"


def test_text_renderer_reports_a_healthy_release():

    from aiops.gate import to_text

    ev = Evidence(namespace="demo", release="idea-board",
                  signals={"pods_total": 2, "pods_ready": 2, "restart_count": 0,
                           "log_error_lines": 0, "http_error_rate": 0.0})
    text = to_text(run_gate(ev, llm=StubLlm(None), allow_ai=False), ev)
    assert "PASS" in text and "rollback    no" in text
