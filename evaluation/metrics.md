# What we measure, and what the numbers show

Everything here is reproducible: `python3 scripts/demo.py`, `python3 scripts/eval_measurement.py` and `python3 scripts/eval_robustness.py`. The data is synthetic, so these results show that the method behaves as designed when the truth is known. They are not evidence of real-world lift; that needs a pilot with real merchants (see the end of this file).

## 1. Correctness of the rules (deterministic)

| Metric | How it's checked | Result |
|---|---|---|
| Decision correctness on hand-built cases | `tests/test_policy.py`, `tests/test_economics.py` (exact paise arithmetic, boundaries such as reward exactly at the ceiling) | All pass |
| Same input, same answer | `test_same_inputs_same_decision` | Pass |
| Browser rules equal the Python engine | `tests/test_parity.py`: 1,500 random policies and proposals plus the 5 recorded demo decisions; decision, every reason (English and Hinglish), every constraint and number must match | All match |
| Fail closed | `test_engine_fails_closed`, `test_js_fails_closed` | Exceptions become DENY |

## 2. Does measurement keep the offers that pay and stop the ones that don't?

Setup (`scripts/eval_measurement.py`, seed 7): 1,000 simulated campaigns of 20 to 60 eligible customers with 20% held back; ₹15 cashback on a ₹350 bill at 12% margin; each shop's true return rate drawn around 22.4%; 40% of offers truly do nothing, the rest lift returns by 5 to 30 points. Both methods use the same rule: stop when the chance of profit is below 50%.

| | Shop's own numbers | Munim, pooled return rate |
|---|---|---|
| Right keep-or-stop call | 68.2% | 75.2% |
| Profitable offers wrongly stopped | 44.7% | 24.4% |
| Losing offers wrongly kept | 22.8% | 25.0% |
| Average profit per campaign | ₹10.21 | ₹15.85 |

Baselines for scale: keeping every offer averages −₹17.85 per campaign; perfect hindsight averages ₹32.42.

## 3. Robustness (`scripts/eval_robustness.py`)

The headline uses a pooled rate centred exactly on the simulated network mean. A real pooled rate will be off, so the same 1,000 campaigns (identical draws and Monte Carlo seeds, so the "correct" row reproduces section 2 exactly) were re-scored with the pooled rate deliberately wrong.

| Pooled rate vs truth | Right calls | Good offers stopped | Losing offers kept | Profit per campaign |
|---|---|---|---|---|
| 10 points too low | 56.8% | 2.7% | 71.2% | −₹3.30 |
| 5 points too low | 69.5% | 8.8% | 45.5% | ₹9.53 |
| Correct | 75.2% | 24.4% | 25.0% | ₹15.85 |
| 5 points too high | 74.8% | 45.5% | 11.2% | ₹14.79 |
| 10 points too high | 69.7% | 68.5% | 3.9% | ₹10.23 |
| Shop's own numbers (no pooling) | 68.2% | 44.7% | 22.8% | ₹10.21 |

- Prior strength barely matters: 20, 60 and 120 give 74.9%, 75.2% and 74.5% right calls.
- On 5 further random seeds pooling beat shop-only every time: +4.7 to +8.4 points of right calls and +₹4.15 to +₹7.54 profit per campaign.
- **The risk is asymmetric.** A pooled rate that is too low makes deadweight look like lift, so losing offers survive; 5 points too low already erases the gain. A rate that is too high only makes Munim cautious. The pooled rate must therefore come from recent, comparable history, and when unsure it should be shaded upward. That shading is not implemented yet.

### Stress test from the independent judge review (`scripts/stress_test.py`)

1,000 campaigns per scenario, 2,000 Monte Carlo samples per evaluation, seed 7. Each scenario changes one setting; "comparison group alone" is the shop judging by its own held-back customers with no pooling.

| Scenario | Keep every offer | Comparison group alone | Pooled |
|---|---|---|---|
| A. Repo settings | −₹17.85 | ₹10.25 | ₹16.06 |
| B. Pooled rate from the shop's own six months, no network | −₹16.08 | ₹9.77 | **₹23.03** |
| C. Festival fortnight: true return rate 6 points above history | −₹46.20 | −₹0.36 | −₹3.97 |
| D. Slow fortnight: 6 points below history | ₹10.49 | ₹23.44 | ₹26.00 |
| E. Only 20% of offers do nothing (repo assumes 40%) | ₹14.71 | ₹21.46 | ₹29.13 |
| F. Small cashback lifts, 0 to 10 points | −₹80.59 | −₹17.29 | −₹18.98 |

What it shows:
- **The shop's own history is a better baseline than the network when nothing has changed** (B). The network rate matters for shops or segments without enough history. Using the shop's own history first is the next step; today's code uses the network rate.
- **A festival fortnight hurts every method** (C), and pooling on a historical rate does worst on profit. That is the "too low" row of the table above.
- **"Keeping every offer loses money" is an assumption, not a finding** (E): with fewer offers that do nothing, keeping everything is profitable, though measurement still adds money.
- **If cashback barely moves customers, every method loses money** (F). Measurement stops most of these offers after their first run, and the weekly budget caps the loss on that run.
- Counting the test run itself, the pooled method is about break-even over two runs in scenario A (−₹1.79).
- The same script replays the demo's two campaigns 400 times with the same customers: judging by the comparison group alone got both calls wrong in 24.2% of replays; the pooled method got both right in 63.8%. The exact counts in the demo run have odds of about 1 in 5,200.

## 4. The demo run (one shop, `scripts/demo.py`, seed 2026)

| Offer | Truth | Shop's own numbers | Munim |
|---|---|---|---|
| Win-back: 13 of 32 returned vs 5 of 9 held back | +20 pp | STOP (6% chance it paid) | Keep measuring (56% it paid) |
| Nudge: 11 of 22 returned vs 0 of 6 held back | 0 pp | WORKED (90% it paid) | STOP (12% it paid) |

One run shows the mechanism, not a rate; section 2 is the rate.

## 5. Product and reliability metrics

| Metric | Value in the prototype | How |
|---|---|---|
| Decision latency | Milliseconds (pure Python arithmetic, no model call) | The policy engine has no I/O |
| Model cost per decision | ₹0: no model in the decision path | The optional LLM only drafts proposals |
| Fallback when the LLM fails | The proposal is refused, never repaired | `tests/test_llm.py` (6 malformed replies, odd endpoint responses) |
| Upstream timeout handling | Quarantined, budget stays reserved, not retried | `test_upstream_timeout_is_quarantined_not_retried` |
| Tamper evidence | Any edited, deleted or reordered ledger entry is detected; a full rewrite fails the HMAC seals | `tests/test_controls.py`, `tests/test_hardening.py` |

## What would show real-world value (not done yet)

A pilot with a few dozen real merchants, comparing offers run through Munim with offers run without it, measured on margin-adjusted repeat revenue over 8 weeks; and a calibration check that "70% chance it paid" comes true about 70% of the time on real outcomes.
