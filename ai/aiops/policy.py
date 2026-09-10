"""The policy engine -- the deciding half of the system.

Every AI proposal passes through here before it can become a tfvars file. The
engine does two things a model cannot be trusted to do:

  1. enforces invariants (a 99.9% SLO *requires* multi-AZ; production cannot
     run on spot capacity; the API server cannot be open to the internet);
  2. prices the proposal against the stated budget with a static table, so
     "does this fit the budget" is arithmetic rather than a guess.

Rules are ordered and each one is either a VIOLATION (blocks, or is clamped
under --auto-remediate) or a WARNING (surfaced, never blocks). The engine is
pure: no cloud calls, no LLM, fully unit-testable, and it produces the same
answer on every run.
"""

from dataclasses import dataclass, field
from enum import Enum

from aiops.models import InfraProposal
from aiops.spec import EnvironmentIntent


class Severity(str, Enum):
    violation = "violation"
    warning = "warning"


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: Severity
    message: str
    # Set when the engine can mechanically fix the proposal. `--auto-remediate`
    # applies these; without it they are reported and the run fails.
    remediation: tuple[str, object] | None = None


@dataclass
class Decision:
    proposal: InfraProposal
    findings: list[Finding] = field(default_factory=list)
    estimated_usd_per_month: float = 0.0
    remediated: list[str] = field(default_factory=list)

    @property
    def violations(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.violation]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.warning]

    @property
    def approved(self) -> bool:
        return not self.violations


# --------------------------------------------------------------------------
# Cost model
# --------------------------------------------------------------------------
# Deliberately coarse on-demand list prices (USD/month, ~730h). Close enough to
# catch an order-of-magnitude mistake, which is the failure mode that matters;
# the pipeline does not pretend to be a billing system.
_NODE_USD = {"small": 30.0, "medium": 62.0, "large": 124.0}
_DB_USD = {"small": 15.0, "medium": 105.0, "large": 250.0}
_NAT_USD_PER_AZ = 33.0
_LB_USD = 20.0
_SPOT_DISCOUNT = 0.35  # spot is billed at ~65% off on-demand
_MULTI_AZ_DB_MULTIPLIER = 2.0

ALLOWED_SIZES = ("small", "medium", "large")
MAX_NODES_ANY_ENV = 20

# Connection ceilings per database size, and what one replica consumes.
# The backend opens `db_pool_size` + `db_max_overflow` connections (5 + 5), so
# replica count converts directly into database connections -- which is how an
# autoscaler can scale an application into connection exhaustion while every
# individual setting looks reasonable.
_DB_MAX_CONNECTIONS = {"small": 100, "medium": 200, "large": 400}
_CONNECTIONS_PER_REPLICA = 10
# Leave room for migrations, psql sessions and the pooler itself.
_CONNECTION_SAFETY_FACTOR = 0.8


@dataclass(frozen=True)
class CostLine:
    """One line of the cost estimate, with the arithmetic kept visible."""

    label: str
    detail: str
    usd_per_month: float


def cost_breakdown(p: InfraProposal) -> list[CostLine]:
    """Itemise the monthly estimate.

    Cloud-neutral on purpose: the inputs are t-shirt sizes, and each stack's
    sizing table maps a size to comparable machines on either provider
    (`m6i.large` ~ `e2-standard-2`), so one estimate covers both. Real invoices
    differ by a few percent on unit price and by a lot on egress -- this exists
    to catch an order-of-magnitude mistake and to answer "does this fit the
    budget", which is the question the policy engine needs answered.
    """
    spot = p.cost_optimized and not p.high_availability
    node_unit = _NODE_USD[p.node_size.value] * ((1 - _SPOT_DISCOUNT) if spot else 1.0)
    nat_count = 1 if spot else p.az_count
    db_multiplier = _MULTI_AZ_DB_MULTIPLIER if p.high_availability else 1.0

    return [
        CostLine(
            "Compute",
            f"{p.node_count} x {p.node_size.value} node{'s' if p.node_count != 1 else ''}"
            + (" (spot, -35%)" if spot else " (on-demand)"),
            round(node_unit * p.node_count, 2),
        ),
        CostLine(
            "Database",
            f"{p.db_size.value} managed Postgres"
            + (", multi-AZ (x2)" if p.high_availability else ", single-AZ"),
            round(_DB_USD[p.db_size.value] * db_multiplier, 2),
        ),
        CostLine(
            "NAT gateways",
            f"{nat_count} x ${_NAT_USD_PER_AZ:.0f}" + (" (one shared)" if spot else " (one per AZ)"),
            round(_NAT_USD_PER_AZ * nat_count, 2),
        ),
        CostLine("Load balancer", "1 ingress load balancer", round(_LB_USD, 2)),
    ]


def estimate_monthly_cost(p: InfraProposal) -> float:
    """Steady-state monthly estimate, in USD."""
    return round(sum(line.usd_per_month for line in cost_breakdown(p)), 2)


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------
def evaluate(proposal: InfraProposal, intent: EnvironmentIntent) -> Decision:
    """Judge a proposal against an intent. Pure function."""
    decision = Decision(proposal=proposal)
    add = decision.findings.append
    prod = intent.is_production_grade

    # --- sizing sanity -----------------------------------------------------
    if proposal.node_size.value not in ALLOWED_SIZES:
        add(Finding("sizing.node_size_allowed", Severity.violation,
                    f"node_size {proposal.node_size.value!r} is not in {ALLOWED_SIZES}"))
    if proposal.db_size.value not in ALLOWED_SIZES:
        add(Finding("sizing.db_size_allowed", Severity.violation,
                    f"db_size {proposal.db_size.value!r} is not in {ALLOWED_SIZES}"))

    if proposal.node_min_count > proposal.node_count:
        add(Finding("sizing.min_le_desired", Severity.violation,
                    f"node_min_count ({proposal.node_min_count}) exceeds node_count ({proposal.node_count})",
                    remediation=("node_min_count", proposal.node_count)))
    if proposal.node_max_count < proposal.node_count:
        add(Finding("sizing.max_ge_desired", Severity.violation,
                    f"node_max_count ({proposal.node_max_count}) is below node_count ({proposal.node_count})",
                    remediation=("node_max_count", proposal.node_count)))
    if proposal.node_max_count > MAX_NODES_ANY_ENV:
        add(Finding("sizing.blast_radius", Severity.violation,
                    f"node_max_count {proposal.node_max_count} exceeds the {MAX_NODES_ANY_ENV}-node ceiling; "
                    "an autoscaler bug should not be able to spend without bound",
                    remediation=("node_max_count", MAX_NODES_ANY_ENV)))

    if proposal.autoscaling_enabled and proposal.autoscaling_min_replicas > proposal.autoscaling_max_replicas:
        add(Finding("sizing.hpa_bounds", Severity.violation,
                    "autoscaling_min_replicas exceeds autoscaling_max_replicas",
                    remediation=("autoscaling_min_replicas", proposal.autoscaling_max_replicas)))

    # --- mutually exclusive intent ----------------------------------------
    if proposal.high_availability and proposal.cost_optimized:
        add(Finding("intent.ha_excludes_cost_optimized", Severity.violation,
                    "high_availability and cost_optimized are mutually exclusive: cost_optimized "
                    "implies spot capacity and a single shared NAT",
                    remediation=("cost_optimized", False)))

    # --- production invariants --------------------------------------------
    if prod:
        if not proposal.high_availability:
            add(Finding("prod.requires_ha", Severity.violation,
                        f"SLO of {intent.slo.availability_percent}% requires high_availability=true "
                        "(multi-AZ database, NAT per AZ, on-demand nodes)",
                        remediation=("high_availability", True)))
        if proposal.cost_optimized:
            add(Finding("prod.no_spot", Severity.violation,
                        "cost_optimized uses spot capacity, which can be reclaimed with 2 minutes' notice",
                        remediation=("cost_optimized", False)))
        if not proposal.deletion_protection:
            add(Finding("prod.deletion_protection", Severity.violation,
                        "production databases must have deletion_protection=true",
                        remediation=("deletion_protection", True)))
        if proposal.backup_retention_days < 7:
            add(Finding("prod.backup_retention", Severity.violation,
                        f"backup_retention_days={proposal.backup_retention_days} is below the 7-day production minimum",
                        remediation=("backup_retention_days", 7)))
        if proposal.az_count < 3:
            add(Finding("prod.az_spread", Severity.violation,
                        f"az_count={proposal.az_count} cannot survive a zone failure with quorum; production needs 3",
                        remediation=("az_count", 3)))
        if proposal.node_count < 3:
            add(Finding("prod.node_floor", Severity.violation,
                        f"node_count={proposal.node_count} leaves no capacity headroom during a rolling node upgrade",
                        remediation=("node_count", 3)))
        if not proposal.pod_disruption_budget_enabled:
            add(Finding("prod.pdb", Severity.violation,
                        "a PodDisruptionBudget is required so node drains cannot take the service down",
                        remediation=("pod_disruption_budget_enabled", True)))

    # --- availability floor for every environment -------------------------
    if intent.slo.availability_percent >= 99.0 and proposal.backend_replicas < 2:
        add(Finding("slo.single_replica", Severity.violation,
                    f"a {intent.slo.availability_percent}% SLO cannot be met with one backend replica: "
                    "any pod eviction is full downtime",
                    remediation=("backend_replicas", 2)))

    # --- capacity vs stated load ------------------------------------------
    # One backend replica runs 2 uvicorn workers; budget ~50 rps per replica and
    # require 2x headroom over the stated peak.
    required = max(2 if intent.slo.availability_percent >= 99.0 else 1,
                   int(-(-intent.expected_rps * 2 // 50)))
    effective = proposal.autoscaling_max_replicas if proposal.autoscaling_enabled else proposal.backend_replicas
    if effective < required:
        add(Finding("capacity.headroom", Severity.violation,
                    f"{effective} backend replicas cannot serve {intent.expected_rps} rps with 2x headroom; "
                    f"need at least {required}",
                    remediation=("backend_replicas", required)))

    # --- database connection ceiling ---------------------------------------
    # Checked against the autoscaler's *maximum*, not the current replica
    # count: the failure only appears under the load that triggers scale-up,
    # which is the worst possible moment to discover it.
    if proposal.autoscaling_enabled:
        peak_replicas = proposal.autoscaling_max_replicas
    else:
        peak_replicas = proposal.backend_replicas

    available = int(_DB_MAX_CONNECTIONS[proposal.db_size.value] * _CONNECTION_SAFETY_FACTOR)
    needed = peak_replicas * _CONNECTIONS_PER_REPLICA
    if needed > available:
        safe_replicas = max(1, available // _CONNECTIONS_PER_REPLICA)
        field = "autoscaling_max_replicas" if proposal.autoscaling_enabled else "backend_replicas"
        add(Finding("capacity.db_connections", Severity.violation,
                    f"{peak_replicas} replicas would open {needed} database connections, above the "
                    f"{available} usable on a {proposal.db_size.value} instance "
                    f"({_DB_MAX_CONNECTIONS[proposal.db_size.value]} max, "
                    f"{int(_CONNECTION_SAFETY_FACTOR * 100)}% safety factor). Scale-up would exhaust "
                    "connections instead of adding capacity; add a connection pooler or a larger instance",
                    remediation=(field, safe_replicas)))

    # --- budget ------------------------------------------------------------
    decision.estimated_usd_per_month = estimate_monthly_cost(proposal)
    if decision.estimated_usd_per_month > intent.budget_usd_per_month:
        add(Finding("budget.exceeded", Severity.violation,
                    f"estimated ${decision.estimated_usd_per_month:.0f}/month exceeds the "
                    f"${intent.budget_usd_per_month:.0f} budget for {intent.name}"))
    elif decision.estimated_usd_per_month > intent.budget_usd_per_month * 0.85:
        add(Finding("budget.near_limit", Severity.warning,
                    f"estimated ${decision.estimated_usd_per_month:.0f}/month is within 15% of the "
                    f"${intent.budget_usd_per_month:.0f} budget"))

    # --- advisory ----------------------------------------------------------
    if not prod and proposal.high_availability:
        add(Finding("cost.ha_in_nonprod", Severity.warning,
                    "high_availability roughly doubles database cost; unusual outside production"))
    if prod and not proposal.autoscaling_enabled:
        add(Finding("prod.no_autoscaling", Severity.warning,
                    "production without an HPA cannot absorb a traffic spike"))

    return decision


def remediate(decision: Decision, intent: EnvironmentIntent, max_passes: int = 5) -> Decision:
    """Apply every mechanical fix, then re-evaluate until the result is stable.

    Iterating matters: clamping `high_availability` to true can newly violate
    the budget rule, and the operator must see that rather than a proposal that
    passed a single pass. If violations remain after `max_passes`, they are
    genuinely unresolvable and the caller fails the run.
    """
    current = decision
    applied: list[str] = []

    for _ in range(max_passes):
        fixes = [f for f in current.violations if f.remediation is not None]
        if not fixes:
            break
        patch: dict[str, object] = {}
        for finding in fixes:
            key, value = finding.remediation  # type: ignore[misc]
            patch[key] = value
            applied.append(f"{finding.rule}: {key} -> {value!r}")
        current = evaluate(current.proposal.model_copy(update=patch), intent)

    current.remediated = applied
    return current
