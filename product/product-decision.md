# Product decision

**Decision: build Munim, the spend authority and scorecard for a merchant's AI growth agent.** Frozen scope as of 23 Oct 2026.

| | |
|---|---|
| Target merchant | A kirana or small shop on Paytm devices with a few hundred repeat customers, thin margins (about 10 to 15% gross), and an owner who runs the counter and has no time for dashboards |
| User problem | A growth agent can now propose and spend on offers (S4). The owner can't check margin, deadweight or whether it worked, so a generous-looking offer can lose money on every redemption |
| Core workflow | Owner sets three rules by voice → agent proposes an offer → Munim allows, asks the owner, or refuses with the numbers that would pass → passport and offer → measured against a held-back group → kept or stopped, reported in Hinglish |
| Data needed | Payments (date, payer id, amount), consent per customer, offers already sent; the owner's gross margin |
| Supported actions | Cashback offers to a segment of the merchant's own customers |
| AI's job | The growth agent drafts offers and messages. Nothing the model says is used as a number |
| Deterministic rules | Margin floor, comparison group, consent and frequency caps, minimum size, weekly budget, payback after deadweight, approval limit, kill switch |
| Success metrics | Share of offers refused that would have lost money; profit per campaign compared with running every offer; right keep-or-stop calls; owner approvals per week (low is good) |
| Known limitations | Synthetic data and mock rails; pooled rates from simulated shops; in-memory state; no authentication on the API |
| Explicitly excluded | Pricing, stock, credit decisions, free-form chat over sales data, sending real messages or money |
