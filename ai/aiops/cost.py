"""`aiops cost` -- what each environment costs, derived from the same model the
policy engine uses to approve it.

The point of deriving it rather than writing a table in a document: the number
in the docs and the number the budget rule enforces cannot drift apart, because
they are the same function. Change a size in platform.yaml and both move.
"""

from aiops.envspec import baseline_proposal
from aiops.models import InfraProposal
from aiops.policy import cost_breakdown, estimate_monthly_cost
from aiops.spec import EnvironmentIntent, PlatformSpec

WIDTH = 74


def _bar(fraction: float, width: int = 24) -> str:
    filled = max(0, min(width, round(fraction * width)))
    return "#" * filled + "." * (width - filled)


def render_environment(intent: EnvironmentIntent, proposal: InfraProposal) -> list[str]:
    lines = [
        "=" * WIDTH,
        f"  {intent.name.upper()}   SLO {intent.slo.availability_percent}%   "
        f"peak {intent.expected_rps:g} rps   budget ${intent.budget_usd_per_month:,.0f}/mo",
        "=" * WIDTH,
    ]

    breakdown = cost_breakdown(proposal)
    total = estimate_monthly_cost(proposal)

    for line in breakdown:
        share = line.usd_per_month / total if total else 0.0
        lines.append(
            f"  {line.label:<15}{line.detail:<38}${line.usd_per_month:>8,.0f}"
        )
        lines.append(f"  {'':<15}{_bar(share):<38}{share * 100:>7.0f}%")

    used = total / intent.budget_usd_per_month if intent.budget_usd_per_month else 0.0
    lines += [
        "-" * WIDTH,
        f"  {'TOTAL':<15}{'':<38}${total:>8,.0f}",
        f"  {'BUDGET':<15}{'':<38}${intent.budget_usd_per_month:>8,.0f}",
        f"  {'HEADROOM':<15}{_bar(used):<38}{used * 100:>7.0f}% used",
        "=" * WIDTH,
    ]
    return lines


def render(spec: PlatformSpec, proposals: dict[str, InfraProposal] | None = None) -> str:
    """Full report. Uses the deterministic baseline unless proposals are given,
    so the report is reproducible without an API key."""
    out: list[str] = []
    grand = 0.0

    for name in sorted(spec.environments):
        intent = spec.environments[name]
        proposal = (proposals or {}).get(name) or baseline_proposal(intent)
        out += render_environment(intent, proposal)
        out.append("")
        grand += estimate_monthly_cost(proposal)

    out += [
        f"  ALL ENVIRONMENTS{'':<22}${grand:>8,.0f}/month   (${grand * 12:,.0f}/year)",
        "",
        "  Cloud-neutral estimate: sizes are t-shirt sizes and each stack maps",
        "  them to comparable machines on either provider. Excludes data egress,",
        "  backup storage beyond the included allowance, and the AI spend below.",
        "",
        "  AI spend, measured: the release gate consults the model only for an",
        "  ambiguous release, so a clean deploy costs $0. Budget a few cents per",
        "  ambiguous verdict and per plan-env run.",
    ]
    return "\n".join(out)
