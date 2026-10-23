# Live demo script (offline round, 31 Oct)

About 3 minutes. Open https://saksham869.github.io/munim/ before you start. If the network fails, open `docs/index.html` from the repo: it works offline, because fonts and data are bundled. Last resort: `python3 scripts/demo.py` in a terminal prints the same story.

| Time | Show | Say |
|---|---|---|
| 0:00 | Hero slip with the red DENY stamp | "Paytm's Pi agents already suggest ad budgets to small businesses. When an agent can spend a shop's money, someone has to be the CFO. That's Munim." |
| 0:15 | Scroll to "One bill shows the problem" | "The agent's first idea: ₹40 cashback on any bill over ₹100. That bill earns the shop ₹12, so every redemption loses ₹28. A fifth of these customers would come back anyway, and with nobody held back, nobody can tell if it worked." |
| 0:40 | Replay, step 1 | "The owner sets three rules once, by voice: ₹500 a week, keep 6% on every bill, ask me above ₹300." |
| 0:50 | Step 3 | "Munim refuses with four reasons and the exact numbers that would pass. No model is in this path; it's arithmetic on paise." |
| 1:05 | Steps 4 and 5 | "The agent replans with Munim's numbers. ₹480 worst case is above the owner's limit, so the Soundbox asks. The owner taps Haan on the screen, not by voice, because anyone at the counter can speak; Munim re-checks, reserves ₹480 and signs a one-time passport. Only then does the offer go out." |
| 1:25 | Step 8 | "Day 14. On the shop's own numbers, this offer looks like a loser, because 5 of 9 held-back customers came back by chance. Munim uses a return rate pooled across shops and says: probably working, keep measuring. The simulation knows the truth: it really works." |
| 1:50 | Try it: hand the laptop to a judge | "You're the agent. Try to overspend." Click "The agent's greedy first try", then "Let the agent replan", then turn on "Pause all automatic spending". |
| 2:30 | Step 12, "Quietly edit entry 17" | "Every step is hash-chained. Change one verdict and verification fails right there." |
| 2:45 | Proof section | "Across 1,000 simulated campaigns: right keep-or-stop calls rise from 68% to 75%, and average profit per campaign from ₹10 to ₹16. Keeping every offer loses ₹18. The honest caveat: the pooled rate must be estimated well; 5 points too low erases the gain." |

## Questions to be ready for

See `pitch/judge-questions.md`.
