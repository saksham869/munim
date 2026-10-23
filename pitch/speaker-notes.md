# Speaker notes

For `docs/Munim_Pitch.pdf`. About 4 minutes with the deck, then the live demo (`demo/script.md`). Say numbers exactly as written; every one is in `research/source-register.md` or reproducible from `scripts/`. The hardest questions and their answers are in `pitch/judge-questions.md`.

**1. Title.** "Munim is the CFO for every merchant's AI growth agent. Paytm is giving merchants agents that can spend money on growth. Munim decides how much they may spend, makes every offer prove itself, and stops what doesn't pay. This line on the Soundbox is what the owner sees; he taps Haan or Nahi."

**2. Problem.** "1.57 crore merchants pay for Paytm devices. Paytm's Pi Sales and Marketing Agent already spends on ads for small businesses: Pi suggests the budget, the owner taps approve. Cashback to a shop's own customers is the next lever, and the riskier one. Give an agent a budget and three things go wrong: ₹40 back on a ₹100 bill, when the shop earns ₹12; cashback paid to people who'd come anyway; and no way for one shop to tell what worked."

**3. Solution.** "Five steps. The owner sets three rules once, by voice on the AI Soundbox or in the app. Any LLM today, Pi agents later, proposes an offer. Munim allows it inside the rules, holds big spends until the owner taps Haan, or refuses with the exact fix. A signed, single-use passport releases it, and 1 in 5 customers don't get it for 14 days, so we can tell if it worked. On day 14 Munim reports in Hinglish: run it again if it paid; if not, no rerun for 30 days. 'Munim, sab band karo' cancels running offers and holds every new one."

**4. How it works.** "The agent is untrusted and holds no money or keys. Return rates come from payments, never from the agent. The engine has no model inside: it's arithmetic on paise, and any error means no. Every step is hash-chained and sealed."

**5. Demo run.** "Six real engine decisions on a synthetic kirana. The greedy first try gets four refusals, each with a fix. The replan needs the owner's OK. A nudge to shoppers who come anyway is refused, then allowed smaller, then measured: it didn't pay, so the agent can't rerun it for 30 days. The kill switch holds the next offer."

**6. Proof.** "A shop's comparison group is too small: with 6 to 9 people held back, chance decides. In this one run, picked to illustrate, judging by that group alone would have stopped the offer that worked and kept the one that didn't. The evidence is 1,000 simulated campaigns: right calls rise from 68% to 75%, and profit per campaign is ₹15.85 against ₹10.21, or minus ₹17.85 if you keep every offer. Honest caveat: the pooled rate must be right. Five points too low, say in a festival fortnight, erases the gain."

**7. Tech.** "Python with no dependencies for the engine, FastAPI, Bayesian measurement, signed passports, a sealed hash chain, and the same rules in the browser, tested against Python. It plugs into the AI Soundbox, Pi agents, payments data and the offer rails."

**8. USP.** "Guardrails stop bad prompts; Munim stops bad spending. Payment controls like AP2 cap amount, payee and time, and Pi asks the owner to approve a budget. None checks margin, deadweight or a comparison group. Refusals go to the app, never out loud at the counter."

**9. Impact.** "The number to remember: the agent's first offer risked ₹1,280 and would lose money even if every customer came back. The one the owner approved risks at most ₹480. Merchants get a hard weekly cap and a kept margin. Paytm gets agents merchants keep paying for. Customers get offers only if they opted in, at most two in 30 days."

**10. Business model.** "This is a proposal. Munim would ship inside Pi Agents and never be billed alone: merchants pay for agent-run offers, and the checks come with them. Paytm gets cashback offers it can sell to a kirana, with the weekly budget as the worst case. An outcome fee is optional and later; its rules are fixed before an offer runs, and the owner can recheck every verdict in the ledger. Before any price, a pilot: 50 kiranas for 8 weeks. ₹18.6 crore is an illustration if 1% of device merchants paid ₹99 a month for agent-run offers."

**11. Close.** "Let the agent grow the shop. Munim keeps the money safe. Next, for 31 October: a live LLM agent proposing in the demo, and the shop's own history in the measurement. Everything is live at the link on this slide, and the code is public."
