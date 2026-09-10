"""aiops -- the AI layer of the platform.

Three commands, one design rule:

    the model PROPOSES, a deterministic policy engine DECIDES.

Nothing an LLM emits is applied to infrastructure without passing a JSON
schema and then a hand-written policy check that can veto or clamp it. That
is what separates this from a demo: an LLM outage, a hallucination or a
prompt-injected log line degrades the pipeline to its deterministic
behaviour instead of shipping something wrong.
"""

__version__ = "0.1.0"
