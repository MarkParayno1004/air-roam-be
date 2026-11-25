# Products tabs (Single travel / Multi-Country Explorer) Implementation Plan


**Goal:** Split the store's Products page into two tabs, Single travel and Multi-Country Explorer, matching the user's two reference images, on existing catalog data.

**Architecture:** The backend adds the region to each destination and accepts a SIM/eSIM order line without a country (= the whole region). The store groups destinations by region; both tabs share one `PlanPicker`.

**Tech Stack:** Django 5.2 + DRF (air-roam-be); React 19, React Router 7, TanStack Query, Tailwind v4, Vitest (air-roam-fe).

**Spec:** the user's request (below). References: `/Users/markphilipparayno/Downloads/image (3).png` (Single travel) and `/Users/markphilipparayno/Downloads/image (4).png` (Multi-Country Explorer).

> "implement two tabs single travel and multi travel explorer ... The dropdown of countries if there is no inputted text it will be dropdown but when inputting it will show also the dropdown of the result of the country. Change Full speed into unlimited. Just change the UI and the plan now is to show the regions but it is under the multi country explorer use the current data from be and the region dropdown is the list of the regions and only available product under multi is esim and sim"

## Global Constraints

- **Never commit, push, stash, stage, or switch branch.** Both repos are on `feat/region-pricing` with uncommitted work.
- **User's own uncommitted edits: never revert or rewrite:** BE `.env.example`, `README.md`, `docker-compose.yml`; FE `apps/store/app/seo/prerender.ts` (may add one array entry, nothing else), `apps/store/app/seo/prerender.test.ts`, `apps/store/package.json`.
- Do not touch the user's servers (ports 8000, 5174, 5175) or database contents. No migrations, no new dependencies.
- No new admin features, no separate bundle data, no "Global 160+" row. SIM and eSIM share the region's plans and prices. Region names appear only in the Multi-Country Explorer and in the cart/checkout/order of something bought there.
- "Full speed" in the reference becomes "Unlimited" everywhere.
- Smallest complete change; follow the surrounding code style; design tokens, never raw hex; accessible (labels, keyboard, 44px targets).
- FE `npm run typecheck` leaves `tsconfig.tsbuildinfo`; delete it afterwards.

## Review Focus

- Two regions with the same name must stay two dropdown entries (group by region id).
- Changing country/region must not keep a plan id from the previous one.
- A region with a WiFi rate but no plans must not appear in the explorer; a country with no WiFi rate must not let Pocket WiFi be chosen.
- A choice made before hydration is lost: controls stay disabled until mounted (existing `fieldset disabled={!today}` pattern).
- A Pocket WiFi line without a country must be rejected; old clients sending `country_code` behave exactly as before.

---

### Task 1: Backend — region on destinations, whole-region plan lines

**Repo:** `/Users/markphilipparayno/personal/air-roam/air-roam-be`

**Files:** Modify `catalog/views.py`, `catalog/serializers.py`, `catalog/tests/test_public_api.py`, `orders/serializers.py`, `orders/checkout.py`, the existing checkout tests under `orders/tests/`, `schema.yml` (regenerate: see README for the spectacular command).

**Interfaces — Produces:**
- `GET /api/v1/destinations` items gain `"region": {"id": "<uuid>", "name": "<str>"}`.
- `POST /api/v1/orders` line: `country_code` becomes optional. Omitted on a SIM/eSIM line with `region_plan_id` = the whole region.

- [ ] **Step 1: Tests first.** In `test_public_api.py` change the shape test (rename to `test_destination_shape`): expected dict gains `"region": {"id": str(r.id), "name": "Secret Zone"}`; drop the leak assertion. In the checkout tests add:
  - `test_plan_without_country_covers_the_whole_region`: region name "Asia", countries ["JP","KR"], plan 5GB/7 days ₱399, eSIM; line without `country_code` → 201, order line `variant_name_snapshot == "Asia 5GB · 7 days"`, `countries_snapshot == ["JP","KR"]`, `unit_price == "399.00"`, no booking.
  - `test_wifi_without_country_is_rejected`: Pocket WiFi line with dates, no `country_code` → 400, error code `country_required`.
  - `test_whole_region_line_removed_when_region_inactive`: that line is not sold (same result as today's inactive-region line).
- [ ] **Step 2:** Run them, see them fail.
- [ ] **Step 3: Implement.** Nested serializer for `region` (named component in the schema); `build_destinations` puts the region in `priced`. `CheckoutLineSerializer.country_code`: `required=False, default=""`. In `checkout.py`: code from `l.get("country_code", "")`; WiFi with no code raises `DomainError("country_required", "Choose a country.")`; `_line_name` uses the plan's region name when there is no code; `_current_price` skips the country check when there is no code; `countries_snapshot` is `[code]`, or the region's countries when there is no code. Check `variant_name_snapshot`'s max_length fits region name (100) + label; if it does not, truncate nothing silently — report it.
- [ ] **Step 4:** Update the `Region` docstring ("Staff-only … Customers pick a country") so it is true, and regenerate `schema.yml`.
- [ ] **Step 5:** `.venv/bin/python -m pytest -q` all pass; `python manage.py makemigrations --check --dry-run` shows no changes.

### Task 2: Store — two tabs

**Repo:** `/Users/markphilipparayno/personal/air-roam/air-roam-fe`

**Files:**
- Regenerate `packages/api/src/schema.d.ts` (`npm run gen:api`).
- Create `apps/store/app/catalog/{CountryCombobox,PlanPicker,ProductTabs}.tsx`, `apps/store/app/routes/multi-country.tsx`, `apps/store/app/catalog/explorer.test.tsx`.
- Modify `apps/store/app/routes/products.tsx`, `apps/store/app/routes.ts` (`products/multi-country`), `apps/store/app/seo/prerender.ts` (add `"/products/multi-country"` after `"/products"`), `apps/store/app/catalog/ProductCard.tsx` (only to share rental logic), `apps/store/app/cart/{store.tsx,rental.ts,cart.test.tsx}`, `apps/store/app/checkout/usePlaceOrder.ts`, and fixtures that build a `Destination`.

**Interfaces — Consumes:** Task 1's `region` and optional `country_code`.

**Behaviour**
- `ProductTabs`: a nav with two links, "Single travel" (`/products`) and "🌐 Multi-Country Explorer" (`/products/multi-country`); the active one is underlined, primary, `aria-current="page"` (NavLink with `end`). Breadcrumb "Products > …" under it.
- **Single travel** (`/products`): label "Destination country" + `CountryCombobox` (placeholder "Type a country..."); heading "📍 {country or —}" with "One destination only. Each option below is priced and chosen separately."; `PlanPicker` with every product; then "Visiting other countries on this trip?" / "Switch to the Multi-Country Explorer — available for eSIM and SIM only." and a link row "🌐 Compare multi-country regional plans … View ›".
- **CountryCombobox** (WAI-ARIA combobox/listbox, no dependency): options are destinations passed in. Focus or click opens the list. No typed text → every country. Typed text → countries whose name contains it (case-insensitive) or whose code equals it; none → "No country found". ArrowUp/Down, Enter, Escape, mouse. While the text still equals the chosen country's name, the list shows every country. Leaving the field: empty text clears the choice, other text goes back to the chosen country's name (or empty).
- **Multi-Country Explorer**: heading "🌐 Multi-Country Explorer", "Available for eSIM and SIM only — pocket wifi is single-country only."; labelled `<select>` "Region / plan bundle" listing regions (grouped by `region.id`, only those with plans, sorted by name), first preselected; `PlanPicker` with non-WiFi products; a "{region} covers" panel with one chip per country. No regions → "No multi-country plans available right now."
- **PlanPicker**: soft panel with one labelled dropdown per product (in the order pocket_wifi, esim, sim): "{product name} speed" with the single option "Unlimited" for WiFi; "{product name} data plan" listing `plan.label` for eSIM/SIM, first plan preselected. Below "Tap a card to choose that option", one card per product as a radio option: emoji by type (📶 📱 💳, aria-hidden), product name, "{place} only, unlimited" / "{place} only, {plan label}" (Multi: "{region}, {plan label}"), price "₱350 /day" or "₱900 total" ("—" before a country is chosen), "Data only" Pill on eSIM, WiFi note "One country only — not available for multi-country trips", "✓ Selected" on the chosen one (primary border). A product with nothing to sell there is disabled: "Not available in {place}". First available product is preselected. Below: for WiFi, Start/End `DateField`s, days total, problem text, "Rent device"; for eSIM/SIM "Add to cart". Same rules, texts and line shape as today's `ProductCard`; share the rental logic instead of copying it. Controls disabled until mounted.
- Grid: 1 column on phones, 3 columns (2 in Multi) from `md`.
- **Cart**: a Multi line is `{product, country_code: "", region: {id, name}, plan}` (`region?` optional on `CartLine`). `lineName` uses `region.name` when set. `toApiLine` omits `country_code` for it. Existing lines unchanged; saved carts still load.

- [ ] **Step 1: Tests first** in `explorer.test.tsx` and `cart.test.tsx`: combobox (empty shows all, typing filters, Enter picks, no match text, blur restores); Single (pick Japan, choose eSIM, choose 10GB, Add → `onAdd` line with `country_code: "JP"`; WiFi shows "Unlimited" and "₱100"; WiFi disabled for a country with no rate; changing country resets the plan); Multi (no WiFi product; two regions with one name give two options; region without plans absent; changing region resets the plan; Add → line with `country_code: ""` and `region`; covers chips); cart (`lineName` → "Air Roam eSIM · Asia 5GB · 7 days"; `toApiLine` has no `country_code`).
- [ ] **Step 2:** Run, see them fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `npm test` and `npm run typecheck` clean (remove `tsconfig.tsbuildinfo`).
