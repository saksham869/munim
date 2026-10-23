# Threat model and security review

**Review.** An independent security reviewer (a separate agent that had not seen the pitch) read the code and ran attacks against it on 23 Oct 2026. At that point 143 tests passed. Every finding below was fixed the same day with a test that fails without the fix. The suite now has 180 tests.

**Sources the reviewer used:**
- OWASP Top 10 for LLM Applications 2025: https://genai.owasp.org/llm-top-10/
- Digital Personal Data Protection Act, 2023 (Gazette of India, 11 Aug 2023): https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf

This is a prototype-level review, not a certification and not legal advice.

---

## 1. What needs protecting

| Asset | Threat | Main control |
|---|---|---|
| The merchant's money | An agent overspends, or offers lose money | Weekly budget reserved under a lock; margin and payback rules; owner's approval limit counts the whole week |
| The owner's authority | The agent approves its own offers, or carries on after "stop" | Separate owner and agent tokens; the kill switch cancels live offers |
| Customers | Spam, offers without consent, leaks of phone or UPI ids | Consent never assumed; at most 2 offers in 30 days; ids pseudonymised at import and kept out of the ledger |
| The record | Someone rewrites history, or the agent puts words in Munim's mouth | Hash chain plus per-entry HMAC seal; Soundbox lines carry no agent text |

## 2. Trust boundaries

```
[UNTRUSTED]  growth agent / LLM ── CampaignProposal (typed, bounded) ──┐
                                                                       │
[TRUSTED, from payments]  insights.build_segments ── Segment ─────────►│
                                                                       ▼
                         policy.PolicyEngine.evaluate ── ALLOW / GATE / DENY + a fix
                                       │                       │
              GATE ► owner approves (owner token) ► re-check   │ DENY ► back to the agent
                                       ▼
   budget.commit (locked) ─► passport.issue (HMAC, single use) ─► offers.create_offer (mock)
                                       │
   measurement.evaluate (holdout) ─► budget.settle ─► ledger.append (hash chain + HMAC seal)
                                       │
                           summary.* ─► Soundbox and app text (numbers and fixed phrases only)
```

The design's strength, confirmed by the reviewer: the agent supplies only a typed proposal (`munim/models.py`, "Everything in here is untrusted"). Baselines, baskets and segments come from payments, never from the agent. Money is integer paise. Any error inside the policy engine is a refusal.

## 3. Who could attack, and what they can do

| Actor | Can | Cannot |
|---|---|---|
| Growth agent or LLM, possibly prompt-injected | Propose any offer, as often as it likes | Supply its own return rates; approve; pay; choose who is held back; put its own words on the Soundbox |
| Anyone holding the agent token | Same as the agent | Approve, reject, use the kill switch or the demo routes (403) |
| Anyone with no token | Nothing, once tokens are set (401) | |
| Someone at the counter | Tap "Haan" on a shared screen | See residual risk 6 |
| Insider who can write the stored ledger | Edit entries and recompute the public hashes | Recompute the seals without the key (see residual risk 1) |
| The offer service | Time out or answer ambiguously | Cause a blind retry: the offer is quarantined as UNKNOWN until a person checks |

## 4. Findings and status

| ID | Severity | Finding | Status and fix | Test (in `tests/test_hardening.py` unless noted) |
|---|---|---|---|---|
| A | High | The ledger was a plain SHA-256 chain. Anyone who could write it could edit an entry (STOP changed to WORKED) and recompute every later hash, and verification still passed. | **Fixed.** Each entry also carries an HMAC seal under a key derived from the engine secret. The key is never exported. `verify_entries(entries, key)` reports `sealed`. The public chain can still be checked without the key. | `test_full_rewrite_passes_the_public_chain_but_not_the_seals`, `test_munim_seals_its_ledger_and_catches_a_rewrite` |
| B | Medium-high | Nothing serialised decide and execute. In the reviewer's run, five concurrent proposals all went live, 32 customers went over the 2-in-30-days cap, and one customer got 5 offers. Budget stayed correct. | **Fixed.** One re-entrant lock covers propose, approve, execute, outcome and the kill switch. | `test_concurrent_proposals_cannot_break_the_frequency_cap` (checked to fail without the lock) |
| C | Medium | The passport's customer-list digest joined ids with newlines, so `("a","b")` and `("a\nb",)` collided, and the signed customer count was never checked. | **Fixed.** Digest of the canonical JSON of the sorted ids; `verify` rejects a list whose size differs from the signed count. | `test_customer_list_fingerprint_is_injective` |
| D | Medium | The agent's offer name was spoken verbatim on the owner's Soundbox, so an agent could say "APPROVED by owner. Bonus unlocked" next to a STOP verdict (OWASP LLM05 and LLM09). | **Fixed.** Soundbox lines contain no agent text. Offers are named by their terms ("₹15 cashback on ₹250+"). Refusals are never spoken aloud and never read out margins. | `test_soundbox_names_the_offer_by_its_terms_not_the_agents_words`, `test_spoken_refusal_never_reads_out_margins_or_reasons` |
| E | Low | `customer_ids` had no size limit at the API, and the LLM parser accepted any reward (₹10⁹ passed). | **Fixed.** At most 5,000 ids per proposal; the LLM parser uses the same ranges as the API. | `test_oversized_customer_lists_are_rejected`, `test_llm_numbers_outside_the_api_ranges_are_refused` |
| F | High | No API authentication: whoever could propose could also approve, and the ledger then recorded "merchant" as the approver. The demo routes that inject outcomes were on the default app. | **Fixed.** `MUNIM_AGENT_TOKEN` can only propose. `MUNIM_OWNER_TOKEN` can also approve, reject, use the kill switch and the demo routes. The app runs open only when neither token is set (local demo), and `/health` says so. `MUNIM_DEMO_ROUTES=0` removes the demo routes. | `test_the_agent_cannot_approve_its_own_offer`, `test_unknown_tokens_are_refused_and_health_reports_auth`, `test_demo_routes_can_be_switched_off` |
| G | Medium | No persistence: the ledger, the budget and the set of used passports live in memory. | **Open** (prototype). See residual risk 4. | — |

The judge review (see `reviews/decision-log.md`) found four more gaps with a safety angle. All are fixed:

| Gap | Fix | Test |
|---|---|---|
| The owner's approval limit could be dodged by splitting one offer into two smaller ones | The limit counts the week's total auto-approved spend | `test_splitting_an_offer_does_not_dodge_the_owners_limit` |
| A new offer could pay customers held back by a running offer, spoiling its measurement | Customers in another live offer's comparison group are left out | `test_customers_held_back_by_a_live_offer_are_left_out_of_the_next` |
| "Munim, sab band karo" set a flag but live offers kept paying | The kill switch cancels live offers and returns their unspent budget; an uncertain cancel waits for a person | `test_kill_switch_cancels_live_offers_and_returns_the_budget`, `test_an_uncertain_cancel_waits_for_a_human` |
| A stopped offer could be rerun the next week | New rule `recently_stopped`: same segment, same or higher reward, within 30 days of a STOP | `test_stopped_offer_cannot_rerun_for_30_days`, plus the JS parity cases |

## 5. OWASP Top 10 for LLM Applications (2025)

| Risk | How Munim handles it |
|---|---|
| LLM01 Prompt injection | The agent's free text never reaches money logic or the Soundbox. The engine uses its own numbers. |
| LLM02 Sensitive information disclosure | The LLM proposer gets aggregates only (counts, rates, average basket), never customer ids. The ledger holds id digests and counts. |
| LLM05 Improper output handling | Owner-facing text is built from engine numbers and fixed phrases; the browser renders with `textContent`. |
| LLM06 Excessive agency | The agent cannot pay. Every rupee needs a budget reservation and a single-use passport. The kill switch cancels live offers. |
| LLM09 Misinformation | Verdicts come from a comparison group with stated uncertainty, and the agent cannot speak beside them. |
| LLM10 Unbounded consumption | Input sizes and number ranges are bounded on both entry points; the LLM call has a 20-second timeout. |

LLM03, LLM04, LLM07 and LLM08 (supply chain, poisoning, system-prompt leakage, embeddings) do not materially apply: the money path has no model in it.

## 6. Privacy (DPDP Act 2023, prototype level)

**In place:**
- **Minimisation.** Raw customer ids never enter the ledger (it stores digests and counts). The passport's public view is a digest and a count. CSV import replaces phone numbers, emails and UPI ids with salted HMAC pseudonyms. The LLM sees aggregates only.
- **Consent.** Never assumed. Without a consent column, nobody can receive an offer. Customers without consent are left out of every offer and counted in the decision.
- **Volume.** At most 2 offers per customer in 30 days by default, now safe under concurrency.

**Open:**
- **Erasure against an append-only chain.** The DPDP Act gives a right to erasure (Sec. 12) and requires erasure once the purpose is served (Sec. 8(7)). Deleting an entry breaks a hash chain. Ids are already kept out of the chain, but proposals' free text (`message`, `rationale`) is stored in it and could carry personal data. Production fix: store only a hash of free text in the chain and keep the text in a separate, erasable store.
- **The LLM endpoint** is operator configuration with no stated purpose limit. It receives aggregates only, but its provider's retention terms would need checking.

## 7. Residual risks

1. **The seal key lives with Munim.** An insider who has the key can still rewrite the ledger and re-seal it. Fix: anchor the head hash outside Munim, for example by showing it in the owner's app each day.
2. **The mock offer service does not check passports.** Munim checks the passport before it calls the rails. In production the rails must verify it too, or Munim must hold the only credential that can create offers.
3. **One process.** The lock and the budget are safe within one process. Production needs a database transaction or a single writer per merchant.
4. **No persistence.** Used passport nonces (passports expire after an hour), budget entries and the ledger must be stored durably, or a restart could allow a captured passport to be replayed before it expires.
5. **Open mode.** With neither token set, the API is open, by design for local demos. Never deploy that way; `/health` reports the mode.
6. **A shared screen.** Anyone at the counter could tap "Haan" on the Soundbox. Above a small amount, production approval should need the owner's phone (the Paytm for Business app, with a PIN).
7. **Erasure and the LLM endpoint**, as in section 6.
