# ShipCheck evaluation results

60 synthetic experiments (10 per scenario, base seed 2026). Each experiment has a planted truth, so the correct decision is known.

| Scenario | What's planted | Correct decision | ShipCheck | Naive p < 0.05 rule |
|---|---|---|---|---|
| real_win | Treatment truly lifts conversion by 10-15%; test is large enough. | SHIP | 9/10 | 10/10 |
| real_loss | Treatment truly lowers conversion by 10-15%; test is large enough. | DON'T SHIP | 10/10 | 10/10 |
| no_effect | Treatment changes nothing; test is large enough to tell. | DON'T SHIP | 9/10 | 9/10 |
| underpowered | Treatment has a small real lift, but the test stopped far too early. | KEEP RUNNING | 10/10 | 0/10 |
| broken_split | No real effect, but a logging bug silently drops ~7% of treatment users who didn't convert, which fakes a win. | INVALID - DON'T TRUST | 10/10 | 0/10 |
| guardrail_harm | Conversion truly rises, but page load time gets ~8% slower. | DON'T SHIP | 10/10 | 0/10 |

**Overall: ShipCheck 58/60 (97%), naive rule 29/60 (48%).**

## ShipCheck's mistakes

Some errors are expected: at a 5% significance level and 80% power, chance alone produces occasional false positives and misses.

| Scenario | Seed | Correct | ShipCheck said |
|---|---|---|---|
| real_win | 2034 | SHIP | DON'T SHIP |
| no_effect | 4031 | DON'T SHIP | SHIP |
