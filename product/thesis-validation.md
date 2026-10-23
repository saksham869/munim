# Thesis validation

The brief's leading thesis: *a merchant growth agent that turns sales records into a margin-aware customer-recovery action.* This file checks Munim against each step of that thesis and against what Paytm already ships.

## Step by step

| Thesis step | Munim | Evidence |
|---|---|---|
| 1. Open an app or import a sample sales file | `scripts/import_payments.py` loads a payments CSV with row-level validation; the live page replays a full run | `tests/test_ingest.py` |
| 2. Summarise what the records show | Segments with size, average bill and backtested return rate | `munim/insights.py`; demo step 2 |
| 3. Find an opportunity, or an offer that would destroy margin | Lapsed regulars who used to spend ₹1,28,000 a month; and the agent's ₹40 offer that loses ₹28 a bill | Demo steps 2 and 3 |
| 4. Show evidence and uncertainty | Every refusal quotes its numbers; results come with the chance of profit, not a point estimate | `munim/measurement.py` |
| 5. The merchant asks a question in natural language | **Not built as free-form chat.** The owner speaks rules and approvals to the Soundbox; free-form Q&A over sales data was excluded (scorecard idea 3) | `product/opportunity-scorecard.md` |
| 6. Recommend a specific action | The growth agent proposes a concrete offer; after a refusal, Munim returns the exact numbers that would pass | `constraints` in every DENY |
| 7. A deterministic rule engine checks it | `munim/policy.py`, mirrored in the browser and checked on 1,500 random cases | `tests/test_policy.py`, `tests/test_parity.py` |
| 8. Preview, see impact and assumptions, approve | GATE asks the owner with the worst-case spend; approval re-runs every rule | `test_approval_rechecks_with_fresh_state` |
| 9. Record the action; real results only if available, otherwise labelled simulated | Hash-chained ledger; every result in the demo is labelled simulated, with the truth shown beside it | `munim/ledger.py`; demo steps 8, 9 and 12 |

## Where the thesis had to change

Segmentation and win-back suggestions alone are not defensible: they are standard, and Paytm already runs an agent that plans campaigns and suggests budgets (S4). The thesis survives only with the differentiators below, each of which is demonstrated and tested:

| Differentiator | Demonstrated | Tested |
|---|---|---|
| Margin-aware limits on each offer, with the exact fix | Demo step 3, sandbox | `test_margin_floor_denies_and_says_how_to_fix` |
| Payback that counts cashback paid to people who'd come anyway | Demo step 6 (nudge refused) | `test_deadweight_customers_are_not_paid_to_do_what_they_do_anyway` |
| A comparison group the agent can't pick | Demo step 5 | `test_agent_cannot_choose_the_comparison_group` |
| Closed loop: approve, spend, measure, keep or stop, budget returned | Demo steps 5 to 9 | `test_deny_then_replan_then_approve_then_measure` |
| Measurement that works for a 30-customer campaign | Proof section, `evaluation/metrics.md` | `scripts/eval_measurement.py`, `scripts/eval_robustness.py` |
| Hinglish explanations from engine numbers, never from a model | Every Soundbox line | `test_every_reason_speaks_both_languages`, `test_lines_quote_engine_numbers` |

## What would falsify it

- Paytm's agents never get spending authority beyond suggesting an ad budget, so there is nothing to authorise. Partly answered: S4 shows the agent already proposes the budget.
- Merchants refuse comparison groups even when explained. Untested; needs a pilot.
- Pooled return rates can't be estimated within about 5 points. Untested on real data; `evaluation/metrics.md` shows why it matters.
