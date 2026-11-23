import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from shipcheck import DEMO_CONFIG, Decision, analyse  # noqa: E402
from shipcheck.memo import states_decision, template_memo  # noqa: E402
from shipcheck.simulate import SCENARIOS, make_experiment  # noqa: E402


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_each_scenario_on_a_fixed_seed(scenario):
    df = make_experiment(scenario, seed=1)
    assert analyse(df, DEMO_CONFIG).decision == SCENARIOS[scenario]


def test_broken_split_is_flagged_before_anything_else():
    r = analyse(make_experiment("broken_split", seed=3), DEMO_CONFIG)
    assert not r.srm_ok and r.decision == Decision.INVALID


def test_missing_group_raises():
    df = make_experiment("no_effect", seed=1)
    with pytest.raises(ValueError):
        analyse(df[df.variant == "control"], DEMO_CONFIG)


def test_template_memo_names_the_decision():
    r = analyse(make_experiment("guardrail_harm", seed=1), DEMO_CONFIG)
    assert states_decision(template_memo(r, "Checkout test"), r.decision)


@pytest.mark.parametrize("heading,decision,ok", [
    ("## Test: SHIP", Decision.SHIP, True),
    ("## Test: DON'T SHIP", Decision.SHIP, False),
    ("## Test: Do not ship", Decision.DONT_SHIP, True),
    ("## Test: Keep running", Decision.SHIP, False),
])
def test_ai_memo_guard(heading, decision, ok):
    assert states_decision(heading + "\nbody text about shipping", decision) is ok
