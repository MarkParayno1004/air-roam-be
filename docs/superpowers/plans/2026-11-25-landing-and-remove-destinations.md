# Landing page + remove Destinations Implementation Plan


**Goal:** Remove the store's Destinations pages; the landing page sells and lists every available country, each opening Products with that country chosen. New header.

**Spec (user):** "in the frontend remove all of modules under destinations the component the details page and list of countries in destination instead replace it with list of countries that is already available from the backend and when clicked it will route to products details. destination is redundant and enhance the landing page enhance the header remove the search make something that can persuade customers or encourage them to buy and replace the favicon ..." (favicon.svg/png already done by the controller: `apps/store/public`, links in `root.tsx`.)

> **Changed while building (user):** "only show here the popular under Where are you headed?" The list shows popular countries only, with a "See all N countries" link to `/products`; hidden when none are tagged.

> **Added (user):** highlights and selection use `#fdb62b` (token `accent`). Hero offer is the cheapest SIM/eSIM plan among popular countries; `?type=` and `&plan=` preselect on Products.

## Global Constraints

- Never commit, stage, stash, push or switch branch. Work only in `/Users/markphilipparayno/personal/air-roam/air-roam-fe` (Task 1-2: `apps/store`, `e2e`, `README.md`). `apps/admin` and `apps/store/package.json` hold other uncommitted edits: don't touch.
- `apps/store/app/seo/prerender.ts` and `prerender.test.ts` hold the user's uncommitted edits that exist only for destination pages; removing those pages makes them obsolete, so they may be rewritten here (the controller saved a copy).
- The backend stays as is: `GET /destinations` is the data source (countries with prices), API types keep the name `Destination`.
- No new dependencies, no raw hex in components, inline SVG icons via `components/icons.tsx`, no emoji. Accessible: labels, keyboard, visible focus, 44px targets, contrast 4.5:1, reduced motion. No horizontal scroll at 320px.
- **Honest persuasion only:** claims must come from live data or facts already true in the product. No invented reviews, ratings, customer counts, discounts, countdowns, coverage, speeds, refund guarantees or "cheapest" claims. True facts: prices in PHP, pay with Xendit (cards, GCash, Maya), eSIM installs before you fly, SIM is delivered in the Philippines, Pocket WiFi shared by up to 5 devices, Pocket WiFi delivery ₱200 for 7 days or fewer and free above, eSIM/SIM days start on activation, rental dates are final once ordered, an account is required only to check out.
- Smallest complete change in the surrounding style.

### Task 1: Remove Destinations, Products opens with a country

- Delete routes `destinations` and `destinations/:slug` (`routes.ts`, `routes/destinations.tsx`, `routes/destination.tsx`) and `catalog/{DestinationView,DestinationCard,DestinationGrid,PopularDestinations}.tsx`, `seo/jsonld.ts`, `destinationTitle`, `fetchDestinationPage`, plus their tests. `searchDestinations` moves to `CountryCombobox.tsx`.
- `/products?country=<slug>` (e.g. `japan`) opens with that country chosen. The URL is the single source of the choice: choosing in the combobox or a chip writes `?country=` (replace history), clearing removes it; unknown slug = nothing chosen. The page is pre-rendered without a query, so read the param only after mount (`useMounted`) to avoid a hydration mismatch. The combobox text must show the country when it arrives from the URL, including when the URL changes while mounted.
- New `catalog/CountryList.tsx` on the home page (replaces Popular + search): every country from the API, popular ones first (with a "Popular" Pill), then alphabetical; each card is a link to `/products?country=<slug>` with country code, name and "From ₱350". Section id `countries`, heading "Where are you headed?". Works in the pre-rendered HTML. Empty → "No countries available right now." Remove the hero search form.
- `prerender.ts`: paths = `STATIC_PATHS` without `/destinations`; keep the strict URL check and the API reachability check exactly as today (strict throws, local warns); drop slugs and the dev placeholder. Tests follow.
- Update `sitemap.test.ts`, `e2e/store-checkout.spec.ts` (goto `/products?country=japan`; the country-page heading assertion goes), README line about destinations, and every remaining link/text ("View all destinations", breadcrumbs). No dead code left (`grep -ri "/destinations"` in apps/store/app shows only the API path).
- Tests: URL param preselects and adds with `country_code`; unknown slug; choosing updates URL; clearing; URL change while mounted; CountryList order, link, Pill, empty; first render (renderToString) has nothing chosen.

### Task 2: Landing page and header

Section order (ui-ux-pro-max: conversion + trust, pricing transparency, FAQ, CTA in nav, sections and end):
1. **Header** (sticky): Logo = the new mark (`/favicon.svg` as `<img alt="">`, 40px) + "Air Roam"; nav "One country" `/products`, "Multiple countries" `/products/multi-country`, "Help" `/contact` (active states exact; `/products` must not look active on multi-country); actions: cart as an icon with count badge and accessible name "Cart (2)", "Log in" / "My account" as text, primary button "Get connected" → `/products`. Sign up stays reachable (login page has the link; also in the mobile menu). Mobile: logo, cart icon, 44px menu button; menu closes on navigation and Escape, has aria-expanded/aria-controls, shows the nav, Log in, Sign up and the CTA.
2. **Hero** (primary background, on-primary text; the strongest moment of the page): small eyebrow with live count ("11 countries · prices in PHP"); H1 "Land online. Skip the roaming surprise."; one supporting sentence on eSIM, SIM and Pocket WiFi; two CTAs: "Choose your country" (→ `#countries`, solid on light) and "Going to several countries?" (→ `/products/multi-country`, outline); a three-fact line (Pay with cards, GCash or Maya · Set up before you fly · No account needed to browse). Right side: a travel-ticket visual (reuse the TripTicket look, decorative route line + plane) showing a REAL offer from live data: the lowest-priced SIM/eSIM plan of the first popular country (else first country): country, plan label, price, "₱71/day", and a button "Get this plan" → `/products?country=<slug>`. No offer → the ticket is left out.
3. **CountryList** (Task 1), polished as compact cards; 2/3/4 columns; if more than 12, show 12 and a "Show all N countries" button (popular first; all links stay in the pre-rendered HTML).
4. **Which one is right for you?** three cards (Pocket WiFi / eSIM / SIM): best for, 3 facts, live "from ₱X" (lowest across countries), CTA to `/products`.
5. **How it works** (3 steps, existing copy improved, matching the true flow).
6. **Questions** (`<details>` FAQ, 5 items built only from the true facts above).
7. **Final CTA band** "Your flight is booked. Is your data?" with button "Choose your country".
- Footer: new logo, links updated (One country, Multiple countries).
- `/` meta title/description updated to the same pitch.
- Remove anything unused after this. Tests: header active state, cart badge name, mobile menu Escape; hero offer picks the lowest plan of the first popular country and hides without plans; "from" prices; show-all button; FAQ present.
- Visual check in Chrome (playwright `channel: "chrome"`, dev server http://localhost:5175 read-only) at 320, 375, 768, 1280: refine until it looks finished; save `landing-*.png` to the scratchpad.
