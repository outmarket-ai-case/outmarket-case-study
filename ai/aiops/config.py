"""aiops configuration. Everything comes from the environment."""

import os
from dataclasses import dataclass

# Default to the most capable model: these decisions gate production deploys,
# and the token cost is rounding error next to a bad rollout.
DEFAULT_MODEL = "claude-opus-5"


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    model: str
    effort: str
    max_tokens: int
    # When true, aiops never calls the API and every stage falls through to its
    # deterministic path. Set automatically when no API key is present so the
    # pipeline degrades instead of failing.
    offline: bool

    @classmethod
    def from_env(cls) -> "Settings":
        key = os.environ.get("ANTHROPIC_API_KEY") or None
        return cls(
            api_key=key,
            model=os.environ.get("AIOPS_MODEL", DEFAULT_MODEL),
            effort=os.environ.get("AIOPS_EFFORT", "high"),
            max_tokens=int(os.environ.get("AIOPS_MAX_TOKENS", "8000")),
            offline=os.environ.get("AIOPS_OFFLINE", "").lower() in {"1", "true", "yes"} or key is None,
        )
