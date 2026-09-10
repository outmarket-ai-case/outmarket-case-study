"""platform.yaml -- the human-authored intent file.

Developers describe *goals* ("cost-sensitive staging", an SLO, a budget) and
never touch machine types or replica counts. Compiling that into concrete
infrastructure is the AI's job; approving it is the policy engine's.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Slo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    availability_percent: float = Field(ge=90.0, le=99.999)
    p95_latency_ms: int = Field(ge=10, le=10_000)


class EnvironmentIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    intent: str = Field(min_length=10, max_length=1000, description="Plain-English goal.")
    expected_rps: float = Field(ge=0.1, le=100_000)
    slo: Slo
    budget_usd_per_month: float = Field(gt=0)
    data_classification: str = "internal"

    @field_validator("name")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not v.replace("-", "").isalnum() or not v.islower():
            raise ValueError("environment name must be a lowercase slug")
        return v

    @property
    def is_production_grade(self) -> bool:
        """The single derived fact that drives the strictest policy rules.

        Deliberately keyed off the SLO rather than the environment *name*: an
        environment called "staging" that promises 99.9% availability gets
        production guardrails, and nobody can dodge them by renaming a folder.
        """
        return self.slo.availability_percent >= 99.9


class PlatformSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app: str
    environments: dict[str, EnvironmentIntent]

    @classmethod
    def load(cls, path: str) -> "PlatformSpec":
        import yaml

        with open(path) as fh:
            raw = yaml.safe_load(fh)
        # The key in the mapping is authoritative for the environment name.
        for name, env in (raw.get("environments") or {}).items():
            env.setdefault("name", name)
        return cls.model_validate(raw)

    def environment(self, name: str) -> EnvironmentIntent:
        if name not in self.environments:
            known = ", ".join(sorted(self.environments)) or "<none>"
            raise KeyError(f"environment {name!r} not in platform.yaml (have: {known})")
        return self.environments[name]
