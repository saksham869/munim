# Decision log

What the independent reviews found, where they disagreed with the original design or with each other, and what was decided. All reviews ran on 23 Oct 2026.

## The reviews

Each review was done by a separate AI agent with its own brief. None saw another's output. None was a real Paytm employee, judge or merchant.

| Review | Brief | Output |
|---|---|---|
| Security and agent architecture | Attack the money path; check privacy against the DPDP Act and OWASP's LLM risks | `security/threat-model.md` |
| Skeptical judge | Role-play a judge from Paytm's merchant business plus a field researcher who knows Delhi NCR kiranas; score the Stage 1 PDF; stress-test the claims | This log, `pitch/judge-questions.md`, `scripts/stress_test.py` |
| Ecosystem and competitor research | What Paytm and others already offer, with sources opened and quoted | `research/paytm-ecosystem.md`, `research/competitors.md`, `research/merchant-problems.md` |
| Statistics and evaluation | Recheck the measurement claims | **Not completed.** A usage limit stopped it before it reported. The judge's stress test and `scripts/eval_robustness.py` cover the main statistical questions; no separate statistics review exists |

**Two cautions.**
- The judge's "field experience" (peak hours, owners knowing regulars by face, a lane that talks) is informed judgement from an AI role-play, not interviews.
- No kirana owner has been asked anything yet. That is the most important gap in the evidence (see the end of this log).

The judge scored the deck before these fixes at 6.2 out of 10 on criteria it assumed, since the event publishes none: "Shortlist: yes, with conditions... It would not win as submitted." Its scores are not repeated after the fixes; nobody can promise a result.

## Decisions

| # | Topic | What reviewers said | Decision | Status |
|---|---|---|---|---|
| 1 | "Stopped" and "sab band karo" | Judge: a STOP verdict stopped nothing (offers end at day 14 anyway, and the agent could rerun it next week), and the kill switch only set a flag while live cashback kept paying | Make the words true in code, rather than soften them. New rule `recently_stopped` (no rerun for 30 days); the kill switch cancels live offers and returns their budget; the UNCERTAIN line now says the offer has ended | Done, tested |
| 2 | Agent bypasses | Judge and security: anyone who could propose could approve; the owner's limit could be split across two offers; a new offer could pay another offer's held-back customers; concurrent proposals broke the frequency cap | Owner and agent tokens; the limit counts the week's total; held-back customers are left out of other offers; one lock over the money path | Done, tested |
| 3 | Ledger and passport | Security: an unkeyed chain can be rewritten; the passport digest collided; Munim checks its own passport, the rails do not | HMAC seal on every entry; injective digest plus a count check. Said plainly that production rails must check the passport | Done; anchoring the head and rail-side checks remain open |
| 4 | Approving by voice | Original design: the owner says "haan". Judge (field role): he says "haan" to customers all day, and a helper or a child could approve spending | Approvals are a tap: on the AI Soundbox screen, or in the app for older boxes. Voice can only stop things, because stopping is always safe | Done in the deck and summaries. Residual: anyone at the counter can tap (threat model) |
| 5 | What the Soundbox says aloud | Judge: refusals read out margins in front of customers, and English agent names sat inside Hinglish. Security: the agent's offer name was spoken verbatim, so it could put words beside the verdict | No agent text on the Soundbox. Offers are named by their terms ("₹15 cashback on ₹250+"). A refusal is one neutral line pointing to the app | Done, tested |
| 6 | Slide 6 compared two different probabilities | Judge: "93% it brings customers back" stood next to the shop's "6% chance of profit"; Munim's chance of profit was 56%, UNCERTAIN | Deck now says "Keep measuring (56% chance it paid)", labels the run "One run, picked to illustrate", and points to the 1,000-campaign test | Done |
| 7 | Headline value | Judge: ₹15.85 per campaign rests on chosen settings, values a rerun, and is about −₹2 over two runs counting the test run | Lead with the value that needs no simulation: the agent's first offer risked ₹1,280 and would lose money even if every customer came back; Munim refused it and the approved one risks at most ₹480. The ₹15.85 stays, labelled as a simulation of the keep-or-stop call | Done (slide 9) |
| 8 | Network prior or the shop's own history | Judge's stress test: a prior built from the shop's own six months beat the network prior when nothing had changed (₹23.03 against ₹9.77 for the shop's comparison group alone, in that scenario); in a festival fortnight, the network-prior method lost more than the shop's comparison group (−₹3.97 against −₹0.36) | Keep the network prior in the Stage 1 demo, because that is what the engine does today, but stop claiming one shop's data is too small: its comparison group is. Publish the robustness table and the stress test. Next step for 31 Oct: use the shop's own history where it has enough | Wording done; the code change is planned |
| 9 | Where is the AI? | Judge: no model runs in the demo, and "no LLM inside" invites "so where is the AI?" at an AI hackathon | Keep the model out of the decision path (an LLM may draft an offer; arithmetic approves the spend), and say so. The optional LLM proposer (`munim/llm.py`) exists and is tested with a stub. A live LLM proposing on stage is the first item for 31 Oct | Open |
| 10 | Pi's role | Research: Pi suggests Meta ad budgets, not cashback | Deck says "Any LLM today, Pi agents later" and "Today Pi suggests ad budgets; Munim checks the offers step" | Done |
| 11 | Reach and consent | Judge: Paytm cashback can only reach customers who pay with Paytm and opted in; the simulator assumes 93% consent | Say it on the deck ("Cashback to Paytm payers who opted in") and the page. Reachable, consented customers per shop is the first number to size with Paytm | Stated; unmeasured |
| 12 | One blended margin | Judge: a ₹250 bill of mostly atta and oil can lose money on ₹15 cashback | Wording now "At least 6% kept on a bill at your usual margin". Category margins need basket data | Open |
| 13 | Holding back regulars | Judge (field role): owners will resent holding back regulars from a win-back offer. The measurement needs a comparison group | Keep 1 in 5 held back, because without it no verdict is possible. Explain it plainly, as slide 3 now does: "1 in 5 customers don't get it for 14 days, so we can tell if it worked." Not built: offering the same deal to the held-back customers after 14 days if it worked | Open; ask owners |
| 14 | Business model | Judge: "Paid when it works" contradicted "Bundled"; a fee on offers Munim marks as worked lets the referee grade itself; ₹99 a month exceeds the simulated value; "Beyond kiranas" is unsupported; "Munim ships with Pi Agents" read like a partnership | Slide 10 rewritten as a labelled proposal: bundled into Pi Agents and never billed alone; the price illustration is for agent-run offers, not Munim by itself; any outcome fee uses rules fixed before the offer runs and a ledger the owner can recheck; "Beyond kiranas" replaced by a proposed pilot | Done |
| 15 | Tagline | Judge suggested "The trusted munim behind every merchant's AI copilot", in the brief's own words | Kept "The CFO for every merchant's AI growth agent". It is already on the live page, the repo and the deck, and "CFO" names the job: limits, payback, proof. Accepted risk: "a CFO for an agent?" may confuse a judge for a second | Kept |
| 16 | Slide 2 headline, "Nobody is the CFO" | Judge (low): the owner already approves Pi's budget, so somebody is | Kept as a metaphor for checking the arithmetic, which is what nobody does today (source register S11) | Kept |
| 17 | Competitive risk | Research: Pi's hiring post names "incremental revenue" and "guardrails" as goals, so Paytm could build this itself | Position Munim as the check Pi would adopt, not a rival product. The hiring post is not quoted in the deck | Accepted risk |
| 18 | Multi-agent design | Considered planner, critic and executor agents | One proposer plus a deterministic engine. Extra agents add failure modes without adding evidence (`research/technical-options.md`) | Done |

## The biggest gap: no merchant has been asked

The judge's last suggestion still stands: talk to three kirana owners before 31 Oct and put nothing on a slide that they did not say. Three questions:

1. Would you let an app give ₹15 cashback to customers who stopped coming?
2. Would you keep 1 in 5 of them out, to check whether it worked?
3. How do you want to approve: a button, the app, or by voice?
