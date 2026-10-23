# The hardest questions for the offline round (31 Oct, Noida)

Drafted by the independent judge review on 23 Oct 2026, then updated after the fixes it asked for were made. Every answer is true of the repo as it stands. **[Top 5]** marks the questions most likely to sink the entry if answered badly.

Numbers come from `docs/data/eval.json`, `docs/data/robustness.json`, `docs/data/scenario.json` and `scripts/stress_test.py`. Sources S1–S14 are in `research/source-register.md`.

---

**1. [Top 5] "Your slide says 'no LLM inside'. Where is the AI, and did any AI run in your demo?"**

No model runs in the recorded demo. The agent there is a scripted reference agent, so every run is identical, and the Soundbox lines are fixed phrases filled with engine numbers. Two parts are AI: an optional LLM proposer for any OpenAI-compatible model, whose reply is parsed strictly and still has to pass every rule; and Bayesian measurement that pools return rates. Keeping the model out of the decision is deliberate: an LLM may draft an offer, but arithmetic decides whether the merchant's money moves, so every decision can be audited and replayed.
- *Grounding:* `munim/agent.py`; `munim/llm.py` (off unless the `MUNIM_LLM_*` variables are set; tested with a stub, never against a live model); `munim/summary.py`.
- *Prep:* run the LLM proposer live on stage against the engine for three attempts.

**2. [Top 5] "Paytm already shows merchants their repeat customers, Pi already suggests budgets the owner approves, and the AI Soundbox already answers business questions. What does Munim add?"**

Those exist. Paytm's Payment Analytics shows online merchants their new, repeat and lost customers (S12). Pi suggests an ad budget and the owner approves it (S4). The AI Soundbox answers questions in 11 languages (S9). Merchant-funded offers exist for online checkout, with a per-offer cap (S13). None of these checks a spend against the shop's margin, discounts the customers who would have come back anyway, or keeps a comparison group (S11). Munim is that check: it refuses an offer that cannot pay back, caps the week's exposure, keeps a comparison group the agent cannot choose, and records all of it in a sealed ledger. Pi does not run cashback today, so Munim covers a lever Pi does not yet pull.
- *Grounding:* `munim/policy.py`; `munim/economics.py` `break_even_lift_bps`; `research/paytm-ecosystem.md`.

**3. [Top 5] "Most of a kirana's UPI customers pay with PhonePe or Google Pay. How does a Paytm cashback reach them, and where does consent come from?"**

It cannot reach them. The realistic audience is customers who pay with the Paytm app and have opted in, probably a minority of a shop's payers. The deck says so ("Cashback to Paytm payers who opted in"). Our simulator assumes 93% have opted in, which flatters the demo. Munim refuses any campaign with fewer than 10 eligible customers, so many real segments would be refused as too small. Reachable, consented customers per shop is the first number to size with Paytm. On consent, Munim never assumes it: a payments file with no consent column means nobody can receive an offer.
- *Grounding:* `munim/simulator.py` (`consented=rng.random() < 0.93`); `MerchantPolicy.min_eligible_customers = 10`; `munim/ingest.py`.

**4. "What is the difference between '56% chance it paid' and the 93% in your data?"**

93% is the chance the offer brought anyone back at all. 56% is the chance it brought back enough to pay for its cashback, so the verdict was UNCERTAIN: keep measuring. The deck and the page both show 56%. The narrower, fair claim: judged only by its 9-person comparison group, the shop would have stopped an offer that truly worked; the pooled baseline avoided that mistake, but did not prove a profit.
- *Grounding:* `docs/data/scenario.json`, the day-14 outcome (`prob_lift_positive` 0.929, `prob_profitable` 0.563).

**5. "Your demo needed 5 of 9 held-back regulars to come back by chance. Isn't that cherry-picked?"**

Yes, it was picked to illustrate. Those exact counts are rare, about 1 in 5,200 at the simulation's true return rates. Replaying the same two groups 400 times, judging by the comparison group alone got both calls wrong 24% of the time; the pooled method got both right 64% of the time. The evidence is the 1,000-campaign test: the pooled method makes the right keep-or-stop call 75% of the time against 68%, and wrongly stops 24% of profitable offers against 45%. It keeps slightly more losing offers (25% against 23%).
- *Grounding:* `scripts/stress_test.py` (tail odds and the 400 replays); `scripts/eval_measurement.py`.

**6. "Your simulation centres every shop on exactly the return rate your prior uses. What happens in Diwali week? And why pool at all, when the shop's own history gives 21.9% against the network's 22.4%?"**

When the pooled rate is wrong, pooling gets worse. With a rate 5 points too low, it keeps 45.5% of losing offers and earns ₹9.53 per campaign against ₹10.21 for the shop's comparison group alone; 10 points too low, it loses money. A festival fortnight makes a historical rate too low in exactly this way. On history: the judge's stress test built the rate from the shop's own six months and it did better still (₹23.03 against ₹9.77 in that run), as long as nothing had changed. So the honest design is a pooled rate from the shop's own recent history where it has enough, and from similar shops where it does not. That change is the next step; today's code uses the network rate.
- *Grounding:* `docs/data/robustness.json`; `scripts/stress_test.py` scenarios B and C; `munim/simulator.py` `pooled_priors()`.

**7. [Top 5] "Your headline benefit is ₹15.85 per campaign. It assumes 40% of offers do nothing, and the money is spent before you 'stop' anything. What is the real value to a merchant?"**

₹15.85 is the value of the keep-or-stop call on an offer's next run, under settings we chose. If only 20% of offers do nothing, keeping every offer is already profitable (+₹14.71). Counting the test run, Munim is about break-even over two runs (−₹17.85 + ₹15.85). The surer value comes before any money moves: the agent's first offer risked ₹1,280 and would lose money even if every customer came back; Munim refused it with the exact fix, and the approved offer risks at most ₹480. Whatever goes wrong, the most a merchant can lose is the weekly budget he set.
- *Grounding:* `scripts/eval_measurement.py`; `scripts/stress_test.py` scenario E; the first steps in `scenario.json`.

**8. "When Munim says 'stopped', what actually stops? And if I say 'Munim, sab band karo' while an offer is live?"**

Offers run a fixed 14 days, so an offer has ended by the time it is measured. A STOP verdict then blocks the agent from rerunning it: an offer of the same or higher cashback to the same group is refused for 30 days. "Sab band karo" cancels every live offer, returns its unspent budget, and holds every new offer for the owner's yes. If the offer service gives an unclear answer to a cancel, the offer is quarantined for a person to check, as on creation.
- *Grounding:* `recently_stopped` in `munim/policy.py` and `docs/rules.js`; `Munim.set_kill_switch` in `munim/engine.py`; `tests/test_hardening.py`.

**9. "Can the agent get around Munim?"**

Not through the API. The agent's token can only propose, so approve, reject and the kill switch return 403. The owner's "ask me first" limit counts the week's total, so splitting an offer does not dodge it. Customers held back by a live offer are left out of the next one. One lock covers the money path, so concurrent proposals cannot break the frequency cap. What remains: the mock offer service does not check the passport, so in production the rails must check it too; with no tokens set the API runs open as a local demo; and the budget lock holds within one process.
- *Grounding:* `munim/api.py`; `munim/policy.py`; `security/threat-model.md`.

**10. "Why would a kirana owner agree to hold back his own regulars from a win-back offer?"**

Many won't, if it is put as "held back". They know those people and fear losing them. It is 1 in 5 eligible customers for 14 days, the price of knowing whether the cashback did anything. A better design, not built yet: give them the same offer once the 14 days are up if it worked. We have not asked owners yet; this is the first question to ask.
- *Grounding:* `MerchantPolicy.min_holdout_pct = 20`.

**11. "Kirana margins vary by item. How can you promise 'at least 6% on every bill' when you only see the bill amount?"**

We can't, and the deck no longer says it. It says "at least 6% kept on a bill at your usual margin": the floor uses one blended margin the owner states (12% in the demo), so a ₹250 bill of mostly atta and oil could lose money on ₹15 cashback. Doing better needs basket or category data, for example from a billing app.
- *Grounding:* `MerchantPolicy.gross_margin_bps`; `munim/economics.py` `reward_ceiling_paise`.

**12. "Who pays for Munim? And isn't a fee on offers Munim marks as worked a conflict of interest?"**

The proposal is to bundle Munim into Pi Agents and never bill it alone: merchants would pay for agent-run offers, and the checks come with them. The ₹99 a month on the slide illustrates scale for that offers feature; it is an assumption to test, not a price. An outcome fee is optional and later, and yes, it would make the referee a player. If it is ever used, the keep-or-stop rules are fixed before the offer runs and every verdict can be rechecked by the owner from the comparison group recorded in the ledger. The first step is a pilot, not pricing.
- *Grounding:* deck slide 10; `munim/measurement.py` (keep at 75% or above, stop below 50%, fixed in code).

**13. "Why should Paytm not just build this itself?"**

It might. Pi's product hiring post names "incremental revenue" and "guardrails" among the goals (S7), which suggests Paytm sees the same problem. Munim is built to be adopted rather than to compete: plain Python with no dependencies in the engine, deterministic and replayable, and an API that takes a growth agent's proposals as they are.

**14. "Your ledger is 'tamper-evident'. Who stops you from rewriting it? And how do you erase a customer's data from an append-only chain?"**

Each entry is hash-chained and sealed with an HMAC key the export never contains, so an edit breaks the chain and a full rewrite fails the seals. Whoever holds the key could still rewrite it, so in production the head hash should be anchored outside Munim, for example shown in the owner's app each day. On erasure: customer ids never enter the ledger (it stores digests and counts), but proposals' free text does, so production should keep only a hash of free text in the chain and the text in a separate, erasable store.
- *Grounding:* `munim/ledger.py`; `security/threat-model.md` sections 6 and 7.

**15. [Top 5] "Has a single merchant seen this?"**

No, not yet. Everything about owners in the deck comes from published sources or the simulation, and the deck labels which is which. Before the offline round we plan to ask three kirana owners whether they would let an app give ₹15 cashback to customers who stopped coming, whether they would keep 1 in 5 out to check it worked, and how they want to approve: a button, the app or by voice. Only what they actually say will go on a slide.
