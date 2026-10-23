# How Indian kirana and small merchants work today

Short evidence file from an independent research pass by a separate reviewer. All sources checked **23 Oct 2026**. The question: how small merchants record sales, track repeat customers, run discounts and talk to customers.

**How to read this file**
- Quoted text is exact, from pages I opened.
- Confidence: **High** = large survey or primary source. **Medium** = survey reported by press, or a company survey. **Low** = a single anecdote.
- The evidence base is thin. Credible, recent, kirana-specific surveys on repeat-customer tracking and discounting were **not found** in this pass. Gaps are marked.

---

## Evidence

| Workflow | Evidence (exact where quoted) | Source (opened) | Checked | Confidence |
|---|---|---|---|---|
| **Talking to customers: WhatsApp is near-universal** | PayNearby "MSME Digital Index 2024", which "draws from a comprehensive nationwide survey of over 10,000 MSMEs in the retail sector" (kirana stores, recharge outlets, medical shops, customer service points, travel agents; 32% women): "WhatsApp and WhatsApp Business dominated the messaging landscape, with an impressive usage rate of 97 per cent." The survey does **not** break down what WhatsApp is used for (orders, reminders, marketing). Article published 26 Jun 2024. | https://india.entrepreneur.com/news-and-trends/whatsapp-and-whatsapp-business-dominate-msme-landscape-with/476232 | 23 Oct 2026 | Medium (company survey reported by press; PayNearby's own retailer network may not represent all kiranas) |
| **Recording sales: low software adoption** | Same survey: 29% use accounting software, 17% point-of-sale software, 14% CRM software, 6% no software (manual methods). The article does not mention khata apps by name. | same | 23 Oct 2026 | Medium. Note: "6% no software" looks low next to the other figures. Read it as respondents in PayNearby's network, not all kiranas. |
| **Devices and barriers** | Smartphones are the main device for 70%; 68% use them for business (paraphrase of the article's figures). "the primary hurdles include a reluctance to embrace new technology, reported by 36 per cent"; 18% cite cost. | same | 23 Oct 2026 | Medium |
| **Recording credit (khata) and chasing dues** | A Delhi kirana owner logs daily sales in a paper journal and puts about 25 daily credit purchases on a loose sheet (paraphrase). He moved to an app khata (Chqbook): "Earlier I had to spend a lot of time to do the hisaab." The app sends automated SMS reminders with a UPI or wallet payment link: "I didn't send the reminder, the app did." He avoids pressing regulars for payment in case they switch stores: "These are all gali-mohalle ke log." The article also cites close to 60 million small business owners (paraphrase). Published 20 Oct 2020. | https://www.businesstoday.in/latest/trends/how-kirana-store-owners-are-getting-neighbourhood-buyers-to-pay-back-dues/story/419521.html | 23 Oct 2026 | Low (one anecdote, 2020) |
| **Payments and alerts** | Paytm: "Never miss a payment with instant voice alerts."; "Create payment links in seconds and collect payments securely through WhatsApp, SMS, or email." PhonePe: "Use the PhonePe QR to accept payments from all BHIM UPI apps."; SmartSpeaker alerts "in select regional languages." | https://play.google.com/store/apps/details?id=com.paytm.business&hl=en_IN ; https://apps.apple.com/in/app/id1463742453 | 23 Oct 2026 | High (what the products offer, not usage rates) |
| **Small merchants buying customer acquisition** | Paytm Pi targets businesses without a marketing team: "A salon, clinic, gym, boutique or local store."; "leads can come directly to your WhatsApp." | https://paytm.com/blog/artificial-intelligence/how-pi-sales-marketing-agent-works/ | 23 Oct 2026 | High (product description, not adoption data) |
| **AI agents moving onto WhatsApp** | Meta Business Agent in India (July, apparently 2026): answers "business-specific queries", recommends products, books appointments, qualifies leads (paraphrase); access through a waitlist. Early adopter Madhulika Enterprises reported a 25-30% rise in conversions (company-reported, paraphrase). | https://www.uniindia.com/whatsapp-unveils-meta-business-agent-for-businesses-in-india/business-economy/news/3902347.html | 23 Oct 2026 | Medium |
| **Tracking repeat customers (F&B example)** | Restaurant CRM: "Automatically capture and organize data from every visit and order"; "Run win-back campaigns to bring back lost customers"; "Trusted by 32000+ Restaurants." | https://www.reelo.io/ | 23 Oct 2026 | Medium (vendor claims; restaurants, not kiranas) |
| **Tracking repeat customers (online)** | Paytm Payment Analytics: "Track new, repeat & lost customers" (Payment Gateway merchants). | https://paytmpayments.com/payment-analytics | 23 Oct 2026 | High (product exists; usage unknown) |
| **Pressure on kiranas** | AICPDF estimate of about 2 lakh kirana closures in a year amid quick commerce (Oct 2024). From source register S8; **not re-opened in this pass.** | https://www.medianama.com/2024/10/223-quick-commerce-boom-closure-2-lakh-kirana-stores-products-distributors/ | Not re-checked in this pass | Medium (industry-body estimate, per register) |

---

## Gaps (not found in this pass)

1. No credible survey on **how kiranas identify or track repeat customers**: memory, the khata credit list, or payment data.
2. No credible survey on **how kiranas run discounts**: frequency, size, who funds them, whether brand schemes or the shop pays.
3. No breakdown of **what MSMEs use WhatsApp for**: orders, credit reminders, broadcasts.
4. No recent, large-sample figure on **khata-app adoption** among kiranas. Company user counts exist in press (e.g. Khatabook, OkCredit funding stories), but I did not open them. They are company claims, not surveys.

Leads seen in search results only, not opened:
- PayNearby MSME Digital Index coverage: https://yourstory.com/smbstory/indian-retail-msme-embrace-digital-technology-paynearby ; https://cxotoday.com/media-coverage/73-msmes-report-business-growth-via-digital-adoption-led-by-upi-and-smartphones-paynearby-survey/
- Meta India head on WhatsApp business messaging: https://www.outlookbusiness.com/news/business-messaging-whatsapp-engines-of-growth-biz-digitisation-driving-headroom-meta-india-head
- The IndiaRetailing page on the PayNearby index (https://www.indiaretailing.com/2024/09/18/msme-digital-index-2024-by-paynearby) loaded without its statistics.

---

## Implications for Munim (Inference, not verified)

- **Channel.** With 97% WhatsApp use among surveyed retail MSMEs, and with both Pi and Meta's agent sending customers to WhatsApp, customer-facing offers would go out on WhatsApp. The Soundbox suits the owner-facing loop (rules, approvals, reports), which matches the deck's split.
- **Data.** Software adoption is low (14% CRM, 29% accounting), so most kiranas do not have a customer database. The only systematic customer record is likely the payment stream, plus the credit khata for regulars. Munim's segments therefore depend on Paytm payment data being able to recognise returning payers. That is an assumption to confirm (see paytm-ecosystem.md, section 5).
- **Adoption.** 36% cite reluctance to adopt new technology. That supports zero-setup, voice-first defaults and argues against anything that needs the owner to configure campaigns.
- **Relationship sensitivity.** The 2020 anecdote shows owners avoid upsetting regulars. That supports Munim's frequency caps and consent checks. It also suggests holding back offers from some regulars, as a holdout requires, may need explaining to the owner. Inference only.
