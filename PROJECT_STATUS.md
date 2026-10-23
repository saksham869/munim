# Project status

Last updated 23 Oct 2026, 11:30 PM IST. Stage 1 deadline: Sat 24 Oct 2026, 11:59 PM IST (PDF upload). Offline round: 31 Oct 2026, Paytm, Noida.

## Done

- Engine: rules, measurement, passports, budget, sealed ledger, mock offer rails, HTTP API with owner and agent tokens; 180 tests passing.
- Hardening from the independent reviews: a STOP verdict blocks reruns for 30 days; the kill switch cancels live offers; the owner's limit counts the week's total; held-back customers are protected; one lock over the money path; HMAC-sealed ledger; injective passport digest; no agent text on the Soundbox; bounded inputs (`security/threat-model.md`).
- Live demo page on GitHub Pages: replay of the three-week run, a sandbox running the same rules in the browser (checked against Python on 1,500 random cases), evaluation and robustness results, architecture, limits.
- Pitch deck (11 slides, PDF 0.23 MB, 15 clickable links); every outside claim checked against a source (`research/source-register.md`, S1 to S14); unsupported claims removed; the judge review's deck fixes applied, including a consistent business model on slide 10.
- Evaluation, robustness and stress tests (`evaluation/metrics.md`); test plan; architecture; data dictionary; demo script; speaker notes; the fifteen hardest judge questions with answers (`pitch/judge-questions.md`).
- Independent reviews: security and agent architecture, skeptical judge, Paytm ecosystem and competitors. Findings and decisions are in `reviews/decision-log.md`. The statistics review was cut off by a usage limit before it reported.

## Next, for 31 October

1. Ask three kirana owners the three questions at the end of `reviews/decision-log.md`. Put nothing on a slide they did not say.
2. A live LLM proposing offers in the demo, against the same engine.
3. Use the shop's own history for the pooled return rate where it has enough.
4. Approval screen for the owner; Hindi voice flow for "sab band karo".

## Verified facts

- Stage 1 asks for a pitch with 7 named sections, uploaded as PDF, DOC or DOCX up to 2 MB (`research/event-requirements.md`).
- 1.57 crore merchants pay for Paytm payment devices (Q1 FY27).
- Paytm's Pi Sales & Marketing Agent spends on ads for small businesses and suggests the budget, which the merchant approves. No public source shows Pi running cashback offers.
- Paytm's Payment Analytics shows online merchants their new, repeat and lost customers; merchant-funded offers exist for online checkout. Nothing public covers offline QR or Soundbox merchants.
- None of the agent-payment controls reviewed (AP2, ACP, Mastercard Agent Pay, UPI pilots, Pi) checks margin, deadweight or a comparison group.
- In simulation with known truth, pooled measurement beats judging by the comparison group alone on every seed tried; the gain disappears if the pooled rate is 5 points too low, and a rate built from the shop's own history does better than the network rate when nothing has changed.

## Working hypotheses (not proven)

- Owners will accept that 1 in 5 eligible customers don't get an offer for 14 days, if it is explained in one line.
- Enough of a shop's customers pay with Paytm and opt in for campaigns of 10 or more people.
- An agent refused with exact numbers will replan inside the rules, as the reference agent does.
- Paytm would bundle a spend-control layer with its growth agents. Price and uptake in the deck are labelled assumptions.

## Unresolved risks

- No real merchant data, no real offer API and no merchant interviews: all results are simulated.
- Reach: Paytm cashback can only reach customers who pay with Paytm and opted in.
- The pooled rate is the most important number, and an underestimate (a festival fortnight) is the dangerous direction.
- Budget, ledger and used passports live in memory, in one process; the mock rails do not check passports.
- Judging criteria are not published.
