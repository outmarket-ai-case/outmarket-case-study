"""aiops command line.

    aiops plan-env     --spec platform.yaml --env prod --cloud aws
    aiops gate         --namespace idea-board-dev --release idea-board
    aiops plan-command --comment "/platform deploy a preview to gcp"

Exit codes are meaningful because CI branches on them:
    0  proceed
    1  blocked (policy violation / rollback required / rejected plan)
    2  needs a human (degraded release, clarification needed)
"""

import argparse
import json
import logging
import shlex
import sys
from pathlib import Path

from aiops import commands, cost, envspec, gate
from aiops.config import Settings
from aiops.evidence import FixtureCollector, KubectlCollector
from aiops.llm import LlmClient, LlmUnavailable
from aiops.spec import PlatformSpec

EXIT_OK, EXIT_BLOCKED, EXIT_NEEDS_HUMAN = 0, 1, 2

# Default regions per cloud. Overridable; kept here so `plan-env` needs only a
# cloud name on the command line.
DEFAULT_REGIONS = {"aws": "eu-west-1", "gcp": "europe-west1"}


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)-7s %(name)s: %(message)s",
        stream=sys.stderr,
    )


# --------------------------------------------------------------------------
def cmd_plan_env(args: argparse.Namespace) -> int:
    spec = PlatformSpec.load(args.spec)
    intent = spec.environment(args.env)
    llm = LlmClient(Settings.from_env())

    result = envspec.plan(intent, llm=llm, auto_remediate=not args.no_remediate)
    decision = result.decision

    print(f"\n=== {spec.app} / {args.cloud} / {intent.name} ===")
    print(f"proposal source     : {result.source}" + (f" ({result.note})" if result.note else ""))
    print(f"estimated cost      : ${decision.estimated_usd_per_month:.0f}/month "
          f"(budget ${intent.budget_usd_per_month:.0f})")
    print(f"policy decision     : {'APPROVED' if decision.approved else 'REJECTED'}")
    print(f"\nrationale: {result.rationale}")
    for tradeoff in result.tradeoffs:
        print(f"  tradeoff: {tradeoff}")
    for fix in decision.remediated:
        print(f"  remediated: {fix}")
    for warning in decision.warnings:
        print(f"  warning [{warning.rule}]: {warning.message}")
    for violation in decision.violations:
        print(f"  VIOLATION [{violation.rule}]: {violation.message}")

    if args.out:
        region = args.region or DEFAULT_REGIONS[args.cloud]
        paths = envspec.write_artifacts(result, intent, args.cloud, region, Path(args.out))
        print("\nwrote:")
        for label, path in paths.items():
            print(f"  {label:7s} {path}")

    if not decision.approved:
        print("\nRefusing to emit an approved plan: the violations above are not mechanically fixable.",
              file=sys.stderr)
        return EXIT_BLOCKED
    return EXIT_OK


# --------------------------------------------------------------------------
def cmd_cost(args: argparse.Namespace) -> int:
    spec = PlatformSpec.load(args.spec)
    report = cost.render(spec)
    print(report)
    if args.output:
        Path(args.output).write_text(report + "\n")
    return EXIT_OK


# --------------------------------------------------------------------------
def cmd_gate(args: argparse.Namespace) -> int:
    collector = FixtureCollector(args.fixture) if args.fixture else KubectlCollector()
    evidence = collector.collect(args.namespace, args.release)

    llm = LlmClient(Settings.from_env())
    result = gate.run_gate(evidence, llm=llm, allow_ai=not args.no_ai)

    # Markdown is for a PR comment; text is for a human at a terminal.
    print(gate.to_text(result, evidence) if args.format == "text" else gate.to_markdown(result, evidence))
    if args.output:
        Path(args.output).write_text(gate.to_markdown(result, evidence))

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {
                    "health": result.verdict.health.value,
                    "confidence": result.verdict.confidence,
                    "should_rollback": result.verdict.should_rollback,
                    "triage": result.triage.value,
                    "source": result.source,
                    "summary": result.verdict.summary,
                    "overrides": result.overrides,
                    "signals": evidence.signals,
                },
                indent=2,
                default=str,
            )
        )

    return result.exit_code


# --------------------------------------------------------------------------
def cmd_plan_command(args: argparse.Namespace) -> int:
    llm = LlmClient(Settings.from_env())
    try:
        review = commands.plan_command(args.comment, llm=llm, context=args.context or "")
    except LlmUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_NEEDS_HUMAN

    plan = review.plan
    print(f"intent      : {plan.intent}")
    print(f"explanation : {plan.explanation}")

    if plan.clarification_needed:
        print(f"\nneeds clarification: {plan.clarification_needed}")
        return EXIT_NEEDS_HUMAN

    for reason in review.rejected:
        print(f"REJECTED: {reason}", file=sys.stderr)

    if review.steps:
        print("\nplan:")
        for index, step in enumerate(review.steps, start=1):
            mark = " [needs approval]" if step.destructive else ""
            print(f"  {index}. {step.operation}{mark}")
            print(f"     $ {shlex.join(step.argv)}")
            print(f"     why: {step.reason}")

    if review.rejected:
        return EXIT_BLOCKED
    if not review.steps:
        print("\nnothing to do.")
        return EXIT_BLOCKED if plan.intent == "unsupported" else EXIT_OK
    if review.needs_approval and not args.approve:
        print("\nThis plan contains destructive operations. Re-run with --approve to emit it for execution.",
              file=sys.stderr)
        return EXIT_NEEDS_HUMAN

    if args.emit:
        Path(args.emit).write_text(
            json.dumps([{"operation": s.operation, "argv": s.argv} for s in review.steps], indent=2)
        )
        print(f"\nwrote executable plan to {args.emit}")
    return EXIT_OK


# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aiops", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plan-env", help="Compile platform.yaml intent into tfvars + Helm values")
    p.add_argument("--spec", default="platform.yaml")
    p.add_argument("--env", required=True)
    p.add_argument("--cloud", required=True, choices=sorted(DEFAULT_REGIONS))
    p.add_argument("--region", help="Overrides the per-cloud default region")
    p.add_argument("--out", help="Directory to write artifacts into")
    p.add_argument("--no-remediate", action="store_true",
                   help="Fail on policy violations instead of clamping them")
    p.set_defaults(func=cmd_plan_env)

    p = sub.add_parser("cost", help="Cost per environment, from the policy engine's own model")
    p.add_argument("--spec", default="platform.yaml")
    p.add_argument("--output", help="Also write the report here")
    p.set_defaults(func=cmd_cost)

    p = sub.add_parser("gate", help="Judge a deployed release and decide on rollback")
    p.add_argument("--namespace", required=True)
    p.add_argument("--release", default="idea-board")
    p.add_argument("--fixture", help="Replay a recorded evidence snapshot instead of using kubectl")
    p.add_argument("--no-ai", action="store_true", help="Deterministic rules only")
    p.add_argument("--format", choices=("markdown", "text"), default="markdown",
                   help="markdown for a PR comment (default), text for a terminal")
    p.add_argument("--output", help="Write the markdown verdict here (for a PR comment)")
    p.add_argument("--json", help="Write the machine-readable verdict here")
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("plan-command", help="Turn a PR comment into an allowlisted command plan")
    p.add_argument("--comment", required=True)
    p.add_argument("--context", help="Extra context, e.g. 'PR 42, branch feature-x, image sha-abc123'")
    p.add_argument("--approve", action="store_true", help="Permit destructive operations")
    p.add_argument("--emit", help="Write the validated plan as JSON here")
    p.set_defaults(func=cmd_plan_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(args.verbose)
    return args.func(args)
