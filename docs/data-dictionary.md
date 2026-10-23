# Data dictionary

All data in this repository is synthetic. No real customer, merchant or payment data is used.

## Synthetic kirana (`munim/simulator.py`, `SyntheticKirana(seed=2026)`)

| Field | Meaning | How it is generated |
|---|---|---|
| `customer_id` | `c0000` to `c0699` | Sequential; no names, phones or any personal data |
| `kind` | regular (25%), occasional (35%), rare (40%) | Random by seed |
| `daily_rate` | Chance of a visit on a given day | Regular 2 to 3 visits a week; occasional 0.25 to 0.55; rare 0.03 to 0.10; scaled by a weekday factor (busier Fri to Sun) |
| `lapse_day` | Day a regular stopped coming | 22% of regulars churn at a random day; 18% lapse in the last 8 weeks (a quick-commerce dark store opening nearby) |
| `post_lapse_rate` | Visit rate after lapsing | 0.7% to 1.5% a day |
| `basket_median_paise`, `basket_sigma` | Bill size | Log-normal around a per-customer median (₹150 to ₹380), clipped to ₹30 to ₹3,000 |
| `consented` | Opted in to offers | 93% |
| `offers_30d` | Offers already received in 30 days | 0 for 94%, 1 for 4%, 2 for 2% |

Transactions (`Txn`): `day` (0 to 179), `hour` (7 to 22, weighted to morning and evening peaks), `customer_id`, `amount_paise`. The seed-2026 history has 13,772 payments from 650 active customers.

Ground truth the simulator knows and Munim does not: each customer's true chance of returning in any window (`true_return_prob`) and, in a simulated campaign, the true lift.

## Segments (`munim/insights.py`)

| Segment | Rule on day *d* | Return rate used by the rules |
|---|---|---|
| `lapsed_regulars` | 8+ visits in the 69 days before the last 3 weeks, none in the last 21 days | Backtested: of customers who matched on each of the past 8 weekly reference days, the share who came back within 14 days |
| `one_time_recent` | Exactly one visit, 1 to 6 weeks ago | Same method |
| `occasional_active` | 2 to 6 visits in 60 days, at least one in the last 14 | Same method |

If a rule has no history, the return rate defaults to 50%, deliberately high, so the payback rule gets stricter rather than looser.

## Merchant policy (`MerchantPolicy`)

`weekly_budget_paise` (₹500 in the demo), `gross_margin_bps` (12%), `keep_margin_bps` (6%), `approval_threshold_paise` (₹300), `min_holdout_pct` (20), `max_holdout_pct` (50), `max_offers_per_customer_30d` (2), `max_plausible_lift_bps` (25 pp), `max_validity_days` (14), `min_eligible_customers` (10), `version`. The fingerprint is the first 16 hex characters of SHA-256 over the canonical JSON.

## Proposal (`CampaignProposal`), untrusted

`campaign_id`, `merchant_id`, `segment_id`, `name`, `customer_ids`, `reward_paise`, `min_bill_paise`, `holdout_pct`, `validity_days`, `message`, `rationale`, `attempt`, `proposed_by`. Free text is stored and shown, never used in a calculation.

## Decision

`decision` (ALLOW, GATE, DENY), `reasons` (each with `code`, `effect`, `en`, `hi`), `constraints` (the numbers that would pass: `max_reward_paise`, `suggested`, `min_bill_for_requested_reward_paise`, `min_holdout_pct`, `min_eligible_customers`, `max_treated_customers`, `max_reward_for_all_paise`, `max_reward_for_payback_paise`), `numbers` (`eligible`, `treated`, `holdout`, `max_spend_paise`, `baseline_return_bps`, `basket_used_paise`, `break_even_lift_bps`, ...), and digests of the treated and held-back customer lists.

Reason codes: `invalid_proposal`, `margin_floor`, `no_measurement`, `excluded_no_consent` (note), `excluded_frequency_cap` (note), `too_small_to_measure`, `over_budget`, `cannot_pay_back`, `unrealistic_payback`, `approval_required` (GATE), `kill_switch` (GATE), `within_rules` (note), `duplicate_campaign`, `engine_error`.

## Outcome and result (`measurement.py`)

Outcome: `treated_n`, `treated_returned`, `holdout_n`, `holdout_returned`, `spend_paise`, `avg_basket_paise`. Result adds the return rates, lift mean and 90% interval, `prob_lift_positive`, `prob_profitable`, incremental visits, revenue and margin, net, ROI, and `verdict` (WORKED if P(profit) ≥ 0.75, STOP if < 0.50, otherwise UNCERTAIN).

## Generated files (`docs/data/`)

| File | Produced by | Contents |
|---|---|---|
| `scenario.json` / `.js` | `scripts/demo.py` | The three-week run: every step's proposal, decision, Soundbox lines, results, ledger summary; byte-identical on every run |
| `eval.json` / `.js` | `scripts/eval_measurement.py` | 1,000-campaign comparison of shop-only and pooled measurement |
| `robustness.json` / `.js` | `scripts/eval_robustness.py` | The same comparison with a deliberately wrong pooled rate, other prior strengths and 5 more seeds |

The `.js` copies hold the same data so `docs/index.html` works when opened straight from disk.
