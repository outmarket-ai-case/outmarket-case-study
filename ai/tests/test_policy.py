"""The policy engine is the component that must never be wrong: it is the last
thing between an AI proposal and real infrastructure."""

import pytest

from aiops.models import InfraProposal, TShirtSize
from aiops.policy import (
    MAX_NODES_ANY_ENV,
    Severity,
    estimate_monthly_cost,
    evaluate,
    remediate,
)
from aiops.spec import EnvironmentIntent, Slo


def intent(**overrides) -> EnvironmentIntent:
    base = dict(
        name="dev",
        intent="cost-sensitive internal environment for a handful of testers",
        expected_rps=5.0,
        slo=Slo(availability_percent=99.0, p95_latency_ms=500),
        budget_usd_per_month=250.0,
    )
    return EnvironmentIntent(**(base | overrides))


def prod_intent(**overrides) -> EnvironmentIntent:
    return intent(
        **(
            dict(
                name="prod",
                intent="public production traffic; must survive the loss of a zone",
                expected_rps=200.0,
                slo=Slo(availability_percent=99.9, p95_latency_ms=300),
                budget_usd_per_month=1200.0,
            )
            | overrides
        )
    )


def proposal(**overrides) -> InfraProposal:
    base = dict(
        node_size=TShirtSize.small,
        db_size=TShirtSize.small,
        node_count=2,
        node_min_count=1,
        node_max_count=4,
        az_count=2,
        high_availability=False,
        cost_optimized=True,
        deletion_protection=False,
        backup_retention_days=3,
        backend_replicas=2,
        frontend_replicas=1,
        autoscaling_enabled=False,
        autoscaling_min_replicas=2,
        autoscaling_max_replicas=4,
        pod_disruption_budget_enabled=False,
        rationale="test",
    )
    return InfraProposal(**(base | overrides))


def rules(decision) -> set[str]:
    return {f.rule for f in decision.findings}


# --- happy path -----------------------------------------------------------
def test_sensible_dev_proposal_is_approved():
    decision = evaluate(proposal(), intent())
    assert decision.approved, [f.message for f in decision.violations]


def test_sensible_prod_proposal_is_approved():
    decision = evaluate(
        proposal(
            node_size=TShirtSize.medium,
            db_size=TShirtSize.medium,
            node_count=3, node_min_count=3, node_max_count=9, az_count=3,
            high_availability=True, cost_optimized=False,
            deletion_protection=True, backup_retention_days=14,
            backend_replicas=8, frontend_replicas=2,
            autoscaling_enabled=True, autoscaling_min_replicas=8, autoscaling_max_replicas=16,
            pod_disruption_budget_enabled=True,
        ),
        prod_intent(),
    )
    assert decision.approved, [f.message for f in decision.violations]


# --- production invariants ------------------------------------------------
def test_production_slo_forces_ha_and_protection():
    decision = evaluate(proposal(), prod_intent())
    assert not decision.approved
    assert {"prod.requires_ha", "prod.no_spot", "prod.deletion_protection",
            "prod.backup_retention", "prod.az_spread", "prod.node_floor",
            "prod.pdb"} <= rules(decision)


def test_slo_tier_not_environment_name_drives_strictness():
    """An environment called 'staging' that promises 99.9% still gets
    production guardrails -- nobody dodges them by renaming a folder."""
    strict_staging = intent(
        name="staging",
        slo=Slo(availability_percent=99.9, p95_latency_ms=300),
        budget_usd_per_month=1200.0,
    )
    assert strict_staging.is_production_grade
    assert "prod.requires_ha" in rules(evaluate(proposal(), strict_staging))


def test_ha_and_cost_optimized_are_mutually_exclusive():
    decision = evaluate(proposal(high_availability=True, cost_optimized=True), intent())
    assert "intent.ha_excludes_cost_optimized" in rules(decision)


# --- capacity and availability -------------------------------------------
def test_single_replica_cannot_meet_a_99_percent_slo():
    decision = evaluate(proposal(backend_replicas=1), intent())
    assert "slo.single_replica" in rules(decision)


def test_capacity_headroom_is_enforced_against_stated_rps():
    # 200 rps needs ceil(400/50) = 8 replicas.
    decision = evaluate(proposal(backend_replicas=2), intent(expected_rps=200.0))
    finding = next(f for f in decision.findings if f.rule == "capacity.headroom")
    assert finding.remediation == ("backend_replicas", 8)


def test_autoscaling_ceiling_counts_as_capacity():
    decision = evaluate(
        proposal(backend_replicas=2, autoscaling_enabled=True,
                 autoscaling_min_replicas=2, autoscaling_max_replicas=10),
        intent(expected_rps=200.0),
    )
    assert "capacity.headroom" not in rules(decision)


# --- guardrails -----------------------------------------------------------
def test_blast_radius_ceiling_is_clamped():
    decision = evaluate(proposal(node_max_count=50), intent())
    finding = next(f for f in decision.findings if f.rule == "sizing.blast_radius")
    assert finding.remediation == ("node_max_count", MAX_NODES_ANY_ENV)


def test_inconsistent_scaling_bounds_are_caught():
    assert "sizing.min_le_desired" in rules(evaluate(proposal(node_min_count=5, node_count=2), intent()))
    assert "sizing.max_ge_desired" in rules(evaluate(proposal(node_max_count=1, node_count=2), intent()))


# --- budget ---------------------------------------------------------------
def test_budget_is_arithmetic_not_a_guess():
    p = proposal(node_size=TShirtSize.large, db_size=TShirtSize.large, node_count=10,
                 node_max_count=10, cost_optimized=False)
    decision = evaluate(p, intent(budget_usd_per_month=100.0))
    assert "budget.exceeded" in rules(decision)
    assert decision.estimated_usd_per_month == estimate_monthly_cost(p)
    assert decision.estimated_usd_per_month > 100.0


def test_budget_violation_has_no_mechanical_fix():
    """Cost cannot be clamped: only a human can decide to shrink the
    environment or raise the budget."""
    decision = evaluate(
        proposal(node_size=TShirtSize.large, node_count=10, node_max_count=10, cost_optimized=False),
        intent(budget_usd_per_month=50.0),
    )
    finding = next(f for f in decision.findings if f.rule == "budget.exceeded")
    assert finding.remediation is None


def test_near_budget_warns_but_does_not_block():
    p = proposal()
    cost = estimate_monthly_cost(p)
    decision = evaluate(p, intent(budget_usd_per_month=cost / 0.9))
    assert decision.approved
    assert "budget.near_limit" in {f.rule for f in decision.warnings}


def test_spot_is_cheaper_and_ha_costs_more():
    spot = estimate_monthly_cost(proposal(cost_optimized=True))
    on_demand = estimate_monthly_cost(proposal(cost_optimized=False))
    ha = estimate_monthly_cost(proposal(cost_optimized=False, high_availability=True, az_count=3))
    assert spot < on_demand < ha


# --- remediation ----------------------------------------------------------
def test_remediation_converges_and_reports_every_fix():
    decision = remediate(evaluate(proposal(), prod_intent()), prod_intent())
    assert decision.approved, [f.message for f in decision.violations]
    assert decision.remediated
    p = decision.proposal
    assert p.high_availability and not p.cost_optimized
    assert p.deletion_protection and p.backup_retention_days >= 7
    assert p.az_count >= 3 and p.node_count >= 3 and p.pod_disruption_budget_enabled


def test_remediation_surfaces_a_budget_it_cannot_fix():
    """Clamping to HA doubles the database cost. If that breaks the budget the
    operator must see it, not get a plan that passed one pass."""
    tight = prod_intent(budget_usd_per_month=120.0)
    decision = remediate(evaluate(proposal(), tight), tight)
    assert not decision.approved
    assert {f.rule for f in decision.violations} == {"budget.exceeded"}


def test_evaluate_is_pure():
    p = proposal()
    before = p.model_dump()
    evaluate(p, prod_intent())
    assert p.model_dump() == before


@pytest.mark.parametrize("severity", list(Severity))
def test_severities_are_partitioned(severity):
    decision = evaluate(proposal(), prod_intent())
    assert all(f.severity in set(Severity) for f in decision.findings)
    assert set(decision.violations).isdisjoint(decision.warnings)


# --- database connection ceiling -----------------------------------------
def test_autoscaler_cannot_scale_into_connection_exhaustion():
    """Each replica opens pool+overflow (10) connections, so replica count
    converts directly into database connections. The rule checks the
    autoscaler's *maximum*, because the failure only appears under the load
    that triggers scale-up -- the worst moment to discover it."""
    target = prod_intent()
    candidate = proposal(
        high_availability=True, cost_optimized=False, deletion_protection=True,
        backup_retention_days=14, az_count=3, node_count=3,
        pod_disruption_budget_enabled=True, backend_replicas=8,
        autoscaling_enabled=True, autoscaling_min_replicas=8,
        autoscaling_max_replicas=24,  # 24 x 10 = 240 connections
        db_size=TShirtSize.medium,    # 200 max, 160 usable
    )

    decision = evaluate(candidate, target)
    rules = [f.rule for f in decision.violations]
    assert "capacity.db_connections" in rules

    # Clamped to what the instance can actually serve: 160 // 10.
    fixed = remediate(decision, target)
    assert fixed.proposal.autoscaling_max_replicas == 16
    assert "capacity.db_connections" not in [f.rule for f in fixed.violations]


def test_connection_rule_uses_replica_count_when_autoscaling_is_off():
    target = intent()
    candidate = proposal(backend_replicas=12, autoscaling_enabled=False,
                        db_size=TShirtSize.small)  # 100 max, 80 usable -> 8 replicas
    decision = evaluate(candidate, target)
    finding = next((f for f in decision.violations if f.rule == "capacity.db_connections"), None)
    assert finding is not None
    assert finding.remediation == ("backend_replicas", 8)


def test_a_sane_configuration_does_not_trip_the_connection_rule():
    target = prod_intent()
    candidate = proposal(
        high_availability=True, cost_optimized=False, deletion_protection=True,
        backup_retention_days=14, az_count=3, node_count=3,
        pod_disruption_budget_enabled=True, backend_replicas=8,
        autoscaling_enabled=True, autoscaling_min_replicas=8,
        autoscaling_max_replicas=16, db_size=TShirtSize.medium,
    )
    assert "capacity.db_connections" not in [f.rule for f in evaluate(candidate, target).violations]
