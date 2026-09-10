"""The command planner's security property: the model picks operations from a
catalogue, it never produces a command string. These tests pin that boundary."""

import pytest

from aiops.commands import CATALOGUE, InvalidArgument, catalogue_prompt, plan_command, validate
from aiops.llm import LlmClient, LlmUnavailable
from aiops.models import CommandPlan, PlannedStep


class StubLlm(LlmClient):
    def __init__(self, plan: CommandPlan | None):
        self._plan = plan
        self.calls = 0

    def structured(self, **kwargs):  # type: ignore[override]
        self.calls += 1
        if self._plan is None:
            raise LlmUnavailable("simulated outage")
        self._last_prompt = kwargs.get("user", "")
        return self._plan


def make_plan(steps: list[PlannedStep], **overrides) -> CommandPlan:
    base = dict(intent="deploy_preview", steps=steps, explanation="test plan")
    return CommandPlan(**(base | overrides))


# --- the allowlist --------------------------------------------------------
def test_a_valid_plan_binds_to_concrete_argv():
    review = validate(make_plan([
        PlannedStep(operation="deploy",
                    arguments={"cloud": "gcp", "environment": "pr-42", "image_tag": "sha-abc1234"},
                    reason="deploy the preview"),
        PlannedStep(operation="run_gate",
                    arguments={"namespace": "idea-board-pr-42", "release": "idea-board"},
                    reason="confirm it is healthy"),
    ]))

    assert review.executable
    assert review.steps[0].argv == ["scripts/deploy.sh", "gcp", "pr-42", "sha-abc1234"]
    assert review.steps[1].argv[:4] == ["python", "-m", "aiops", "gate"]
    assert not review.needs_approval


def test_an_operation_outside_the_catalogue_is_rejected():
    review = validate(make_plan([
        PlannedStep(operation="kubectl_exec", arguments={"cmd": "rm -rf /"}, reason="malicious"),
    ]))
    assert not review.executable
    assert not review.steps
    assert "not in the catalogue" in review.rejected[0]


def test_one_rejected_step_invalidates_the_whole_plan():
    """A partially valid plan is more dangerous than none: executing steps 1
    and 3 while skipping 2 leaves the system in an unplanned state."""
    review = validate(make_plan([
        PlannedStep(operation="describe_pods",
                    arguments={"namespace": "idea-board-dev", "release": "idea-board"}, reason="ok"),
        PlannedStep(operation="delete_cluster", arguments={}, reason="not allowed"),
    ]))
    assert review.rejected
    assert not review.executable
    assert len(review.steps) == 1  # bound, but the plan is not executable


@pytest.mark.parametrize(
    "arguments,fragment",
    [
        ({"cloud": "azure", "environment": "pr-1", "image_tag": "t"}, "cloud must be one of"),
        ({"cloud": "aws", "environment": "PR_1", "image_tag": "t"}, "not a valid Kubernetes name"),
        ({"cloud": "aws", "environment": "pr-1", "image_tag": "tag with spaces"}, "not a valid image tag"),
        ({"cloud": "aws", "environment": "pr-1;rm -rf /", "image_tag": "t"}, "not a valid Kubernetes name"),
    ],
)
def test_arguments_are_validated_not_interpolated(arguments, fragment):
    review = validate(make_plan([PlannedStep(operation="deploy", arguments=arguments, reason="x")]))
    assert not review.steps
    assert fragment in review.rejected[0]


def test_shell_metacharacters_cannot_reach_argv():
    """Even if validation somehow passed, operations render argv lists rather
    than shell strings -- there is no shell to inject into."""
    for name in ("; rm -rf /", "$(whoami)", "a && b", "`id`", "../../etc"):
        with pytest.raises(InvalidArgument):
            CATALOGUE["describe_pods"].build({"namespace": name, "release": "idea-board"})


def test_missing_and_extra_arguments_are_both_errors():
    with pytest.raises(InvalidArgument, match="missing argument"):
        CATALOGUE["deploy"].build({"cloud": "aws"})
    with pytest.raises(InvalidArgument, match="unknown argument"):
        CATALOGUE["describe_pods"].build(
            {"namespace": "n", "release": "r", "extra": "surprise"}
        )


def test_replica_bounds_are_enforced():
    assert CATALOGUE["scale_backend"].build({"namespace": "n", "release": "r", "replicas": "3"})[-1] == "--replicas=3"
    for bad in ("-1", "999", "three", ""):
        with pytest.raises(InvalidArgument):
            CATALOGUE["scale_backend"].build({"namespace": "n", "release": "r", "replicas": bad})


# --- destructive gating ---------------------------------------------------
@pytest.mark.parametrize("operation", ["rollback", "teardown_preview", "scale_backend"])
def test_destructive_operations_are_flagged(operation):
    assert CATALOGUE[operation].destructive


def test_read_only_operations_are_not_flagged():
    for operation in ("describe_pods", "tail_logs", "run_gate", "wait_rollout", "create_namespace"):
        assert not CATALOGUE[operation].destructive


def test_a_destructive_plan_requires_approval():
    review = validate(make_plan([
        PlannedStep(operation="teardown_preview",
                    arguments={"namespace": "idea-board-pr-42", "release": "idea-board"},
                    reason="the PR was closed"),
    ], intent="teardown_preview"))
    assert review.executable
    assert review.needs_approval


# --- ambiguity and unsupported requests -----------------------------------
def test_clarification_makes_a_plan_non_executable():
    review = validate(make_plan([], clarification_needed="Which cloud should the preview go to?"))
    assert not review.executable


def test_unsupported_intent_yields_no_steps():
    review = validate(make_plan([], intent="unsupported", explanation="the catalogue cannot do this"))
    assert not review.steps
    assert not review.executable


# --- prompt construction --------------------------------------------------
def test_the_catalogue_is_described_to_the_model():
    prompt = catalogue_prompt()
    for name in CATALOGUE:
        assert name in prompt
    assert "DESTRUCTIVE" in prompt


def test_comment_is_fenced_and_marked_untrusted():
    llm = StubLlm(make_plan([]))
    plan_command("/platform deploy a preview", llm=llm)
    assert "untrusted" in llm._last_prompt.lower()
    assert "```" in llm._last_prompt


def test_planning_has_no_deterministic_fallback():
    """Guessing what a developer meant is exactly what must not be improvised."""
    with pytest.raises(LlmUnavailable):
        plan_command("/platform do something", llm=StubLlm(None))
