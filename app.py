"""ShipCheck: should we ship this A/B test?  Run with:  streamlit run app.py"""

import pandas as pd
import streamlit as st

from shipcheck import Config, Decision, Guardrail, analyse
from shipcheck.memo import ai_memo, template_memo
from shipcheck.simulate import DESCRIPTIONS, SCENARIOS, make_experiment

st.set_page_config(page_title="ShipCheck", layout="wide")
st.title("ShipCheck")
st.caption("Checks whether an A/B test can be trusted, then says whether to ship it. "
           "The statistics make the decision; AI only writes the memo.")

COLOURS = {Decision.SHIP: "green", Decision.DONT_SHIP: "red",
           Decision.KEEP_RUNNING: "orange", Decision.INVALID: "violet"}

# ---------- Data ----------
with st.sidebar:
    st.header("1. Data")
    source = st.radio("Source", ["Try a sample test", "Upload a CSV"])
    if source == "Try a sample test":
        scenario = st.selectbox("Sample", list(SCENARIOS), format_func=lambda s: s.replace("_", " "))
        st.caption(DESCRIPTIONS[scenario])
        df = make_experiment(scenario, seed=42)
        test_name = f"Sample: {scenario.replace('_', ' ')}"
    else:
        up = st.file_uploader("One row per user, with a variant column and metric columns", type="csv")
        if up is None:
            st.info("Upload a CSV, or switch to a sample test.")
            st.stop()
        df = pd.read_csv(up)
        test_name = st.text_input("Test name", up.name.rsplit(".", 1)[0])

cols = list(df.columns)
numeric = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]

with st.sidebar:
    st.header("2. Setup")
    variant_col = st.selectbox("Variant column", cols, index=cols.index("variant") if "variant" in cols else 0)
    labels = sorted(df[variant_col].astype(str).unique())
    if len(labels) < 2:
        st.error("The variant column needs at least two groups.")
        st.stop()
    control = st.selectbox("Control group", labels, index=labels.index("control") if "control" in labels else 0)
    treatment = st.selectbox("Treatment group", [x for x in labels if x != control])
    primary = st.selectbox("Primary metric", numeric,
                           index=numeric.index("converted") if "converted" in numeric else 0)
    primary_up = st.toggle("Higher is better", True, key="p_up")

    st.subheader("Guardrails")
    st.caption("Metrics that must not get worse.")
    default_g = [c for c in ("refunded", "load_time_ms") if c in numeric and c != primary]
    g_cols = st.multiselect("Guardrail metrics", [c for c in numeric if c != primary], default_g)
    guardrails = [Guardrail(c, st.toggle(f"{c}: higher is better", c not in ("refunded", "load_time_ms"),
                                         key=f"g_{c}")) for c in g_cols]

    st.subheader("Thresholds")
    mde = st.slider("Smallest lift worth detecting", 0.01, 0.30, 0.10, 0.01, format="%.2f")
    alpha = st.select_slider("Significance level", [0.01, 0.05, 0.10], 0.05)
    split = st.slider("Planned share of users in treatment", 0.1, 0.9, 0.5, 0.05)

cfg = Config(variant_col=variant_col, control=control, treatment=treatment, primary=primary,
             primary_higher_is_better=primary_up, guardrails=guardrails, alpha=alpha,
             mde_relative=mde, expected_split=split)

try:
    r = analyse(df, cfg)
except Exception as e:  # bad column choices, non-numeric data, etc.
    st.error(f"Couldn't analyse this data: {e}")
    st.stop()

# ---------- Decision ----------
st.markdown(f"## :{COLOURS[r.decision]}[{r.decision.value}]")
for reason in r.reasons:
    st.write(reason)

# ---------- Checks ----------
st.subheader("Checks")
c1, c2, c3 = st.columns(3)
c1.metric("Split as planned?", "Yes" if r.srm_ok else "No",
          f"{r.n_control:,} vs {r.n_treatment:,} users", delta_color="off")
c2.metric("Big enough?", "Yes" if r.powered else "No",
          f"needs {r.required_n_per_arm:,} per arm", delta_color="off")
c3.metric("Guardrails safe?", "Yes" if not r.harmed_guardrails else "No",
          ", ".join(r.harmed_guardrails) or "nothing got worse", delta_color="off")


def row(m, role):
    pct = m.kind == "binary"
    return {
        "Metric": m.name, "Role": role,
        "Control": f"{m.control_mean:.2%}" if pct else f"{m.control_mean:,.1f}",
        "Treatment": f"{m.treatment_mean:.2%}" if pct else f"{m.treatment_mean:,.1f}",
        "Change": f"{m.rel_diff:+.1%}",
        "95% CI (difference)": (f"{m.ci_low * 100:+.2f} to {m.ci_high * 100:+.2f} pp" if pct
                                else f"{m.ci_low:+,.1f} to {m.ci_high:+,.1f}"),
        "p-value": f"{m.p_value:.3g}",
        "Verdict": ("better" if m.good_direction else "worse") if m.significant else "no clear change",
    }


st.subheader("Results")
st.dataframe(pd.DataFrame([row(r.primary, "Primary")] + [row(g, "Guardrail") for g in r.guardrails]),
             hide_index=True, width="stretch")

# ---------- Memo ----------
st.subheader("Decision memo")
use_ai = st.toggle("Write the memo with AI (needs ANTHROPIC_API_KEY)", False)
memo = None
if use_ai:
    with st.spinner("Writing memo..."):
        memo = ai_memo(r, test_name)
    if memo is None:
        st.caption("AI memo unavailable (no API key, an error, or it didn't state the decision "
                   "correctly), so showing the standard memo.")
memo = memo or template_memo(r, test_name)
st.markdown(memo)
st.download_button("Download memo", memo, file_name="decision_memo.md")

with st.expander("Preview the data"):
    st.dataframe(df.head(50), hide_index=True)
