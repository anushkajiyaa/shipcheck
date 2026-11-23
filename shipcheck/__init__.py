from .analysis import Config, Decision, Guardrail, Report, analyse, naive_decision

DEMO_CONFIG = Config(
    primary="converted",
    guardrails=[Guardrail("refunded", higher_is_better=False),
                Guardrail("load_time_ms", higher_is_better=False)],
    mde_relative=0.10,
)

__all__ = ["Config", "Decision", "Guardrail", "Report", "analyse", "naive_decision", "DEMO_CONFIG"]
