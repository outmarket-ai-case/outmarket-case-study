"""Schemas for everything an LLM is allowed to emit.

These double as the JSON Schema handed to the model (structured outputs) and
as the validation boundary on the way back in. A field the model cannot fill
correctly is a field it should not be deciding.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------
# 1. Environment spec compiler
# --------------------------------------------------------------------------
class TShirtSize(str, Enum):
    small = "small"
    medium = "medium"
    large = "large"


class InfraProposal(BaseModel):
    """The AI's proposed answer to 'what infrastructure does this intent need?'

    Deliberately narrow: the model chooses from the same cloud-neutral knobs a
    human would set in a tfvars file. It cannot invent a field, name a machine
    type, or reach a cloud API.
    """

    model_config = ConfigDict(extra="forbid")

    node_size: TShirtSize
    db_size: TShirtSize
    node_count: int = Field(ge=1, le=50)
    node_min_count: int = Field(ge=1, le=50)
    node_max_count: int = Field(ge=1, le=50)
    az_count: int = Field(ge=2, le=4)

    high_availability: bool
    cost_optimized: bool
    deletion_protection: bool
    backup_retention_days: int = Field(ge=1, le=35)

    backend_replicas: int = Field(ge=1, le=50)
    frontend_replicas: int = Field(ge=1, le=50)
    autoscaling_enabled: bool
    autoscaling_min_replicas: int = Field(ge=1, le=50)
    autoscaling_max_replicas: int = Field(ge=1, le=50)
    pod_disruption_budget_enabled: bool

    rationale: str = Field(
        max_length=1200,
        description="Why this shape fits the stated intent, SLO and budget. Shown in the PR.",
    )
    tradeoffs: list[str] = Field(
        default_factory=list,
        max_length=6,
        description="What this configuration gives up. One short sentence each.",
    )


# --------------------------------------------------------------------------
# 2. Release gate
# --------------------------------------------------------------------------
class Health(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    failed = "failed"


class EvidenceRef(BaseModel):
    """Forces the model to point at the input that justifies its verdict.

    A finding with no citation is dropped before the verdict is acted on, which
    is the cheapest available defence against a confident hallucination.
    """

    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="Evidence key, e.g. 'pod_events' or 'metrics'.")
    excerpt: str = Field(max_length=400, description="Verbatim line or value from that source.")
    interpretation: str = Field(max_length=300)


class ReleaseVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    health: Health
    confidence: float = Field(ge=0.0, le=1.0)
    should_rollback: bool
    summary: str = Field(
        max_length=800,
        description="Human-readable summary for the PR comment. Lead with the outcome.",
    )
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=8)
    suggested_next_step: str = Field(default="", max_length=300)


# --------------------------------------------------------------------------
# 3. PR command planner
# --------------------------------------------------------------------------
class PlannedStep(BaseModel):
    """One step of a plan.

    `operation` must name an entry in the operation catalogue and `arguments`
    must satisfy that entry's schema. The model never emits a shell string --
    it selects a parameterised operation, and the catalogue renders the
    command. Prompt injection therefore cannot reach a shell.
    """

    model_config = ConfigDict(extra="forbid")

    operation: str
    arguments: dict[str, str] = Field(default_factory=dict)
    reason: str = Field(max_length=300)


class CommandPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["deploy_preview", "teardown_preview", "rollback", "scale", "inspect", "unsupported"]
    steps: list[PlannedStep] = Field(default_factory=list, max_length=10)
    explanation: str = Field(max_length=600)
    clarification_needed: str = Field(
        default="",
        max_length=300,
        description="Set when the request is too ambiguous to plan safely; leave empty otherwise.",
    )
