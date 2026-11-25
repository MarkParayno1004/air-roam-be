# Pocket WiFi plans + store redesign Implementation Plan

**Goal:** Staff create Pocket WiFi plans (name, price per day, GB per day) inside each region; the store's product pages get our own design instead of copying the reference images.

**Spec (user):** "can you revamp the design? ... not actual in the reference that I give. make our own design. Also the air roam pocket wifi speed is unlimited or regular. regular is 1 gb. so in the region admin put another component which pocket wifi plans and inside of that there is a row Plan (Unlimited/Regular) Price and GB. can be customizable". Answers: GB is **per day**; "There is a different price for each region again for Pocket Wifi so I need it to create a plan also regarding the product".

> **Changed after building:** the highest-price rule below was removed at the user's request. Every Pocket WiFi line pays its own plan's daily price.

## Global Constraints

- Never commit, push, stash, stage or switch branch. Never run `migrate` on the dev DB (the controller does). Don't touch servers on 8000/5174/5175.
- User's own uncommitted edits stay: BE `.env.example`, `README.md`, `docker-compose.yml`; FE `apps/store/app/seo/prerender.ts`, `prerender.test.ts`, `apps/store/package.json`.
- No new dependencies. Smallest complete change, surrounding style, design tokens never raw hex.
- Pocket WiFi: priced per day, GB per day (empty = unlimited), prices differ per region. Highest rate rule is kept but compares **like with like**: every WiFi line pays the highest daily price among WiFi lines with the same GB per day (`data_mb`; null = unlimited). Delivery fee unchanged (₱200 when total WiFi days ≤ 7, else free).
- A SIM/eSIM line can never use a WiFi plan and a WiFi line can never use a SIM/eSIM plan.
- Region names only in the Multi-Country Explorer and cart/checkout/orders of something bought there.
- Accessible: labels, keyboard, visible focus, 44px targets, 4.5:1 contrast, `prefers-reduced-motion`. No emoji as icons: inline SVG.

### Task 1: Backend (air-roam-be)

- `RegionPlan` gains `name` (CharField 50, blank, default ""), `for_wifi` (Boolean, default False); `validity_days` becomes nullable. Check constraint: for_wifi ⇔ validity_days is null. `Region.pocket_wifi_daily_rate` is removed. Update docstrings/comments that become false (also `OrderLine.region_plan` "null = Pocket WiFi").
- `label`: SIM unchanged ("5GB · 7 days"). WiFi: data is "Unlimited" or "1GB/day"; label is `"{name} · {data}"`, or just the name when name equals data case-insensitively ("Regular · 1GB/day", "Unlimited").
- Migrations: 0006 adds the fields, makes validity nullable and copies each region's rate (including soft-deleted regions) into a WiFi plan `name="Unlimited", data_mb=None, for_wifi=True, price=rate`; 0007 drops the rate and adds the constraint (separate files: Postgres can't alter a table with pending trigger events). Reversible: the reverse writes the region's lowest WiFi price back as the rate and deletes the WiFi plans. Test the copy like `catalog/tests`/`tests/test_region_migration.py` does.
- Staff API: region loses `pocket_wifi_daily_rate`. Plans at the existing endpoint gain `name`, `for_wifi`; `for_wifi` can't change after creation (400). WiFi: `name` required (error on `name`), `validity_days` must be empty → stored null. SIM/eSIM: `validity_days` required (error on `validity_days`), `name` stored "". Two live WiFi plans with the same name (case-insensitive) in one region → error on `name`.
- Public `destinations`: `pocket_wifi_daily_rate` replaced by `wifi_plans: [{id, name, label, data_mb, price}]` (active only, cheapest first, `[]` when no active Pocket WiFi product); `plans` is SIM/eSIM only; `from_price` covers both. Existing rules on hidden regions/plans/products hold.
- Checkout: WiFi line needs `country_code` and `region_plan_id` (missing plan → `plan_required`). `_current_price` returns None when `plan.for_wifi` doesn't match the product type. Highest rate per `data_mb` group among kept WiFi lines. Order line stores the plan; `variant_name_snapshot` e.g. "Japan Regular · 1GB/day".
- Update `seed_demo` (Unlimited at today's rate plus Regular 1GB at a lower price), `catalog/admin.py`, `conftest.py` factories, tests, `schema.yml`.
- New tests: label cases; validation cases; cross-use rejected both ways; Japan Regular ₱200 + US Unlimited ₱500 keep their own price; Japan Unlimited ₱350 + US Unlimited ₱500 both pay ₱500; region with only WiFi plans still listed; migration copy. Full `pytest -q` and `makemigrations --check`.

### Task 2: Admin (air-roam-fe/apps/admin)

- Region editor: remove the rate field and the sentence saying customers never see the name (they see it in the Multi-Country Explorer). Two cards: "SIM/eSIM plans" (as today) and "Pocket WiFi plans" with its own "Add Pocket WiFi plan" button and table Plan | Price per day | GB per day | Status | Edit/Delete. GB shows "Unlimited" when empty. WiFi form: "Plan" text field with suggestions Unlimited and Regular (native datalist) but any name allowed, "Price per day (PHP)", "GB per day" (empty = unlimited, same bad-number guard as PlanForm), Active. Choosing "Regular" prefills 1 GB only when the GB field is empty and untouched. Reuse `PlanForm`/`PlanTable` (a `wifi` prop) rather than copying them. Server errors next to fields. Opening one card's form must not hide the other card.
- Regions list: WiFi column shows "from ₱200/day" (active WiFi plans) or "—"; Plans counts SIM/eSIM plans.
- Payload: `{name, data_mb, price, is_active, for_wifi: true}` for WiFi (no validity); SIM/eSIM unchanged plus nothing. Tests.

### Task 3: Store (air-roam-fe/apps/store)

Data: `packages/api/src/schema.d.ts` is already regenerated. `CartLine.plan` is now set for every line; `daily_rate` goes. `cartTotals` uses the highest daily price per `data_mb` group; `toApiLine` sends `region_plan_id` and that rate for WiFi. `lineName` for WiFi: "Air Roam Pocket WiFi · Japan Regular · 1GB/day". Cart/checkout wording about the highest rate must stay true ("same data plan"). An old saved cart must not crash (reset as today). `jsonld`/`sitemap`/fixtures follow.

Design ("trip builder", our own; keep theme tokens and Inter; minimal, spacious, one accent):
1. **Band** (primary-soft, full width): H1 "Where are you going?", one-line sub; segmented control of two links "One country" `/products` and "Multiple countries" `/products/multi-country` (pill track, active = surface + primary text, `aria-current`); the destination field large (h-14) inside the band: `CountryCombobox` or the region `<select>`; on One country, quick chips of `is_popular` countries (none → nothing).
2. **Body**, two columns from `lg` (left steps, right sticky summary), single column below.
   - Step 1 "How do you want to connect?": one radio card per product with inline SVG icon (wifi / phone / sim), name, description, "from ₱X" (+ "/day" for WiFi); unavailable ones disabled with "Not available in {place}".
   - Step 2 "Choose a plan": radio tiles instead of dropdowns. SIM/eSIM: big GB ("Unlimited" when null), "7 days", price and "₱71/day". WiFi: plan name, "Unlimited data" or "1GB/day", "₱350/day", then Start/End dates as step 3 "When do you need it?".
   - Multiple countries: "One plan works in {n} countries" panel with country chips; no WiFi product.
   - Before a destination is chosen: steps are replaced by one calm empty state with three short product explainers (no dead controls, no "—" prices).
3. **Summary** styled as a travel ticket (the signature element): country code or region name big, dashed perforation, product, plan, dates, days, price lines (delivery fee hint for WiFi: "₱200 delivery for 7 days or fewer, free above"), total, full-width CTA ("Add to cart" / "Rent device") and the reason when disabled ("Choose your rental dates"). On phones a fixed bottom bar with total + CTA replaces the in-page CTA, with padding so nothing is covered.
4. Link card to the other mode ("Visiting more than one country?").
5. Country pages (`DestinationView`): same picker with the country fixed (keep breadcrumb, H1, good-to-know). `ProductCard`, unused `Chips` and their tests go.
- Motion: 150-200ms color/shadow only, reduced-motion respected.
- Tests: adapt; add WiFi plan choice (Regular ₱200/day added with its plan), changing destination resets plan, unavailable product fallback, disabled reasons, hydration guard, cart per-tier rate.
- Check visually in headless Chrome (playwright `channel: "chrome"`) at 375, 768, 1280 against a scratch server on another port with mocked API or the running API (GET only); no horizontal overflow, no console errors.
