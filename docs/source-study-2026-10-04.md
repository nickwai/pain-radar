# Source study — 2026-10-04 (input for the 10-08 review)

**Question:** where do people who already pay for software complain? Background: 0 of
the 4 ideas reported so far survived a competitor check, and 3 of their 4 source posts
were written by sellers (see README, "2026-10-04 — an ad became the top idea").

**Method:** one gentle request per candidate from the WSL machine (GitHub Actions IPs
may differ), then the real triage prompt (`triage_posts`, temperature 0, current
`user_industries`) on a random sample. `out_of_industry` means "a real problem, but
outside your industries" — read it as real pain you have chosen not to see.

## Results

| Source | Access | Sample | real | out_of_industry | Verdict |
|---|---|---|---|---|---|
| **lawnsite Business Operations** (`/forums/business-operations.20/index.rss?order=post_date`) | RSS ✅, median body 460 chars | 15 | 0 | **14** | Best pain found: invoicing software bugs, route drive time, crew time clocks, unprofitable recurring customers, CRM wishlist. Only ~0.5 posts/day. Blocked by industries list. |
| **contractortalk Business** (`/forums/business.16/index.rss?order=post_date`) | RSS ✅, 535 chars | 15 | 0 | 7 | Real pain (unanswered estimates, change orders, sub licence/COI tracking) plus 5 self_promo — software vendors hunt these owners, itself a money signal. ~0.15 posts/day. |
| contractortalk / lawnsite / salongeek, whole site | RSS ✅ | 8 each | 0 | 6–7 | Mostly equipment and craft talk; use business sub-forums instead. |
| truckersreport | RSS ✅ | 8 | 0 | 2 | Chat and news. Skip. |
| Spiceworks (Discourse) | JSON ✅ | 8 | 0 | 1 | IT help questions and chat. Skip. |
| Apple App Store reviews, ≤3 stars (Poshmark, Depop, Vinted, Whatnot, Mercari, eBay, Shopify, TradingView, Square) | JSON ✅, 22–146 low-star/app, median 210 chars | 36 | 6 | 17 | Complaints are about the platform itself (bans, support, fees, scams) — only the vendor can fix. Few solo-buildable gaps (eBay bulk photo listing for card sellers). Skip as idea source; maybe useful as competitor evidence later. |
| Shopify App Store reviews, 1–2 stars (Klaviyo, Judge.me, Printful, ShipStation, Privy) | HTML ✅, 10/page | 20 | 0 | 11 | Same: vendor quality/support. "Removed X, too expensive" = switching signal, but the fix is a rival SaaS, not solo. Skip. |
| WordPress.org plugin reviews (WooCommerce, Stripe, MailPoet) | RSS ✅ | 16 | 0 | 0 | Mostly 5-star thanks; 1-star are plugin bugs. Skip. |
| Capterra, G2, Trustpilot, AccountingWEB | 403 ❌ | | | | Blocked. |
| UK Business Forums | JS challenge ❌ | | | | Blocked. |
| landlordzone, propertytribes, indiehackers feeds | 404 ❌ | | | | No feed found. |

## Takeaways

1. **Review sites are reachable but the wrong shape.** People reviewing an app complain
   about that app; the fix belongs to the vendor. Not idea material.
2. **Real paid-business pain lives in trade business sub-forums** — and every one of
   those posts is cut today by `user_industries` (tech, trading, toys, fashion,
   automotive, Asian culture).
3. **Decision for 10-08:** keep the industries list (and accept empty days), or add
   something like "trades and field-service business operations (lawn care,
   contractors)" and add the two business sub-forums above as `always_channels`.
   Caveat: field-service software is a crowded market (Jobber, Housecall Pro, LMN,
   Service Autopilot) — ideas there must be narrow gaps, and the competitor check
   matters even more.
