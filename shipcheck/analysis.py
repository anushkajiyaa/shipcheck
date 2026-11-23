"""Core statistics and decision logic for ShipCheck.

The decision is made here, by fixed rules. The optional AI layer (memo.py)
only explains the result in words; it never changes the decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd
from scipy import stats


class Decision(str, Enum):
    SHIP = "SHIP"
    DONT_SHIP = "DON'T SHIP"
    KEEP_RUNNING = "KEEP RUNNING"
    INVALID = "INVALID - DON'T TRUST"


@dataclass
class Guardrail:
    column: str
    higher_is_better: bool = True


@dataclass
class Config:
    variant_col: str = "variant"
    control: str = "control"
    treatment: str = "treatment"
    primary: str = "converted"
    primary_higher_is_better: bool = True
    guardrails: list[Guardrail] = field(default_factory=list)
    alpha: float = 0.05
    power: float = 0.80
    mde_relative: float = 0.05  # smallest relative lift worth detecting
    expected_split: float = 0.5  # share of users meant to get treatment
    srm_alpha: float = 0.001  # strict threshold, as is standard for SRM checks


@dataclass
class MetricResult:
    name: str
    kind: str  # "binary" or "continuous"
    control_mean: float
    treatment_mean: float
    abs_diff: float
    rel_diff: float
    ci_low: float
    ci_high: float
    p_value: float
    significant: bool
    good_direction: bool  # True if the observed change is in the "better" direction


@dataclass
class Report:
    decision: Decision
    reasons: list[str]
    n_control: int
    n_treatment: int
    srm_p: float
    srm_ok: bool
    required_n_per_arm: int
    powered: bool
    primary: MetricResult
    guardrails: list[MetricResult]
    harmed_guardrails: list[str]


def _is_binary(series: pd.Series) -> bool:
    vals = pd.unique(series.dropna())
    return len(vals) <= 2 and set(np.asarray(vals, dtype=float)).issubset({0.0, 1.0})


def compare_metric(c: pd.Series, t: pd.Series, name: str, higher_is_better: bool,
                   alpha: float) -> MetricResult:
    c = c.dropna().astype(float)
    t = t.dropna().astype(float)
    mc, mt = c.mean(), t.mean()
    diff = mt - mc
    z = stats.norm.ppf(1 - alpha / 2)

    if _is_binary(pd.concat([c, t])):
        kind = "binary"
        # Two-proportion z-test with pooled SE for the p-value, unpooled for the CI.
        pooled = (c.sum() + t.sum()) / (len(c) + len(t))
        se_pool = np.sqrt(pooled * (1 - pooled) * (1 / len(c) + 1 / len(t)))
        p = 2 * (1 - stats.norm.cdf(abs(diff) / se_pool)) if se_pool > 0 else 1.0
        se = np.sqrt(mc * (1 - mc) / len(c) + mt * (1 - mt) / len(t))
    else:
        kind = "continuous"
        # Welch's t-test (does not assume equal variances).
        p = float(stats.ttest_ind(t, c, equal_var=False).pvalue)
        se = np.sqrt(c.var(ddof=1) / len(c) + t.var(ddof=1) / len(t))

    rel = diff / mc if mc != 0 else float("nan")
    good = (diff > 0) == higher_is_better if diff != 0 else True
    return MetricResult(name, kind, mc, mt, diff, rel, diff - z * se, diff + z * se,
                        float(p), bool(p < alpha), good)


def required_n_per_arm(baseline_mean: float, baseline_sd: float, mde_relative: float,
                       alpha: float, power: float) -> int:
    """Users needed per arm to detect a relative lift of `mde_relative`."""
    delta = abs(baseline_mean * mde_relative)
    if delta == 0 or baseline_sd == 0:
        return 0
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    return int(np.ceil(2 * ((z_a + z_b) * baseline_sd / delta) ** 2))


def analyse(df: pd.DataFrame, cfg: Config) -> Report:
    groups = df[cfg.variant_col].astype(str)
    c_df = df[groups == str(cfg.control)]
    t_df = df[groups == str(cfg.treatment)]
    n_c, n_t = len(c_df), len(t_df)
    if n_c == 0 or n_t == 0:
        raise ValueError(f"Need rows for both '{cfg.control}' and '{cfg.treatment}' "
                         f"in column '{cfg.variant_col}'.")

    # 1. Sample ratio mismatch: did users split the way the test was set up?
    total = n_c + n_t
    expected = [total * (1 - cfg.expected_split), total * cfg.expected_split]
    srm_p = float(stats.chisquare([n_c, n_t], expected).pvalue)
    srm_ok = srm_p >= cfg.srm_alpha

    # 2. Primary metric.
    primary = compare_metric(c_df[cfg.primary], t_df[cfg.primary], cfg.primary,
                             cfg.primary_higher_is_better, cfg.alpha)

    # 3. Power: was the test big enough to detect the smallest lift we care about?
    base = c_df[cfg.primary].dropna().astype(float)
    sd = np.sqrt(base.mean() * (1 - base.mean())) if primary.kind == "binary" else base.std(ddof=1)
    req = required_n_per_arm(base.mean(), sd, cfg.mde_relative, cfg.alpha, cfg.power)
    powered = min(n_c, n_t) >= req

    # 4. Guardrails: did anything we must not break get significantly worse?
    g_results = [compare_metric(c_df[g.column], t_df[g.column], g.column,
                                g.higher_is_better, cfg.alpha) for g in cfg.guardrails]
    harmed = [g.name for g in g_results if g.significant and not g.good_direction]

    # 5. Decision rules, in priority order.
    reasons: list[str] = []
    if not srm_ok:
        decision = Decision.INVALID
        reasons.append(f"Users did not split as planned ({n_c:,} control vs {n_t:,} treatment, "
                       f"SRM p = {srm_p:.2g}). Results are likely biased; fix assignment and rerun.")
    elif harmed:
        decision = Decision.DONT_SHIP
        reasons.append(f"Guardrail metric(s) got significantly worse: {', '.join(harmed)}.")
    elif primary.significant and primary.good_direction:
        decision = Decision.SHIP
        reasons.append(f"{primary.name} improved by {primary.rel_diff:+.1%} (p = {primary.p_value:.3g}) "
                       f"and no guardrail was harmed.")
    elif primary.significant and not primary.good_direction:
        decision = Decision.DONT_SHIP
        reasons.append(f"{primary.name} got significantly worse ({primary.rel_diff:+.1%}, "
                       f"p = {primary.p_value:.3g}).")
    elif not powered:
        decision = Decision.KEEP_RUNNING
        reasons.append(f"No significant change yet, and the test has {min(n_c, n_t):,} users per arm "
                       f"against the {req:,} needed to detect a {cfg.mde_relative:.0%} lift.")
    else:
        decision = Decision.DONT_SHIP
        reasons.append(f"The test was large enough to detect a {cfg.mde_relative:.0%} lift and found "
                       f"no significant change, so the change is unlikely to be worth shipping.")

    return Report(decision, reasons, n_c, n_t, srm_p, srm_ok, req, powered,
                  primary, g_results, harmed)


def naive_decision(df: pd.DataFrame, cfg: Config) -> Decision:
    """The common shortcut: ship if the primary metric's p-value is below 0.05.

    Used only as a baseline in the evaluation, to show what the checks add.
    """
    groups = df[cfg.variant_col].astype(str)
    r = compare_metric(df[groups == cfg.control][cfg.primary], df[groups == cfg.treatment][cfg.primary],
                       cfg.primary, cfg.primary_higher_is_better, cfg.alpha)
    return Decision.SHIP if (r.significant and r.good_direction) else Decision.DONT_SHIP
