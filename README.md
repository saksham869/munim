# Munim

**The CFO for every merchant's AI growth agent.**

AI agents are starting to run cashback offers for small shops. Munim sits between a merchant's growth agent and the offer rails. It checks every offer against the shop owner's own rules before a rupee moves, keeps a comparison group so the result can be measured, stops offers that don't pay, and tells the owner everything on the Soundbox, in Hinglish.

- **Live demo:** https://saksham869.github.io/munim/ (replay a three-week run, then try to make Munim overspend)
- **Pitch deck:** [docs/Munim_Pitch.pdf](docs/Munim_Pitch.pdf) ([PowerPoint](docs/Munim_Pitch.pptx))
- Built for the Paytm Build for India AI Hackathon, Delhi 2026, **Track 1: Merchant Growth AI**

> A hackathon prototype on a synthetic shop, with a mock offers API. Not a Paytm product, and no Paytm data is used.

---

## The problem, on one bill

The growth agent's first idea for a kirana: **₹40 cashback on any bill over ₹100**, for every regular who stopped coming.

- **It gives away more than the bill earns.** A ₹100 bill earns the shop ₹12 at a 12% margin. Paying ₹40 back loses ₹28 every time the offer is used.
- **It pays people who were coming anyway.** About 22 in 100 of these regulars return within two weeks with no offer at all. They get the cashback too.
- **Nobody can tell whether it worked.** With no one held back for comparison, a losing offer looks like a winning one and keeps running.

Prompt guardrails catch none of this, because none of it is a bad prompt. It is arithmetic. **Guardrails stop bad prompts. Munim stops bad spending.**

## What Munim does

1. **The growth agent proposes** an offer: who gets it, how much cashback, on what minimum bill. It cannot pay anyone.
2. **Munim decides** with numbers it computed itself from the shop's payments: **ALLOW**, **GATE** (the owner must say yes) or **DENY** with the exact numbers that would pass.
3. **The owner answers on the Soundbox** when an offer needs a yes, and can pause all spending with one sentence.
4. **Munim reserves the budget and signs a one-time passport**; only then do the offer rails send the offer.
5. **Measurement compares** customers who got the offer with those held back, using a return rate pooled across many shops.
6. **Munim keeps or stops the offer** and tells the owner what it earned, in Hinglish.

## What happened in the demo run

`python3 scripts/demo.py` runs the full story on a synthetic shop, Sharma General Store in Ghaziabad: 650 customers, 13,772 payments over six months, average bill ₹326. The output is identical on every run.

| Step | What the agent asked for | Munim's answer |
|---|---|---|
| Win back 48 lapsed regulars, try 1 | ₹40 on ₹100+, nobody held back | **DENY**, four reasons: breaks the 6% margin floor (most it can be ₹6; suggests ₹15 on ₹250+), no comparison group, ₹1,280 worst case against a ₹500 weekly budget, and it can never pay back |
| Try 2, using Munim's numbers | ₹15 on ₹250+, 20% held back | **GATE**: inside the rules, but the ₹480 worst case is above the owner's ₹300 limit. Owner says *haan*; Munim reserves ₹480 and signs a passport |
| Nudge 30 occasional shoppers | ₹12 on ₹200+ | **DENY**: 51.3% of them come back anyway, so breaking even needs 29.0 pp more returns; plan for at most 25 pp. Largest reward that pays back: ₹10 |
| Nudge, try 2 | ₹10 on ₹200+ | **ALLOW**: ₹220 worst case, runs without bothering the owner |
| First-timers, after *"Munim, sab band karo"* | ₹10 on ₹200+ | **GATE**: allowed by the rules, but spending is paused |

Then the results came in. The simulation knows the truth, so we can check who read them correctly:

| Offer | The truth | Shop's own numbers alone | Munim (pooled return rate) |
|---|---|---|---|
| Win-back: 13 of 32 returned vs 5 of 9 held back | Works: +20 pp | **STOP** (6% chance it paid) | **Keep measuring** (93% it brought customers back, 56% it paid) |
| Nudge: 11 of 22 returned vs 0 of 6 held back | Does nothing | **WORKED** (90% chance it paid) | **STOP** (12% chance it paid) |

With groups this small, the shop's own numbers get both calls wrong. Unspent reservations (₹285 and ₹110) went back into the weekly budget. All 20 ledger entries verify; quietly editing entry 17 (the nudge's verdict) breaks verification at entry 17.

## Does pooled measurement actually help?

`python3 scripts/eval_measurement.py` simulates 1,000 campaigns of 20 to 60 customers where the true effect is known (40% of offers truly do nothing), then decides keep or stop the way a shop would see it.

| | Shop's own numbers | Munim, pooled |
|---|---|---|
| Right keep-or-stop call | 68.2% | **75.2%** |
| Profitable offers wrongly stopped | 44.7% | **24.4%** |
| Losing offers wrongly kept | **22.8%** | 25.0% |
| Average profit per campaign | ₹10.21 | **₹15.85** |

For scale: running every offer the agent wants averages −₹17.85 per campaign, and perfect hindsight would average ₹32.42. Pooling keeps slightly more losing offers because it waits for evidence before stopping; it wrongly stops far fewer good ones, which is where the money is.

## How it's built

```mermaid
flowchart LR
    A["Growth agent<br/>Paytm's agent or any LLM"] -->|proposal| P
    subgraph M["Munim"]
        T["Trusted numbers<br/>from payments"] --> P["Rules engine<br/>ALLOW / GATE / DENY"]
        P --> H["Comparison group<br/>keyed hash"]
        H --> B["Budget reserved<br/>one-time passport"]
        B --> L[("Hash-chained ledger")]
    end
    P -->|DENY + exact fix| A
    P -->|GATE| O["Shop owner<br/>on the Soundbox"]
    O -->|yes, or pause| P
    B -->|signed passport| R["Offer rails<br/>mock of Paytm offers"]
    R --> C["Customers<br/>offer or held back"]
    C -->|payments| X["Measurement<br/>pooled return rate"]
    X -->|keep or stop| P
    X -->|results in Hinglish| O
```

What it guarantees:

- **No model in the money path.** The rules are plain arithmetic on integer paise and basis points. The same proposal gets the same answer every time.
- **Fails closed.** Any exception inside the engine is a DENY.
- **The agent can't bring its own numbers.** Segments, return rates and basket sizes are computed from the shop's payments and backtested on earlier weeks.
- **Money moves only with a passport.** HMAC-signed, single use, bound to one offer, its exact customer list and the current rules version; it expires in an hour.
- **Budget is reserved first.** The worst case is held under a lock before an offer goes live and re-checked at approval time; unspent money returns after measurement.
- **Uncertain upstream calls are quarantined, not retried.** A timeout from the offer rails leaves the reservation in place until someone confirms whether the offer exists.
- **Quiet edits break the chain.** Every step is SHA-256 hash-chained; change one past entry and verification fails from there on.

### The rules, in order

| Rule | Refuses when |
|---|---|
| Shape | a field isn't a whole number, the reward isn't below the minimum bill, the length doesn't match the 14-day measurement window, customers are outside the segment |
| Margin floor | the reward would leave less than the owner's kept margin on the smallest qualifying bill |
| Comparison group | fewer than 20% of customers are held back |
| Consent and frequency | (filters, not refusals) customers who haven't opted in, or already got 2 offers in 30 days, are left out |
| Enough to measure | fewer than 10 eligible customers remain |
| Weekly budget | the worst case (every treated customer redeems) exceeds what's left this week |
| Payback | the offer can't pay back even if everyone returns, or needs more than a 25 pp lift to break even, counting cashback paid to people who would have come anyway: L* = p·r / (B·m − r) |
| Owner's limit | (GATE) worst-case spend is above the owner's auto-approve limit |
| Kill switch | (GATE) the owner has paused automatic spending |

Measurement uses Beta-binomial posteriors with a return-rate prior pooled across shops, Monte Carlo for the chance of profit, and fixed thresholds: keep when P(profit) ≥ 75%, stop below 50% (the break-even point for a risk-neutral owner), otherwise keep measuring.

## Run it

The engine needs only Python 3.9 or newer, with no packages.

```bash
git clone https://github.com/saksham869/munim.git && cd munim
python3 scripts/demo.py                  # the three-week story, step by step

pip install -r requirements-dev.txt
python3 -m pytest                        # 143 tests
uvicorn munim.api:app --port 8090        # HTTP API; interactive docs at http://localhost:8090/docs
```

The demo page is static: open `docs/index.html`, or serve the folder with `python3 -m http.server -d docs`.

Optional: set `MUNIM_LLM_BASE_URL`, `MUNIM_LLM_API_KEY` and `MUNIM_LLM_MODEL` to let any OpenAI-compatible model propose offers. Its reply is parsed strictly into a typed proposal and still has to pass every rule. It is off by default.

## Repository layout

```
munim/
  policy.py        the rules engine: ALLOW / GATE / DENY with reasons in English and Hinglish
  economics.py     margin, budget and break-even arithmetic in integer paise
  insights.py      segments and backtested return rates from payment history
  holdout.py       comparison groups picked by a keyed hash the agent can't predict
  measurement.py   Beta-binomial measurement with a pooled prior; WORKED / UNCERTAIN / STOP
  passport.py      signed, single-use, expiring spend authorisations
  budget.py        weekly budget with reservations under a lock
  ledger.py        SHA-256 hash-chained audit log
  offers.py        mock offer rails: idempotent, with timeouts Munim must handle
  engine.py        ties it together: propose, approve, execute, measure, kill switch
  agent.py         a deliberately greedy reference growth agent that replans from Munim's numbers
  llm.py           optional LLM proposer for any OpenAI-compatible endpoint
  summary.py       Soundbox lines in Hinglish and English
  simulator.py     the synthetic kirana with known ground truth
  api.py           FastAPI service
scripts/
  demo.py              the three-week run; writes docs/data/scenario.json
  eval_measurement.py  1,000 simulated campaigns; writes docs/data/eval.json
docs/              the live demo (GitHub Pages) and the pitch deck
  rules.js         the rules engine mirrored for the browser
tests/             143 tests, including test_parity.py: the browser rules must match the
                   Python engine on 1,500 random cases, message for message
```

## How it would plug into Paytm

- Proposals come from Paytm's own growth agent; Munim needs no change to how it plans.
- Segments and return rates come from the merchant's payment history.
- Approved offers go out through Paytm's offers and cashback rails, behind the same adapter the mock implements.
- Pooled return rates come from Paytm's merchant cohorts, which no single shop has.
- Decisions and results are spoken on the Soundbox the merchant already owns.

## What this prototype doesn't do yet

- **The shop is synthetic**, so the demo can show the truth next to Munim's estimate.
- **The offer rails are a mock.** They behave like a real API, including timeouts, but no money moves.
- **Pooled return rates come from 20 simulated shops**, not real cohorts.
- **Small campaigns stay uncertain for a while.** Munim says "keep measuring" rather than guessing.
- **The owner's voice rules are typed in the demo script.** Speech recognition is out of scope.
- **One merchant, one process.** The budget lock and the ledger live in memory.

## License

MIT, see [LICENSE](LICENSE). The demo page's fonts, Martel and Hind, are under the SIL Open Font License (see `docs/fonts/`).

Built by Satyam Mishra (mishrasatyam3456@gmail.com).
