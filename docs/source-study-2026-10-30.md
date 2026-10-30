# Source study — 2026-10-30

**Question:** after cutting 11 zero-yield sources (9789eda), toys, fashion and
automotive had little or no coverage. Are there readable sources for those
industries, or for sports and pets, where owners post business pain?

**Method:** one request per candidate from the WSL machine, then a read of the
newest thread titles. No triage run. Not checked from GitHub Actions IPs.

## Results (53 candidates)

**Added as trials (1c703ea), judged at the next 2-week review:**

| Source | Group | What is there | 7-day fetch |
|---|---|---|---|
| groups.io/g/twsapi (RSS) | trading | traders automating Interactive Brokers (gateway auto-restart, tick data) | 7 |
| forum.intervals.icu (Discourse) | sports | cyclists, coaches, devs on its API | 68 |

**Reachable but fan/hobby talk, not business pain:** niketalk (release news, legit
checks), pokebeach (set news), elitefourum (chat, WTB), hobbytalk (builds, hauls),
gunjap.net (news blog), usethinkscript (indicator sharing), petforums.co.uk,
dogforums, germanshepherds (owner chat), reef2reef (tank photos, shop ads), zwift
(app complaints only Zwift can fix), slowtwitch, tennisforum. chickensmoothie and
community.gingrapp.com answered but returned no usable topics.

**Blocked / no feed:** amibroker, babypips, automotiveforums, thefashionspot,
superfuture, figurerealm, golfwrx, language-learners (403/405); freedomcardboard,
autoshopowner, japan-guide, pushpress, garmin (404); blowoutforums, resellerforum
(HTML only); collectors.com (503); thepokemoncenter (parked); kanjikoohii, brickset,
thesellercommunity, whatnot, sierrachart, tradingview, vintedforum, autopia,
koreanclass101, moego, dogtrainingforum, reefcentral, trainingpeaks, teamsnap,
soccercoachingforum, tennis-warehouse, bikeradar, thegolfshopforum (no response).

## Takeaways

1. Fan forums are open; the owner/seller side (resellers, card shops, pet
   businesses, sports clubs) is blocked or has no forum. Same result as 10-04 and
   10-12. About 30 fan forums tested across three studies, none showed business pain.
2. **Stop hunting fan forums.** Cut the remaining ones in config on the same
   evidence (real/shortlisted over the 10-08, 10-22, 10-30 reviews): styleforum
   1/7, watchuseek 0/6, hardwarezone 0/11, chinese-forums 0/2, purseblog 403.
   garagejournal stays (3/6 on 10-30).
3. Sports and pets: user decided not to add them to `user_industries`.
4. Toys and fashion now have no source; Shopify merchants (toy, card, fashion
   stores) still reach the pool through community.shopify.com.
