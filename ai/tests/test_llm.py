"""The schema hardening in llm.py has to satisfy the structured-outputs subset
without silently losing the constraints Pydantic still enforces."""

from aiops.llm import _strict_schema
from aiops.models import CommandPlan, InfraProposal, ReleaseVerdict


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def test_every_object_forbids_extra_properties():
    for model in (InfraProposal, ReleaseVerdict, CommandPlan):
        for obj in walk(_strict_schema(model)):
            if obj.get("type") == "object":
                assert obj["additionalProperties"] is False


def test_every_property_is_required():
    for model in (InfraProposal, ReleaseVerdict, CommandPlan):
        for obj in walk(_strict_schema(model)):
            if obj.get("type") == "object" and "properties" in obj:
                assert set(obj["required"]) == set(obj["properties"])


def test_unsupported_keywords_are_stripped():
    banned = {"minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "pattern", "multipleOf"}
    for model in (InfraProposal, ReleaseVerdict, CommandPlan):
        for obj in walk(_strict_schema(model)):
            assert banned.isdisjoint(obj.keys())


def test_constraints_are_still_enforced_at_validation_time():
    """The constraints move from generation-time to validation-time; they are
    not lost. A model that returns node_count=0 fails validation."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        InfraProposal.model_validate(
            {
                "node_size": "small", "db_size": "small", "node_count": 0,
                "node_min_count": 1, "node_max_count": 4, "az_count": 2,
                "high_availability": False, "cost_optimized": True,
                "deletion_protection": False, "backup_retention_days": 3,
                "backend_replicas": 2, "frontend_replicas": 1,
                "autoscaling_enabled": False, "autoscaling_min_replicas": 1,
                "autoscaling_max_replicas": 2, "pod_disruption_budget_enabled": False,
                "rationale": "invalid", "tradeoffs": [],
            }
        )


def test_enums_survive_hardening():
    schema = _strict_schema(InfraProposal)
    sizes = next(obj for obj in walk(schema) if "enum" in obj and "small" in obj["enum"])
    assert set(sizes["enum"]) == {"small", "medium", "large"}
