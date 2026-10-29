# ID5 offerings: what we sell, and to whom

Source: the product overview table and the Identify (Mobile Apps, CTV), Enrich and Monetize one-pagers Satiesh shared on 2026-10-29. If a lead asks for something that isn't described here, **don't assume we sell it**. Say it's not in these docs and that a human needs to check.

## Who buys what

| Company type (as the lead describes itself) | Offerings to consider |
|---|---|
| Publisher, media owner, mobile app, CTV app/platform, audio | **Identify** (free), **Enrich**, **Monetize** |
| Enablement / enrichment partner acting for publishers | **Enrich** |
| SSP | **Sync**, **Expand** |
| DSP | **Optimize** |
| Data platform / data provider / CDP / DMP | **Augment** |
| Activation platform reading IDs in bid requests | **Activate** |
| Advertiser or agency | No direct offering in these docs. They benefit via their DSP or SSP (Optimize, Expand). Say so. |
| Software or services vendor pitching *to* ID5 | Not a buyer. |

## Sell-side (publishers and media owners)

**Identify:** universal, privacy-first ID for media owners. **Free for media owners**. In exchange, their signals feed the shared identity layer.
- Turns available signals (hashed emails, mobile ad IDs, IP, etc.) into a persistent ID5 ID that is shared, encrypted, in the bid stream. Authorized partners decrypt it.
- Web, mobile apps (iOS/Android SDKs, server-to-server API, via existing SSP and enablement partners) and CTV (server-to-server API, ad-server macro, via enablement partners).
- Mobile: addressability despite low ATT opt-in. CTV: an ID5 ID can be generated on 90%+ of CTV inventory, including impressions without a device IFA. Partners report 23%+ more biddable impressions when the ID is present.
- Enables buyer targeting, frequency capping and measurement across channels.
- Scale: 100k+ media partners, 80+ ad tech partners.

**Enrich:** "Don't let a single impression go to waste."
- An enrichment partner connects the publisher's ID5 IDs to other identifiers buyers use (cookies, MAIDs, UID2.0) and decorates bid requests with them, following IAB Tech Lab provenance standards.
- Outcomes: higher fill rates and CPMs, better match rates with demand and data partners, addressability in web, app, CTV and audio. The one-pager quotes partner-reported uplifts in cookie match rates, revenue per DAU and RPM. Don't quote the figures in a post, because the extracted text doesn't make clear which number goes with which metric.
- ID5 cookie-syncs with buyers on the publisher's behalf.

**Monetize:** "Monetize your audiences wherever they are."
- For publishers with first-party audiences. Create addressable audiences keyed to the ID5 ID, expand them across devices and households with the ID5 graph, and activate via SSP/DSP/ad server partners (curated deals, PMPs, audience extension).
- The publisher (or its CDP) decrypts ID5 IDs and ingests the ID5 Cross-Device Graph and Partner Graph.
- Guarded Publisher ID (GPID) works as a PPID in GAM or Microsoft Monetize, where universal IDs aren't supported.
- Graph scale: 1.5B+ individuals, 660M+ households, 100K+ media properties distributing the ID.

## Buy-side and platforms

**Augment** (data platforms): decrypt ID5 IDs and build/activate audiences on them. Look up the ID5 Device Graph (alternate ID5 IDs, device IDs) to extend audiences across channels, and the Partner Graph to push audiences to activation partners. Deploy the ID5 API on suppliers' properties and cookie-sync with ID5.

**Activate** (activation platforms): decrypt ID5 IDs in incoming bid requests.

**Expand** (SSPs): decrypt publishers' ID5 IDs, match them to agency/advertiser segments, and use the Cross-Device Graph to expand segments across channels.

**Sync** (SSPs): decrypt publishers' ID5 IDs and use the Cross-Device and Partner Graphs to enrich bid requests. Cookie-sync with ID5.

**Optimize** (DSPs): decrypt ID5 IDs in bid requests to match segments. Deploy the ID5 SDK on advertiser properties. Use the combined Device and Partner Graph (their own ID only) to expand segments and optimize across channels.

## Products underneath (for reading technical asks)

ID5 ID · Decryption keys · Signal onboarding (custom graph) · Device / Cross-Device Graph · Partner Graph · Cookie sync.

## Positioning

Neutral and identity-focused, with no conflicting business lines. Privacy-by-design: encrypted, permissioned IDs that reflect user consent. Publishers' data isn't handed to the buy side.
