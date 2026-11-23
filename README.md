# ShipCheck

**Should we ship this A/B test?** ShipCheck checks whether an experiment's results can be trusted, then makes a ship / don't ship / keep running call and writes a decision memo for stakeholders.

## The problem

Product teams often decide with one rule: *"the primary metric went up and p < 0.05, so ship it."* That rule misses three common failures:

1. **Broken experiments.** If a bug drops or misassigns some users, the groups stop being comparable, and the test can show a "significant" win that isn't real.
2. **Tests stopped too early.** "Not significant" from a small test means *we don't know yet*, not *it doesn't work*.
3. **Hidden harm.** Conversion goes up, but pages get slower or refunds rise.

## How it works

ShipCheck runs four checks in a fixed order. The first one that fails decides the outcome:

| Order | Check | Method | If it fails |
|---|---|---|---|
| 1 | Did users split as planned? | Sample ratio mismatch (SRM) chi-square test, strict p < 0.001 | **INVALID - DON'T TRUST** |
| 2 | Did any guardrail metric get worse? | Two-proportion z-test or Welch's t-test per guardrail | **DON'T SHIP** |
| 3 | Did the primary metric change? | Same tests, with a 95% confidence interval | **SHIP** if better, **DON'T SHIP** if worse |
| 4 | Was the test big enough? | Power calculation for the smallest lift worth detecting | **KEEP RUNNING** if too small, otherwise **DON'T SHIP** (no meaningful effect) |

## Design decisions

- **Fixed rules make the decision.** Every decision comes from rules that can be tested and explained, not from a model's judgement.
- **Check the split first.** A broken split makes every other number unreliable, so nothing else is trusted until it passes. The threshold is strict (p < 0.001) so real tests aren't flagged by chance.
- **Guardrails can veto a win.** This makes ShipCheck cautious: with two guardrails, chance alone sometimes flags harm that isn't there. The evaluation shows this cost (a few real wins blocked) and I accepted it, because shipping real harm is worse than delaying a real win.
- **"Not significant" isn't treated as "no effect".** The power check is what separates *keep running* from *don't ship*.

## Evaluation

Every experiment in the evaluation is synthetic, with the correct decision planted in advance. That makes it possible to score the tool exactly. `python evaluate.py` runs 10 experiments for each of 6 scenarios:

| Scenario | Correct decision | ShipCheck | Naive "p < 0.05" rule |
|---|---|---|---|
| Real win | SHIP | 9/10 | 10/10 |
| Real loss | DON'T SHIP | 10/10 | 10/10 |
| No effect | DON'T SHIP | 9/10 | 9/10 |
| Stopped too early | KEEP RUNNING | 10/10 | 0/10 |
| Broken split (fake win) | INVALID | 10/10 | 0/10 |
| Win that slows the page | DON'T SHIP | 10/10 | 0/10 |
| **Overall** | | **58/60 (97%)** | **29/60 (48%)** |

A larger run (`python evaluate.py --per-scenario 50 --seed 7`) gives 290/300 (97%) against 150/300 (50%). Full details are in [EVAL_RESULTS.md](EVAL_RESULTS.md).

ShipCheck's two misses are the expected cost of statistics: one guardrail false alarm that blocked a real win, and one false positive on a test with no real effect.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py          # the app
python evaluate.py            # the evaluation
python -m pytest -q           # the tests
```

**Your own data:** upload a CSV with one row per user, a column saying which variant they saw, and numeric metric columns (0/1 for yes/no metrics). `sample_data/` has one example file for each scenario.

## Limitations

- Fixed-horizon tests only. It doesn't correct for checking results repeatedly while a test runs (sequential testing).
- No correction for testing several guardrails at once, and no variance reduction (e.g., CUPED).
- Two groups only, one row per user.
- The evaluation uses simulated data. Real experiments have messier problems such as novelty effects and seasonality.
