# Demo scenario

The demo replays one deterministic run of the real engine (`python3 scripts/demo.py`, seed 2026). Re-running the script produces a byte-identical `docs/data/scenario.json`.

**Shop.** Sharma General Store, a synthetic kirana in Ghaziabad: 650 active customers, 13,772 payments over six months, average bill ₹326. Gross margin 12%.

**Owner's rules.** ₹500 a week for growth, keep at least 6% margin on every bill, ask before any offer that could cost more than ₹300.

**What Munim computes from the payments.**

| Group | Customers | Come back in 14 days anyway | Average bill |
|---|---|---|---|
| Regulars who stopped coming | 48 | 21.9% | ₹341 |
| First-timers who never came back | 16 | 9.5% | ₹225 |
| Occasional shoppers | 129 | 51.3% | ₹277 |

**The story, step by step.**

1. The agent asks for ₹40 on ₹100+ for all 48 lapsed regulars, nobody held back → **DENY** (margin floor, no comparison group, ₹1,280 over the ₹500 budget, can never pay back).
2. It replans with Munim's numbers: ₹15 on ₹250+, 20% held back → **GATE** (₹480 worst case > ₹300). The owner approves; Munim re-checks, reserves ₹480, signs a passport; the mock rails create the offer for 32 customers, with 9 held back.
3. The agent offers ₹12 to 30 occasional shoppers → **DENY**: half of them come anyway, so breaking even needs a 29-point lift (plan for 25 at most).
4. ₹10 on ₹200+ → **ALLOW**: ₹220 worst case, runs without asking.
5. Day 14, win-back: 13 of 32 returned vs 5 of 9 held back. Shop's own numbers say STOP (6% chance it paid); Munim says keep measuring (93% it brought customers back). Truth: +20 points.
6. Day 21, nudge: 11 of 22 vs 0 of 6. Shop's own numbers say WORKED (90%); Munim says STOP (12%). Truth: no effect. ₹110 goes back into the budget.
7. The owner says "Munim, sab band karo". The agent's next offer would pass every rule but now waits for a human.
8. The ledger has 20 entries and verifies; editing entry 17 breaks verification at entry 17.

**What is simulated.** The customers, their behaviour, the true effect of each offer, the offer rails and the owner's voice. What is not simulated: every decision, number, reason and Soundbox line, all produced by the engine.
