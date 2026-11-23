"""Turn a Report into a decision memo.

`template_memo` always works and needs no API key. `ai_memo` asks an LLM to
rewrite the same facts as a readable memo for stakeholders; it is told the
decision is final and may not change it, and the code checks that it didn't.
"""

from __future__ import annotations

import os

from .analysis import Decision, MetricResult, Report


def _fmt(m: MetricResult) -> str:
    if m.kind == "binary":
        vals = f"{m.control_mean:.2%} -> {m.treatment_mean:.2%}"
        ci = f"[{m.ci_low * 100:+.2f}, {m.ci_high * 100:+.2f}] pp"
    else:
        vals = f"{m.control_mean:,.1f} -> {m.treatment_mean:,.1f}"
        ci = f"[{m.ci_low:+,.1f}, {m.ci_high:+,.1f}]"
    sig = "significant" if m.significant else "not significant"
    return f"{m.name}: {vals} ({m.rel_diff:+.1%}), 95% CI {ci}, p = {m.p_value:.3g}, {sig}"


def facts(r: Report) -> str:
    lines = [
        f"Decision: {r.decision.value}",
        *[f"Reason: {x}" for x in r.reasons],
        f"Users: {r.n_control:,} control, {r.n_treatment:,} treatment",
        f"Split check (SRM): {'passed' if r.srm_ok else 'FAILED'} (p = {r.srm_p:.3g})",
        f"Sample size: {'enough' if r.powered else 'NOT enough'} "
        f"(need {r.required_n_per_arm:,} per arm)",
        f"Primary metric - {_fmt(r.primary)}",
        *[f"Guardrail - {_fmt(g)}" + (" [HARMED]" if g.name in r.harmed_guardrails else "")
          for g in r.guardrails],
    ]
    return "\n".join(lines)


NEXT_STEPS = {
    Decision.SHIP: "Roll out gradually and keep watching the guardrail metrics for two weeks.",
    Decision.DONT_SHIP: "Don't roll out. Review what drove the result before designing a follow-up test.",
    Decision.KEEP_RUNNING: "Keep the test running until each arm reaches the required sample size, "
                           "and don't peek at significance again before then.",
    Decision.INVALID: "Don't use these numbers. Find why users were dropped or misassigned "
                      "(logging, redirects, bot filtering), fix it, and restart the test.",
}


def template_memo(r: Report, test_name: str = "Experiment") -> str:
    out = [f"## {test_name}: {r.decision.value}", "", *r.reasons, "", "**Key numbers**", ""]
    out += [f"- {line}" for line in facts(r).splitlines()[len(r.reasons) + 1:]]
    out += ["", f"**Next step:** {NEXT_STEPS[r.decision]}"]
    return "\n".join(out)


PROMPT = """You are writing a short decision memo about an A/B test for product, \
engineering and business stakeholders. The analysis below was done by a statistics engine. \
The decision is FINAL: state it exactly as given and do not argue for a different one.

Write under 180 words in markdown with these parts:
1. A heading with the test name and the decision.
2. "What happened": two or three plain-English sentences. Explain any statistics jargon.
3. "Why this decision": the reasons, in plain English.
4. "Caveats": one or two honest limitations.
5. "Next step": one sentence.

Only use numbers that appear below. Do not invent any.

Test name: {name}
{facts}
Suggested next step: {next_step}
"""


def ai_memo(r: Report, test_name: str = "Experiment") -> str | None:
    """Return an LLM-written memo, or None if no API key is set or the call fails."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=os.environ.get("SHIPCHECK_MODEL", "claude-haiku-5-5"),
            max_tokens=600,
            messages=[{"role": "user", "content": PROMPT.format(
                name=test_name, facts=facts(r), next_step=NEXT_STEPS[r.decision])}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    except Exception:
        return None
    return text if states_decision(text, r.decision) else None


def states_decision(text: str, decision: Decision) -> bool:
    """Guard: the memo must name the engine's decision and no other one."""
    import re

    # Look only at the heading line(s), where the memo states its decision.
    head = text.strip().splitlines()[0].upper().replace("’", "'").replace("DO NOT", "DON'T")
    patterns = {Decision.SHIP: r"(?<!DON'T )\bSHIP\b", Decision.DONT_SHIP: r"\bDON'T SHIP\b",
                Decision.KEEP_RUNNING: r"\bKEEP RUNNING\b", Decision.INVALID: r"\bINVALID\b"}
    found = {d for d, p in patterns.items() if re.search(p, head)}
    return found == {decision}
