/*
 * Munim's spending rules, for the browser demo.
 *
 * A line-for-line mirror of munim/economics.py, munim/money.py and
 * munim/policy.py (plus ReferenceAgent.replan from munim/agent.py).
 * Money is integer paise and rates are integer basis points; all arithmetic
 * runs on BigInt so every result matches Python's integers exactly.
 * tests/test_parity.py runs Python and this file on the same cases and fails
 * if any decision, reason, message, constraint or number differs.
 *
 * Differences from the Python engine, all structural:
 *   - Customers are anonymous flags ({consented, capped} or {consented, offers_30d})
 *     taken from the segment, so the merchant, segment, duplicate and
 *     outside-segment checks cannot fail here and are not repeated.
 *   - Only the sizes of the treated and comparison groups are computed. The
 *     real engine also picks who goes where, with a keyed hash the agent
 *     cannot predict; the sizes are identical.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.MunimRules = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var ALLOW = "ALLOW", GATE = "GATE", DENY = "DENY", NOTE = "NOTE";
  var BPS = 10000n;

  function big(x) { return BigInt(x); }
  function num(x) { return Number(x); }

  // Python's a // b on integers (rounds toward minus infinity).
  function floorDiv(a, b) {
    var q = a / b;
    if (a % b !== 0n && (a < 0n) !== (b < 0n)) q -= 1n;
    return q;
  }
  function ceilDiv(a, b) { return -floorDiv(-a, b); }

  // ------------------------------------------------------------ economics.py

  function rewardCeilingPaise(minBill, grossBps, keepBps) {
    var headroom = big(grossBps) - big(keepBps);
    if (headroom <= 0n || big(minBill) <= 0n) return 0;
    return num(floorDiv(big(minBill) * headroom, BPS));
  }

  function minBillForRewardPaise(reward, grossBps, keepBps) {
    var headroom = big(grossBps) - big(keepBps);
    if (headroom <= 0n) return null;
    return num(ceilDiv(big(reward) * BPS, headroom));
  }

  function marginPerBillPaise(bill, grossBps) {
    return num(floorDiv(big(bill) * big(grossBps), BPS));
  }

  function typicalMinBillPaise(avgBasket) {
    var target = floorDiv(big(avgBasket) * 85n, 100n);
    var rounded = floorDiv(target, 5000n) * 5000n;
    return num(rounded > 5000n ? rounded : 5000n);
  }

  function breakEvenLiftBps(baselineBps, basket, grossBps, reward) {
    var marginScaled = big(basket) * big(grossBps);
    var rewardScaled = big(reward) * BPS;
    if (marginScaled <= rewardScaled) return null;
    return num(ceilDiv(big(baselineBps) * rewardScaled, marginScaled - rewardScaled));
  }

  function maxRewardForLiftPaise(baselineBps, basket, grossBps, maxLiftBps) {
    var denom = (big(baselineBps) + big(maxLiftBps)) * BPS;
    if (denom <= 0n) return 0;
    return num(floorDiv(big(maxLiftBps) * big(basket) * big(grossBps), denom));
  }

  function splitCounts(nEligible, holdoutPct) {
    var holdout = holdoutPct > 0 ? num(ceilDiv(big(nEligible) * big(holdoutPct), 100n)) : 0;
    holdout = Math.min(holdout, nEligible);
    return [nEligible - holdout, holdout];
  }

  // ---------------------------------------------------------------- money.py

  function groupIndian(digits) {
    if (digits.length <= 3) return digits;
    var head = digits.slice(0, -3), tail = digits.slice(-3), parts = [];
    while (head.length > 2) {
      parts.unshift(head.slice(-2));
      head = head.slice(0, -2);
    }
    if (head) parts.unshift(head);
    return parts.concat([tail]).join(",");
  }

  function fmtInr(paise, opts) {
    var decimals = !!(opts && opts.decimals), floor = !!(opts && opts.floor);
    var p = big(paise);
    var sign = p < 0n ? "-" : "";
    if (p < 0n) p = -p;
    var rupees, rem = 0n;
    if (decimals) { rupees = p / 100n; rem = p % 100n; }
    else if (floor && !sign) { rupees = p / 100n; }
    else { rupees = (p + 50n) / 100n; }
    var out = sign + "₹" + groupIndian(rupees.toString());
    if (decimals) out += "." + (rem < 10n ? "0" : "") + rem.toString();
    return out;
  }

  function tenths(bps) {
    var b = big(bps);
    var sign = b < 0n ? "-" : "";
    if (b < 0n) b = -b;
    var t = (b + 5n) / 10n;
    return sign + (t / 10n).toString() + "." + (t % 10n).toString();
  }

  function fmtPct(bps) {
    var b = big(bps);
    if (b % 100n === 0n) return (b / 100n).toString() + "%";
    return tenths(bps) + "%";
  }

  function fmtPp(bps) { return tenths(bps) + " pp"; }

  // --------------------------------------------------------------- policy.py

  var INT_FIELDS = ["reward_paise", "min_bill_paise", "holdout_pct", "validity_days"];
  var HUMAN_CLEARABLE = ["approval_required", "kill_switch"];

  function inr(p) { return fmtInr(p); }
  function cap(p) { return fmtInr(p, { floor: true }); }  // limits are never shown above their true value
  var pct = fmtPct, pp = fmtPp;

  function isCapped(customer, offerCap) {
    if (typeof customer.offers_30d === "number") return customer.offers_30d >= offerCap;
    return !!customer.capped;
  }

  function problems(pol, p, seg) {
    var out = [];
    INT_FIELDS.forEach(function (name) {
      var v = p[name];
      if (typeof v !== "number" || !Number.isInteger(v)) out.push(name + " must be a whole number");
    });
    if (out.length) return out;
    if (!seg) out.push("its segment is not one Munim computed");
    if (p.reward_paise <= 0) out.push("the reward must be positive");
    if (p.min_bill_paise <= 0) out.push("the minimum bill must be positive");
    else if (p.reward_paise >= p.min_bill_paise) out.push("the reward must be smaller than the minimum bill");
    if (!(1 <= p.validity_days && p.validity_days <= pol.max_validity_days)) {
      out.push("validity must be 1 to " + pol.max_validity_days + " days");
    } else if (seg && p.validity_days !== seg.window_days) {
      out.push("validity must match the " + seg.window_days + "-day measurement window");
    }
    if (!(0 <= p.holdout_pct && p.holdout_pct <= pol.max_holdout_pct)) {
      out.push("the comparison group must be 0 to " + pol.max_holdout_pct + "%");
    }
    if (!p.customers || !p.customers.length) out.push("it targets no customers");
    return out;
  }

  function evaluateInner(pol, p, ctx) {
    var seg = ctx.segment;
    var reasons = [], constraints = {}, numbers = {};
    function deny(code, en, hi) { reasons.push({ code: code, effect: DENY, en: en, hi: hi }); }

    // 1. Shape. A malformed proposal gets no further.
    var probs = problems(pol, p, seg);
    if (probs.length) {
      var text = probs.join("; ");
      return {
        campaign_id: String(p.campaign_id), decision: DENY,
        reasons: [{ code: "invalid_proposal", effect: DENY, en: "Refused as malformed: " + text + ".",
                    hi: "Offer theek se nahi bana: " + text + "." }],
        constraints: {}, numbers: {}
      };
    }

    var keep = pol.keep_margin_bps;

    // 2. Margin floor on the smallest qualifying bill.
    var ceiling = rewardCeilingPaise(p.min_bill_paise, pol.gross_margin_bps, keep);
    numbers.reward_ceiling_paise = ceiling;
    if (p.reward_paise > ceiling) {
      var typicalBill = typicalMinBillPaise(seg.avg_basket_paise);
      var typicalReward = rewardCeilingPaise(typicalBill, pol.gross_margin_bps, keep);
      constraints.max_reward_paise = ceiling;
      constraints.suggested = { min_bill_paise: typicalBill, reward_paise: typicalReward };
      var need = minBillForRewardPaise(p.reward_paise, pol.gross_margin_bps, keep);
      if (need !== null) constraints.min_bill_for_requested_reward_paise = need;
      deny("margin_floor",
        inr(p.reward_paise) + " cashback on a " + inr(p.min_bill_paise) + " bill leaves less than the " +
        pct(keep) + " margin you keep on every bill. Most it can be: " + cap(ceiling) + ". " +
        "Suggested: " + cap(typicalReward) + " on bills of " + inr(typicalBill) + "+.",
        inr(p.min_bill_paise) + " ke bill par " + inr(p.reward_paise) + " cashback se har bill par " +
        pct(keep) + " munafa nahi bachega. Zyada se zyada " + cap(ceiling) + ". " +
        "Sujhaav: " + inr(typicalBill) + "+ ke bill par " + cap(typicalReward) + ".");
    }

    // 3. Every campaign keeps a comparison group, or nobody can tell if it worked.
    if (p.holdout_pct < pol.min_holdout_pct) {
      constraints.min_holdout_pct = pol.min_holdout_pct;
      deny("no_measurement",
        "Keeps " + p.holdout_pct + "% of customers as a comparison group; at least " + pol.min_holdout_pct + "% " +
        "is required, or nobody can tell whether the offer worked.",
        "Kam se kam " + pol.min_holdout_pct + "% grahak tulna ke liye rakhne zaroori hain, " +
        "warna pata hi nahi chalega offer kaam kiya ya nahi.");
    }

    // 4. Consent and frequency cap: customers are filtered out, not argued about.
    var offerCap = pol.max_offers_per_customer_30d;
    var consented = p.customers.filter(function (c) { return !!c.consented; });
    var eligible = consented.filter(function (c) { return !isCapped(c, offerCap); });
    var noConsent = p.customers.length - consented.length;
    var capped = consented.length - eligible.length;
    numbers.customers_proposed = p.customers.length;
    numbers.excluded_no_consent = noConsent;
    numbers.excluded_frequency_cap = capped;
    numbers.eligible = eligible.length;
    if (noConsent) {
      reasons.push({ code: "excluded_no_consent", effect: NOTE,
        en: noConsent + " customer(s) have not opted in to offers and were left out.",
        hi: noConsent + " grahakon ne offers ke liye haan nahi kaha, unhe chhod diya." });
    }
    if (capped) {
      reasons.push({ code: "excluded_frequency_cap", effect: NOTE,
        en: capped + " customer(s) already got " + offerCap + " offers in the last 30 days and were left out.",
        hi: capped + " grahakon ko 30 din mein pehle hi " + offerCap + " offer mil chuke, unhe chhod diya." });
    }

    // 5. Enough people to measure anything.
    if (eligible.length < pol.min_eligible_customers) {
      constraints.min_eligible_customers = pol.min_eligible_customers;
      deny("too_small_to_measure",
        "Only " + eligible.length + " eligible customers; at least " + pol.min_eligible_customers +
        " are needed to measure the result.",
        "Sirf " + eligible.length + " grahak bache; nateeja naapne ke liye kam se kam " +
        pol.min_eligible_customers + " chahiye.");
    }

    // 6. Split. A too-small comparison group is sized at the minimum so the numbers still help replanning.
    var holdoutUsed = Math.max(p.holdout_pct, pol.min_holdout_pct);
    var split = splitCounts(eligible.length, holdoutUsed);
    var treated = split[0], holdout = split[1];
    numbers.treated = treated;
    numbers.holdout = holdout;
    numbers.holdout_pct_used = holdoutUsed;

    // 7. Weekly budget, worst case: every treated customer redeems.
    var remaining = ctx.remaining_budget_paise;
    var maxSpend = p.reward_paise * treated;
    numbers.max_spend_paise = maxSpend;
    numbers.remaining_budget_paise = remaining;
    if (maxSpend > remaining) {
      constraints.max_treated_customers = Math.max(0, num(floorDiv(big(remaining), big(p.reward_paise))));
      if (treated > 0) constraints.max_reward_for_all_paise = Math.max(0, num(floorDiv(big(remaining), big(treated))));
      deny("over_budget",
        "Worst case this spends " + inr(maxSpend) + " (" + treated + " customers x " + inr(p.reward_paise) + "); " +
        "only " + cap(remaining) + " is left in this week's budget.",
        "Is offer mein " + inr(maxSpend) + " tak kharch ho sakta hai, par is hafte sirf " + cap(remaining) + " bacha hai.");
    }

    // 8. Payback, counting cashback paid to people who would have come anyway.
    var basket = Math.max(p.min_bill_paise, seg.avg_basket_paise);
    var baseline = seg.baseline_return_bps;
    var be = breakEvenLiftBps(baseline, basket, pol.gross_margin_bps, p.reward_paise);
    numbers.baseline_return_bps = baseline;
    numbers.basket_used_paise = basket;
    numbers.break_even_lift_bps = be;
    var rMax;
    if (be === null || be > num(BPS) - baseline) {
      // Loses money even if every single customer comes back.
      var billMargin = marginPerBillPaise(basket, pol.gross_margin_bps);
      rMax = maxRewardForLiftPaise(baseline, basket, pol.gross_margin_bps, pol.max_plausible_lift_bps);
      constraints.max_reward_for_payback_paise = rMax;
      deny("cannot_pay_back",
        "Even if every one of these customers came back, " + inr(p.reward_paise) + " cashback would cost more than " +
        "the extra margin it earns (" + inr(billMargin) + " on a typical " + inr(basket) + " bill, and " + pct(baseline) +
        " come back anyway). Largest reward that can pay back: " + cap(rMax) + ".",
        "Saare grahak laut aayein tab bhi " + inr(p.reward_paise) + " cashback ka kharch extra munafe se zyada hoga " +
        "(" + inr(basket) + " ke aam bill par " + inr(billMargin) + " munafa, aur " + pct(baseline) + " waise bhi aate hain). " +
        "Zyada se zyada " + cap(rMax) + " cashback.");
    } else if (be > pol.max_plausible_lift_bps) {
      rMax = maxRewardForLiftPaise(baseline, basket, pol.gross_margin_bps, pol.max_plausible_lift_bps);
      constraints.max_reward_for_payback_paise = rMax;
      deny("unrealistic_payback",
        pct(baseline) + " of these customers come back within " + seg.window_days + " days anyway, so most cashback " +
        "would go to people who'd buy regardless. Breaking even needs " + pp(be) + " more of them to return; " +
        "plan for at most " + pp(pol.max_plausible_lift_bps) + ". Largest reward that can pay back: " + cap(rMax) + ".",
        "Inme se " + pct(baseline) + " grahak " + seg.window_days + " din mein waise bhi aate hain; cashback zyadatar unhe " +
        "milega jo bina offer ke bhi kharidte. Fayde ke liye " + pp(be) + " aur grahak lautne chahiye, " +
        "ummeed " + pp(pol.max_plausible_lift_bps) + " tak hi. Zyada se zyada " + cap(rMax) + " cashback.");
    }

    // 9. Big spends wait for the merchant.
    if (maxSpend > pol.approval_threshold_paise) {
      reasons.push({ code: "approval_required", effect: GATE,
        en: "Worst-case spend " + inr(maxSpend) + " is above your " + inr(pol.approval_threshold_paise) + " " +
            "auto-approve limit, so it waits for your OK.",
        hi: "Is offer mein " + inr(maxSpend) + " tak kharch ho sakta hai, aapki " + inr(pol.approval_threshold_paise) + " " +
            "ki seema se zyada. Aapki manzoori chahiye." });
    }

    // 10. Kill switch: nothing spends without a human.
    if (ctx.kill_switch) {
      reasons.push({ code: "kill_switch", effect: GATE,
        en: "Autonomous spending is paused. Every campaign needs your approval.",
        hi: "Apne aap kharch band hai. Har offer ke liye aapki manzoori chahiye." });
    }

    var effects = reasons.map(function (r) { return r.effect; });
    var decision = effects.indexOf(DENY) >= 0 ? DENY : effects.indexOf(GATE) >= 0 ? GATE : ALLOW;
    if (decision === ALLOW) {
      reasons.push({ code: "within_rules", effect: NOTE,
        en: "Within your rules: worst case " + inr(maxSpend) + " of the " + cap(remaining) + " left this week, " +
            "and every bill keeps at least " + pct(keep) + " margin.",
        hi: "Aapke niyamon ke andar: zyada se zyada " + inr(maxSpend) + " kharch, har bill par kam se kam " +
            pct(keep) + " munafa." });
    }

    return { campaign_id: String(p.campaign_id), decision: decision, reasons: reasons,
             constraints: constraints, numbers: numbers };
  }

  /**
   * evaluate(policy, proposal, ctx) -> decision
   *   policy:   the MerchantPolicy fields (snake_case, as in scenario.json)
   *   proposal: {campaign_id, reward_paise, min_bill_paise, holdout_pct, validity_days, customers: [...]}
   *   ctx:      {segment: {window_days, baseline_return_bps, avg_basket_paise}, remaining_budget_paise, kill_switch}
   * Fails closed: anything unexpected is a DENY.
   */
  function evaluate(policy, proposal, ctx) {
    try {
      return evaluateInner(policy, proposal, ctx);
    } catch (exc) {
      return {
        campaign_id: String(proposal && proposal.campaign_id !== undefined ? proposal.campaign_id : "unknown"),
        decision: DENY,
        reasons: [{ code: "engine_error", effect: DENY,
          en: "Munim could not evaluate this proposal (" + ((exc && exc.name) || "Error") + "), so it is refused.",
          hi: "Munim is offer ko jaanch nahi paya, isliye ise roka gaya." }],
        constraints: {}, numbers: {}
      };
    }
  }

  // ---------------------------------------------------- agent.py (replan)

  var STEP_PAISE = 500;  // offers in clean Rs 5 steps

  /**
   * What the reference growth agent does after a DENY: take Munim's numbers and
   * try again. Returns {reward_paise, min_bill_paise, holdout_pct, customer_count}
   * or null when nothing worthwhile fits.
   */
  function replan(previous, decision) {
    if (!decision || decision.decision !== DENY) return null;
    var codes = decision.reasons.filter(function (r) { return r.effect === DENY; }).map(function (r) { return r.code; });
    var stop = ["invalid_proposal", "too_small_to_measure", "engine_error", "duplicate_campaign"];
    if (codes.some(function (c) { return stop.indexOf(c) >= 0; })) return null;
    var c = decision.constraints, n = decision.numbers;
    var reward = previous.reward_paise, minBill = previous.min_bill_paise, holdout = previous.holdout_pct;
    var count = previous.customer_count;

    if (c.suggested) {
      minBill = c.suggested.min_bill_paise;
      reward = Math.min(reward, c.suggested.reward_paise);
    } else if (c.max_reward_paise !== undefined) {
      reward = Math.min(reward, c.max_reward_paise);
    }
    if (c.max_reward_for_payback_paise !== undefined) reward = Math.min(reward, c.max_reward_for_payback_paise);
    reward = num(floorDiv(big(reward), big(STEP_PAISE))) * STEP_PAISE;
    if (reward < 1000) return null;  // below Rs 10 an offer is not worth sending
    if (c.min_holdout_pct !== undefined) holdout = Math.max(holdout, c.min_holdout_pct);

    var remaining = n.remaining_budget_paise, treated = n.treated;
    if (remaining !== undefined && remaining !== null && treated && reward * treated > remaining) {
      var keepTreated = num(floorDiv(big(remaining), big(reward)));
      count = Math.min(count, Math.max(1, num(floorDiv(big(count) * big(keepTreated), big(treated)))));
    }
    return { reward_paise: reward, min_bill_paise: minBill, holdout_pct: holdout, customer_count: count };
  }

  return {
    ALLOW: ALLOW, GATE: GATE, DENY: DENY, NOTE: NOTE,
    HUMAN_CLEARABLE: HUMAN_CLEARABLE,
    evaluate: evaluate,
    replan: replan,
    economics: {
      rewardCeilingPaise: rewardCeilingPaise,
      minBillForRewardPaise: minBillForRewardPaise,
      marginPerBillPaise: marginPerBillPaise,
      typicalMinBillPaise: typicalMinBillPaise,
      breakEvenLiftBps: breakEvenLiftBps,
      maxRewardForLiftPaise: maxRewardForLiftPaise,
      splitCounts: splitCounts
    },
    fmtInr: fmtInr,
    fmtPct: fmtPct,
    fmtPp: fmtPp
  };
});
