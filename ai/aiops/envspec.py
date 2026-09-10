"""`aiops plan-env` -- compile intent into infrastructure.

    platform.yaml  ->  Claude proposes  ->  policy decides  ->  tfvars + values

The interesting property is that the AI is *optional*. If the model is
unreachable, declined, or hallucinates an unusable shape, a deterministic
baseline profile takes over and the same policy engine judges it. The pipeline
never blocks on the API, and it never applies an unjudged proposal.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from aiops.llm import LlmClient, LlmUnavailable
from aiops.models import InfraProposal, TShirtSize
from aiops.policy import Decision, estimate_monthly_cost, evaluate, remediate
from aiops.spec import EnvironmentIntent

log = logging.getLogger("aiops.envspec")

SYSTEM_PROMPT = """\
You are a platform engineer sizing a Kubernetes environment for a small \
three-tier web application (React frontend behind nginx, FastAPI backend, \
managed PostgreSQL).

You will be given one environment's intent: a plain-English goal, an expected \
request rate, an SLO, and a monthly budget. Propose the cloud-neutral \
configuration that meets that intent at the lowest cost.

Constraints you must respect:
- Sizes are t-shirt sizes (small/medium/large), not machine types. A "small" \
node is 2 vCPU / 4 GiB, "medium" 2 vCPU / 8 GiB, "large" 4 vCPU / 16 GiB.
- `high_availability` means multi-AZ database, one NAT gateway per AZ, and \
on-demand nodes. `cost_optimized` means spot nodes and a single shared NAT. \
They are mutually exclusive.
- An SLO of 99.9% or higher requires high_availability, deletion_protection, \
at least 3 AZs, at least 3 nodes, a PodDisruptionBudget, and at least 7 days \
of backups.
- Any SLO of 99% or higher needs at least 2 backend replicas: a single replica \
means every pod eviction is downtime.
- Budget at roughly: $30/month per small node, $62 medium, $124 large (spot is \
~35% cheaper); database $15 small, $105 medium, $250 large (doubled when \
multi-AZ); $33 per NAT gateway per month; $20 for the load balancer.
- One backend replica serves about 50 requests/second. Leave 2x headroom over \
the stated peak.

Be specific about the tradeoff you are making in `rationale`, and put what the \
configuration gives up in `tradeoffs`. A reviewer reads both in a pull request.
"""


@dataclass
class PlanResult:
    decision: Decision
    source: str  # "ai" | "baseline"
    rationale: str
    tradeoffs: list[str]
    note: str = ""

    @property
    def approved(self) -> bool:
        return self.decision.approved


def baseline_proposal(intent: EnvironmentIntent) -> InfraProposal:
    """Deterministic fallback: what a careful engineer would pick from the
    intent alone, with no model involved.

    Intentionally conservative. It exists to keep the pipeline running, not to
    be optimal -- and because it goes through the same policy engine, a
    conservative baseline can still be rejected on budget, which is the correct
    signal to a human.
    """
    prod = intent.is_production_grade
    replicas = max(2, int(-(-intent.expected_rps * 2 // 50))) if intent.slo.availability_percent >= 99.0 else 1

    return InfraProposal(
        node_size=TShirtSize.medium if prod else TShirtSize.small,
        db_size=TShirtSize.medium if prod else TShirtSize.small,
        node_count=3 if prod else 2,
        node_min_count=3 if prod else 1,
        node_max_count=9 if prod else 4,
        az_count=3 if prod else 2,
        high_availability=prod,
        cost_optimized=not prod,
        deletion_protection=prod,
        backup_retention_days=14 if prod else 3,
        backend_replicas=replicas,
        frontend_replicas=2 if prod else 1,
        autoscaling_enabled=prod,
        autoscaling_min_replicas=replicas,
        autoscaling_max_replicas=max(replicas * 3, 6) if prod else replicas,
        pod_disruption_budget_enabled=prod,
        rationale=(
            "Deterministic baseline profile (the model was not consulted or its proposal "
            "was unusable). Sized from the SLO tier and expected request rate."
        ),
        tradeoffs=["Not cost-optimised beyond the environment tier; a human should review."],
    )


def plan(intent: EnvironmentIntent, *, llm: LlmClient, auto_remediate: bool = True) -> PlanResult:
    source = "ai"
    note = ""

    try:
        proposal = llm.structured(
            system=SYSTEM_PROMPT,
            user=_render_intent(intent),
            schema_model=InfraProposal,
        )
    except LlmUnavailable as exc:
        log.warning("falling back to the baseline profile: %s", exc)
        proposal = baseline_proposal(intent)
        source = "baseline"
        note = f"model unavailable ({exc}); used the deterministic baseline"

    decision = evaluate(proposal, intent)
    if auto_remediate and decision.violations:
        decision = remediate(decision, intent)

    return PlanResult(
        decision=decision,
        source=source,
        rationale=decision.proposal.rationale,
        tradeoffs=list(decision.proposal.tradeoffs),
        note=note,
    )


def _render_intent(intent: EnvironmentIntent) -> str:
    return (
        f"Environment: {intent.name}\n"
        f"Intent: {intent.intent}\n"
        f"Expected peak: {intent.expected_rps} requests/second\n"
        f"SLO: {intent.slo.availability_percent}% availability, "
        f"p95 latency under {intent.slo.p95_latency_ms} ms\n"
        f"Budget: ${intent.budget_usd_per_month:.0f}/month\n"
        f"Data classification: {intent.data_classification}\n"
    )


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def render_tfvars(p: InfraProposal, intent: EnvironmentIntent, cloud: str, region: str) -> str:
    """Emit the cloud-neutral variable contract. Only `region` (and GCP's
    `project_id`) differ between clouds -- see docs/cloud-agnostic.md."""
    lines = [
        f"# Generated by `aiops plan-env` for {cloud}/{intent.name}. Do not edit by hand.",
        f"# Estimated cost: ${estimate_monthly_cost(p):.0f}/month (budget ${intent.budget_usd_per_month:.0f}).",
        "",
        f'environment = "{intent.name}"',
        f'region      = "{region}"',
    ]
    if cloud == "gcp":
        lines.append('project_id  = "REPLACE_WITH_YOUR_GCP_PROJECT"')
    lines += [
        "",
        f'node_size      = "{p.node_size.value}"',
        f'db_size        = "{p.db_size.value}"',
        f"node_count     = {p.node_count}",
        f"node_min_count = {p.node_min_count}",
        f"node_max_count = {p.node_max_count}",
        f"az_count       = {p.az_count}",
        "",
        f"high_availability     = {str(p.high_availability).lower()}",
        f"cost_optimized        = {str(p.cost_optimized).lower()}",
        f"deletion_protection   = {str(p.deletion_protection).lower()}",
        f"backup_retention_days = {p.backup_retention_days}",
        "",
    ]
    return "\n".join(lines)


def render_helm_values(p: InfraProposal) -> str:
    """Only the workload-sizing block: the `platform:` block is generated from
    the Terraform contract by scripts/platform-values.sh."""
    import yaml

    return yaml.safe_dump(
        {
            "backend": {"replicaCount": p.backend_replicas},
            "frontend": {"replicaCount": p.frontend_replicas},
            "autoscaling": {
                "enabled": p.autoscaling_enabled,
                "minReplicas": p.autoscaling_min_replicas,
                "maxReplicas": p.autoscaling_max_replicas,
            },
            "podDisruptionBudget": {"enabled": p.pod_disruption_budget_enabled, "minAvailable": 1},
        },
        sort_keys=True,
    )


def write_artifacts(result: PlanResult, intent: EnvironmentIntent, cloud: str, region: str, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = result.decision.proposal

    paths = {
        "tfvars": out_dir / f"{cloud}-{intent.name}.tfvars",
        "values": out_dir / f"{cloud}-{intent.name}-sizing.yaml",
        "report": out_dir / f"{cloud}-{intent.name}-plan.json",
    }
    paths["tfvars"].write_text(render_tfvars(p, intent, cloud, region))
    paths["values"].write_text(render_helm_values(p))
    paths["report"].write_text(
        json.dumps(
            {
                "environment": intent.name,
                "cloud": cloud,
                "source": result.source,
                "approved": result.approved,
                "estimated_usd_per_month": result.decision.estimated_usd_per_month,
                "budget_usd_per_month": intent.budget_usd_per_month,
                "rationale": result.rationale,
                "tradeoffs": result.tradeoffs,
                "remediated": result.decision.remediated,
                "violations": [f.message for f in result.decision.violations],
                "warnings": [f.message for f in result.decision.warnings],
                "proposal": p.model_dump(mode="json"),
                "note": result.note,
            },
            indent=2,
        )
    )
    return paths
