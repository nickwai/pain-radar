# Source study — 2026-10-12

**Question:** after `advice_question` (5f91bef/1b51b82) the pool shrinks to ~1-3 real
problems a week, too few for weekly clustering. Where else do people who already pay
for software post recurring business pain, in a feed we can read?

**Method:** one request per candidate from the WSL machine (same as 10-04). Reachable
Discourse forums collected with the production `fetch_discourse` over 7 days, then
the production `triage_posts` (current prompt incl. `advice_question`, temperature 0)
on up to 20 newest posts per forum (all 90 for Shopify). Not checked from GitHub
Actions IPs.

## Access (70 candidates, 2 batches)

- **Reachable Discourse (19):** community.shopify.com (merchants), discuss.frappe.io
  (ERPNext), forum.manager.io, forum.lightburnsoftware.com, forum.uipath.com,
  community.quickfile.co.uk, community.glideapps.com, community.softr.io,
  community.suitecrm.com, forum.cs-cart.com, community.weweb.io,
  forum.invoiceninja.com, www.dolibarr.org/forum, community.activepieces.com,
  community.xibo.org.uk, forum.mautic.org, forum.plaintextaccounting.org,
  community.syncromsp.com, community.noloco.io (last two: 0 posts in 7 days).
- **Reachable RSS:** electriciantalk, plumbingzone, diynot (whole-site feeds; not
  sampled - trades trial runs until ~10-18), Smartsheet (10 items over 7 months),
  Budibase GitHub discussions (slow).
- **Blocked / no feed:** webhostingtalk, digitalpoint, daycare.com, insurance-forums,
  atxcommunity, fredmiranda, opencart, squarespace (403); hvac-talk, detailingworld
  (202 challenge); webflow, freeagent (Cloudflare challenge); airtable, monday,
  flutterflow, zapier, squareup, atera, chargebee, shipstation, akaunting,
  pressurewashingresource, mrlandlord, dentaltown, espocrm (404); biggerpockets
  (406); bigcommerce, printful, easypost, tacticalrmm, snipeit, kimai,
  sellercentralforums, tradesmanforum (connection error); odoo (timeout);
  pipedream, gohighlevel, halopsa, magento, zoho, clickup, eventespresso (HTML only).

## Yield

| Forum | Posts/day | Sample | real | Main other verdicts |
|---|---|---|---|---|
| **community.shopify.com** | **~25** (3 pages = 3.7 days) | 90 | **13** | 38 self_promo, 19 help, 8 not_a_problem |
| discuss.frappe.io (ERPNext) | 5.8 | 20 | 3 | 9 help, 4 self_promo |
| forum.manager.io | 4.3 | 20 | 2 | 12 help, 5 bug report |
| community.glideapps.com | 1.1 | 5 | 2 | |
| forum.lightburnsoftware.com | 10.3 | 20 | 1 | 16 help |
| forum.uipath.com | 15.3 | 20 | 0 | 9 not_a_problem, 8 help |
| community.quickfile.co.uk | 2.3 | 16 | 0 | 15 help |
| the other 10 | <2 | 1-8 each | 0 | |

## Shopify merchants, read by hand

The 13 real posts are not 13 merchants:
- **3 are developers doing customer discovery** ("I'm a developer researching this
  workflow before building anything"): 3PL invoice reconciliation, personalised
  orders arriving without the engraving text (posted in English AND Spanish), a
  "biggest mobile design challenge" engagement post.
- **1 is an ad triage missed** (Shopify Collective "Payment Guard"; the pitch is in
  the middle of the post).
- The rest are genuine merchants: quantity discounts across variant cart lines, B2B
  compare-at prices, POS order-history permissions, POS authorisation-only payments,
  checkout "Request Forbidden" after migration, stock-report change, external
  product pages.

So realistic genuine yield ≈ **8-9 per 90 ≈ 2/day**, still more than every current
source together (~2/week). Two useful side effects: (1) the discovery posts point at
pains other builders already chase (= competition signal, and they cite the
underlying merchant threads); (2) the personalisation topic repeats, which is what
weekly clustering needs.

ERPNext: real posts are manufacturing/tax process gaps (job cards, scrap batches,
withholding categories). ERPNext is open source with an app marketplace, so a third
party CAN ship the fix. ~1 real/day.

## Recommendation

1. Add **community.shopify.com** (max_pages 3; NOT in always_channels - 25/day would
   take the whole round-robin cap of 10; let the keyword filter pick).
2. Add **discuss.frappe.io** as always_channel (quiet enough).
3. Triage: count customer-discovery posts ("researching before building", "no product
   to promote", surveys of merchants) as `self_promo` - the poster is a would-be seller,
   not someone stuck.
4. Skip the rest (help desks: UiPath, LightBurn, QuickFile, Manager.io = vendor
   feature requests on a closed product).
5. First CI run after adding: check the collect log for HTTP 403/409 on
   community.shopify.com (Cloudflare may block GitHub IPs like the XenForo forums;
   Discourse has no `fetch: local` path yet).
