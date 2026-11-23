"""Score ShipCheck against experiments with known answers.

Runs 10 synthetic experiments for each of 6 scenarios (60 total), compares
ShipCheck's decision and the naive "ship if p < 0.05" rule with the correct
decision, and writes the results to EVAL_RESULTS.md.

Usage:  python evaluate.py [--per-scenario 10] [--seed 2026]
"""

import argparse
from collections import defaultdict
from pathlib import Path

from shipcheck import DEMO_CONFIG, analyse, naive_decision
from shipcheck.simulate import DESCRIPTIONS, SCENARIOS, make_experiment


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-scenario", type=int, default=10)
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()

    tool, naive, total = defaultdict(int), defaultdict(int), defaultdict(int)
    mistakes = []
    for s_i, (scenario, truth) in enumerate(SCENARIOS.items()):
        for k in range(args.per_scenario):
            seed = args.seed + 1000 * s_i + k
            df = make_experiment(scenario, seed)
            got = analyse(df, DEMO_CONFIG).decision
            total[scenario] += 1
            tool[scenario] += got == truth
            naive[scenario] += naive_decision(df, DEMO_CONFIG) == truth
            if got != truth:
                mistakes.append((scenario, seed, truth.value, got.value))

    n = sum(total.values())
    t_all, n_all = sum(tool.values()), sum(naive.values())
    lines = [
        "# ShipCheck evaluation results",
        "",
        f"{n} synthetic experiments ({args.per_scenario} per scenario, base seed {args.seed}). "
        "Each experiment has a planted truth, so the correct decision is known.",
        "",
        "| Scenario | What's planted | Correct decision | ShipCheck | Naive p < 0.05 rule |",
        "|---|---|---|---|---|",
    ]
    for scenario, truth in SCENARIOS.items():
        lines.append(f"| {scenario} | {DESCRIPTIONS[scenario]} | {truth.value} | "
                     f"{tool[scenario]}/{total[scenario]} | {naive[scenario]}/{total[scenario]} |")
    lines += ["", f"**Overall: ShipCheck {t_all}/{n} ({t_all / n:.0%}), "
                  f"naive rule {n_all}/{n} ({n_all / n:.0%}).**", ""]
    if mistakes:
        lines += ["## ShipCheck's mistakes", "",
                  "Some errors are expected: at a 5% significance level and 80% power, "
                  "chance alone produces occasional false positives and misses.", "",
                  "| Scenario | Seed | Correct | ShipCheck said |", "|---|---|---|---|"]
        lines += [f"| {s} | {seed} | {t} | {g} |" for s, seed, t, g in mistakes]
    out = "\n".join(lines) + "\n"
    Path("EVAL_RESULTS.md").write_text(out)
    print(out)


if __name__ == "__main__":
    main()
