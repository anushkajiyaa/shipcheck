"""Generate synthetic A/B tests where the correct decision is known in advance.

Each row is one user: which variant they saw, whether they converted, whether
they asked for a refund, and how long the page took to load.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .analysis import Decision

# scenario -> the decision a careful analyst who knew the truth would make
SCENARIOS: dict[str, Decision] = {
    "real_win": Decision.SHIP,
    "real_loss": Decision.DONT_SHIP,
    "no_effect": Decision.DONT_SHIP,
    "underpowered": Decision.KEEP_RUNNING,
    "broken_split": Decision.INVALID,
    "guardrail_harm": Decision.DONT_SHIP,
}

DESCRIPTIONS = {
    "real_win": "Treatment truly lifts conversion by 10-15%; test is large enough.",
    "real_loss": "Treatment truly lowers conversion by 10-15%; test is large enough.",
    "no_effect": "Treatment changes nothing; test is large enough to tell.",
    "underpowered": "Treatment has a small real lift, but the test stopped far too early.",
    "broken_split": "No real effect, but a logging bug silently drops ~7% of treatment users "
                    "who didn't convert, which fakes a win.",
    "guardrail_harm": "Conversion truly rises, but page load time gets ~8% slower.",
}


def _arm(rng, n, conv, refund, load_ms):
    return pd.DataFrame({
        "converted": rng.binomial(1, conv, n),
        "refunded": rng.binomial(1, refund, n),
        "load_time_ms": rng.lognormal(np.log(load_ms), 0.3, n).round(0),
    })


def make_experiment(scenario: str, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = rng.uniform(0.15, 0.25)
    refund = rng.uniform(0.02, 0.04)
    load = rng.uniform(900, 1500)
    n = int(rng.integers(11000, 14000))
    t_conv, t_load, t_n = base, load, n

    if scenario == "real_win":
        t_conv = base * (1 + rng.uniform(0.10, 0.15))
    elif scenario == "real_loss":
        t_conv = base * (1 - rng.uniform(0.10, 0.15))
    elif scenario == "underpowered":
        n = t_n = int(rng.integers(800, 1500))
        t_conv = base * (1 + rng.uniform(0.03, 0.06))
    elif scenario == "guardrail_harm":
        t_conv = base * (1 + rng.uniform(0.10, 0.15))
        t_load = load * (1 + rng.uniform(0.07, 0.09))
    elif scenario not in ("no_effect", "broken_split"):
        raise ValueError(f"unknown scenario {scenario}")

    c = _arm(rng, n, base, refund, load).assign(variant="control")
    t = _arm(rng, t_n, t_conv, refund, t_load).assign(variant="treatment")

    if scenario == "broken_split":
        non_conv = t.index[t["converted"] == 0]
        drop = rng.choice(non_conv, size=int(0.07 * len(t)), replace=False)
        t = t.drop(index=drop)

    df = pd.concat([c, t], ignore_index=True).sample(frac=1, random_state=seed)
    df.insert(0, "user_id", np.arange(1, len(df) + 1))
    return df[["user_id", "variant", "converted", "refunded", "load_time_ms"]].reset_index(drop=True)
