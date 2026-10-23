# Opportunity scorecard

Eight Merchant Growth AI ideas, scored 1 to 5 on the brief's weighted criteria. Scores are the team's judgments with stated reasons, not measurements. Evidence references point to `research/source-register.md` (S-numbers). This scorecard was written on 23 Oct 2026 to document a choice first made on 22 Oct; it was re-checked against new evidence (S4: Paytm's Pi agent already suggests ad budgets) and the choice held.

Weights: merchant value 20%, differentiation 20%, demonstrable outcome 20%, feasibility before the deadline 15%, AI-specific advantage 10%, Paytm fit 10%, privacy and safety 5%.

| # | Idea | Value | Diff. | Demo | Feasible | AI | Paytm fit | Safety | Weighted |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Spend authority and measurement for growth agents (Munim)**: allow, ask or refuse each agent-proposed offer against the owner's margin and budget, count deadweight, keep a comparison group, stop what doesn't pay | 4 | 5 | 5 | 4 | 3 | 5 | 5 | **4.45** |
| 2 | Win-back recommender: segment lapsed customers and suggest an offer | 4 | 2 | 4 | 5 | 3 | 4 | 4 | 3.65 |
| 3 | Conversational copilot on the Soundbox or WhatsApp: "aaj kitni sale hui?" answered from payments | 3 | 2 | 3 | 4 | 4 | 4 | 3 | 3.15 |
| 4 | Offer and ad copy generator for WhatsApp and social | 3 | 1 | 4 | 5 | 4 | 3 | 4 | 3.25 |
| 5 | Stock reorder and demand forecast for kiranas | 4 | 3 | 2 | 2 | 3 | 2 | 4 | 2.80 |
| 6 | Discount and price optimiser per item | 4 | 3 | 2 | 2 | 3 | 2 | 3 | 2.75 |
| 7 | Working-capital readiness coach (when to take a loan, how much) | 4 | 2 | 2 | 3 | 3 | 4 | 1 | 2.80 |
| 8 | Peak-hour and staffing planner from payment timestamps | 2 | 3 | 3 | 5 | 2 | 3 | 5 | 3.10 |

## Why each was scored as it was

1. **Munim.** Value: agents that spend merchant money already exist (S4), and an unprofitable offer costs real money on thin margins (S8). Differentiation: no public Paytm or competitor material describes margin checks, deadweight-aware payback or comparison groups for agent spend (to be re-confirmed by the competitor review). Demo: refusals with exact numbers and measured results are visible in one run. AI advantage is deliberately moderate: the model drafts and phrases; arithmetic decides. Main risk: it depends on agents actually being given budgets, and on pooled return rates being estimated well (`evaluation/metrics.md`).
2. **Win-back recommender.** Useful and easy, but segmentation is a commodity and the brief notes Paytm may already show repeat and churn trends. Munim keeps this as an input, not the product.
3. **Conversational copilot.** Natural for the Soundbox, but it is the "chatbot on a dashboard" the brief warns against, and text-to-SQL over payments invites wrong numbers spoken with confidence.
4. **Copy generator.** Pi's marketing agent already writes ad images and copy (S4).
5. **Stock and demand.** Payments carry amounts, not items, so the data to do it well isn't in Paytm's payment stream; a demo would rest on invented SKU data.
6. **Price optimiser.** Same data gap as 5, plus the risk of the model setting prices.
7. **Working-capital coach.** Consequential financial advice is a credit decision in disguise; closer to Track 2 and hard to make safe.
8. **Staffing planner.** Easy and safe, but small value for a kirana run by its owner.

## Top three and the decision

1. **Munim (4.45)**, selected.
2. Win-back recommender (3.65): absorbed into Munim as the trusted-insights step, not sold as new.
3. Offer and ad copy generator (3.25): left to the growth agent; Pi's marketing agent already does it (S4).

The conversational copilot (3.15, fourth) survives only as the Soundbox voice interface for rules, approvals and results, never as the decision-maker.
