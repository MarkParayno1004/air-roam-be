# Region Pricing Implementation Plan


**Goal:** Staff set GB, days and prices on a Region; SIM/eSIM sell the region's plans and Pocket WiFi is booked per day at the highest region rate in the checkout, plus a ₱200 fee at 7 days or fewer.

**Architecture:** `Region` + `RegionPlan` replace `ProductVariant`. Checkout resolves a region from the chosen country, drops unavailable lines, then prices what is left. The store shows the same calculation but the server's total always wins. Regions appear only under `/staff`.

**Tech Stack:** Django 5 + DRF + Postgres (ArrayField), pytest; React 19 + React Router 7 + TanStack Query, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-25-region-pricing-design.md`

## Global Constraints

- BE = `/Users/markphilipparayno/personal/air-roam/air-roam-be`, FE = `/Users/markphilipparayno/personal/air-roam/air-roam-fe`. All paths below are relative to one of these.
- Branch `feat/region-pricing` in **both** repos. Both have the user's uncommitted edits (BE: `.env.example`, `README.md`, `docker-compose.yml`; FE: `apps/store/app/seo/prerender.ts`, `prerender.test.ts`, `apps/store/package.json`). Never stage, revert or overwrite them. Task 8 edits `prerender.ts`: stage that one line with a patch, not the whole file.
- `DELIVERY_FEE = 200`, `DELIVERY_FEE_MAX_DAYS = 7`: fee applies when `0 < total WiFi days <= 7`; 8 or more is free. Quantity does not multiply days. Days = end date − start date.
- No region name, id or `region` key in any public (non-`/staff`) response.
- No new dependencies. Order snapshots never change after creation.
- BE tests: `.venv/bin/python -m pytest -q` (needs Docker Postgres; baseline 136 passed). FE tests: `npm test` (baseline 107 passed).
- FE `npm run typecheck` is red from Task 6 until Task 10, because the shared generated types change first. Vitest must pass for the files each task owns.

## Review Focus

1. A WiFi item becomes unavailable while in the cart → removed **before** the highest rate and days are computed, so it can't raise the price or waive the fee (Task 3).
2. Staff reactivate a region whose countries now belong to another active region → rejected, naming the region (Task 2).
3. A request pairs a plan with a country its region doesn't cover → item removed, never sold at another region's price (Task 3).
4. A customer returns with a cart saved before this release → empty cart, no crash (Task 7).
5. The server's total differs from the displayed total with no price notice (fee changed, or an item removed) → customer sees the new total before paying (Task 9).

---

### Task 1: Region and plan models (BE)

**Files:** Modify `catalog/models.py`, `catalog/admin.py`, `catalog/signals.py`, `catalog/views.py` (import only), `conftest.py`, `tests/test_admin.py`. Create `catalog/migrations/0003_region_regionplan.py` (makemigrations). Test `catalog/tests/test_regions.py`.

**Produces** (in `catalog.models`):
- `Region(SoftDeleteModel)`: `name` Char(100); `countries` ArrayField(Char(2)), normalized in `save()` like `ProductVariant`, GIN index `region_countries_gin`; `pocket_wifi_daily_rate` Decimal(12,2) null, min 0.01; `is_active` default True; ordering `["name"]`.
- `RegionPlan(SoftDeleteModel)`: `region` FK PROTECT `related_name="plans"`; `data_mb` PositiveInteger null (= unlimited), min 1; `validity_days` PositiveInteger, min 1; `price` Decimal(12,2) min 0.01; `is_active`; ordering `["validity_days", "price"]`; property `label: str`.
- `region_for_country(code: str) -> Region | None`: the oldest live active region containing the code (deterministic if two overlap).
- `overlapping_region(countries: list[str], exclude_pk=None) -> tuple[str, Region] | None`: first (country code, other live active region).
- Fixtures in `conftest.py`: `region_factory(**fields)` (defaults name "Asia 1", countries ["JP"], `pocket_wifi_daily_rate=Decimal("100.00")`) and `plan_factory(region=None, **fields)` (defaults `data_mb=5120, validity_days=7, price=Decimal("399.00")`).

The existing `class Region(TextChoices)` is renamed `VariantRegion` here and deleted in Task 5.

- [ ] **Step 1: Failing tests** in `catalog/tests/test_regions.py`

```python
@pytest.mark.parametrize("mb,days,label", [(5120, 7, "5GB · 7 days"), (None, 30, "Unlimited · 30 days"), (512, 1, "0.5GB · 1 day")])
def test_plan_label(plan_factory, mb, days, label):
    assert plan_factory(data_mb=mb, validity_days=days).label == label

def test_region_countries_normalized(region_factory):
    assert region_factory(countries=["kr", "jp", "kr"]).countries == ["JP", "KR"]

def test_region_for_country_ignores_inactive_and_deleted(region_factory):
    region_factory(name="Off", is_active=False)
    region_factory(name="Gone").soft_delete()
    live = region_factory(name="Live")
    assert region_for_country("JP") == live and region_for_country("FR") is None

def test_overlapping_region(region_factory):
    r = region_factory(countries=["JP", "KR"])
    assert overlapping_region(["SG", "KR"]) == ("KR", r)
    assert overlapping_region(["KR"], exclude_pk=r.pk) is None
```

- [ ] **Step 2:** `.venv/bin/python -m pytest catalog/tests/test_regions.py -q` → FAIL (ImportError)
- [ ] **Step 3:** Implement. GB in `label` is `f"{round(mb / 1024, 1):g}GB"`. Add both models to the `on_catalog_change` receivers and to admin; extend `tests/test_admin.py`. Mark the missing DB constraint: `# shortcut: overlap checked in the serializer only, add a country table with a unique constraint if staff edit regions concurrently`.
- [ ] **Step 4:** Full BE suite → PASS
- [ ] **Step 5:** Commit `feat: add Region and RegionPlan models`

### Task 2: Staff region API (BE)

**Files:** Modify `catalog/staff_views.py`, `catalog/staff_urls.py`. Test `catalog/tests/test_staff_regions.py`.

**Consumes:** Task 1. **Produces:** `StaffRegionViewSet`, `StaffPlanViewSet` (permission `IsMarketingOrAdmin`, soft delete, nested exactly like `StaffVariantViewSet`):
- `/api/v1/staff/regions` GET/POST, `/regions/<uuid>` GET/PATCH/PUT/DELETE → `StaffRegion {id, name, countries, pocket_wifi_daily_rate, is_active, created_at, updated_at, plans: StaffPlan[]}`; list supports `?search=` on name.
- `/api/v1/staff/regions/<uuid>/plans` and `/plans/<uuid>` → `StaffPlan {id, label, data_mb, validity_days, price, is_active, created_at, updated_at}`.
- `plans` in `StaffRegion` excludes soft-deleted plans (`Prefetch` with `to_attr="live_plans"`, as products do for variants).

- [ ] **Step 1: Failing tests** (`S = "/api/v1/staff"`)

```python
def test_create_region_and_plan(marketing_api):
    r = marketing_api.post(f"{S}/regions", {"name": "Asia 1", "countries": ["kr", "jp"], "pocket_wifi_daily_rate": "100.00"}, format="json")
    assert r.status_code == 201 and r.json()["countries"] == ["JP", "KR"]
    p = marketing_api.post(f"{S}/regions/{r.json()['id']}/plans", {"data_mb": 5120, "validity_days": 7, "price": "399.00"}, format="json")
    assert p.status_code == 201 and p.json()["label"] == "5GB · 7 days"

def test_country_in_another_active_region_rejected(marketing_api, region_factory):
    region_factory(name="Asia 1", countries=["JP"])
    r = marketing_api.post(f"{S}/regions", {"name": "Asia 2", "countries": ["KR", "JP"]}, format="json")
    assert r.status_code == 400 and r.json()["countries"] == ["Japan is already in region Asia 1."]

def test_reactivating_overlapping_region_rejected(marketing_api, region_factory):
    region_factory(name="Asia 1")
    off = region_factory(name="Asia 2", is_active=False)
    assert marketing_api.patch(f"{S}/regions/{off.id}", {"is_active": True}, format="json").status_code == 400

def test_editing_region_does_not_clash_with_itself(marketing_api, region_factory):
    r = region_factory()
    assert marketing_api.patch(f"{S}/regions/{r.id}", {"countries": ["JP", "KR"]}, format="json").status_code == 200

@pytest.mark.parametrize("bad", [{"price": "0"}, {"price": "-1"}, {"validity_days": 0}, {"data_mb": 0}])
def test_bad_plan_values(marketing_api, plan_factory, bad):
    p = plan_factory()
    r = marketing_api.patch(f"{S}/regions/{p.region_id}/plans/{p.id}", bad, format="json")
    assert r.status_code == 400 and next(iter(bad)) in r.json()

def test_wifi_rate_optional_but_positive(marketing_api, region_factory):
    url = f"{S}/regions/{region_factory().id}"
    assert marketing_api.patch(url, {"pocket_wifi_daily_rate": None}, format="json").status_code == 200
    assert marketing_api.patch(url, {"pocket_wifi_daily_rate": "0"}, format="json").status_code == 400

def test_deletes_are_soft_and_travelers_forbidden(marketing_api, auth_api, plan_factory):
    p = plan_factory()
    assert auth_api.get(f"{S}/regions").status_code == 403
    assert marketing_api.delete(f"{S}/regions/{p.region_id}/plans/{p.id}").status_code == 204
    assert marketing_api.get(f"{S}/regions/{p.region_id}").json()["plans"] == []
    assert marketing_api.delete(f"{S}/regions/{p.region_id}").status_code == 204
    assert RegionPlan.all_objects.filter(pk=p.pk).exists()
```

- [ ] **Step 2:** Run → FAIL (404)
- [ ] **Step 3:** Implement. The overlap check is in `validate()`, reading `countries`/`is_active` from attrs then instance (both default for a create), and only when the result is active.
- [ ] **Step 4:** Full BE suite → PASS
- [ ] **Step 5:** Commit `feat: staff region and plan endpoints`

### Task 3: Region-priced checkout and delivery fee (BE)

**Files:** Modify `orders/models.py`, `orders/checkout.py`, `orders/serializers.py`, `conftest.py`. Create `orders/migrations/0003_region_pricing.py`. Tests: `orders/tests/test_checkout.py` and every test using `variant_factory` for orders (`orders/tests/test_staff.py`, `bookings/tests/*`, `payments/tests/*`).

**Consumes:** `Region`, `RegionPlan`, `region_for_country`.

**Produces:**
- `Order.delivery_fee` Decimal(12,2) default 0, included in `total_amount`; added to `OrderSerializer`.
- `OrderLine`: `product_variant` removed; `product` FK PROTECT; `region_plan` FK PROTECT null (null = Pocket WiFi). Snapshot fields keep their names. `OrderLineSerializer` swaps `product_variant` for `product`, `region_plan`.
- Request line: `{product_id: uuid, country_code: str(2), region_plan_id?: uuid|null, quantity 1-10, expected_unit_price, start_at?, end_at?}`. `expected_unit_price` for WiFi is the rate the customer saw charged (the cart's highest).
- Response: `price_updates: [{name, old_unit_price, new_unit_price}]`, `removed_lines: [{name}]`; no ids.
- `orders.checkout`: `DELIVERY_FEE = Decimal("200.00")`, `DELIVERY_FEE_MAX_DAYS = 7`, `create_order(user, client, lines) -> CheckoutResult` (signature unchanged).
- Fixture `product_factory(product_type="esim", **fields)`; `order_factory(kind, owner, client, start_in_days, nights)` keeps its signature, with eSIM ₱799 and WiFi ₱350/day in Japan so existing payment totals hold except for the fee.

Algorithm, in order, inside the existing `@transaction.atomic`:
1. Per line load the product (`Product.all_objects`), uppercase the country. SIM/eSIM without `region_plan_id` → `DomainError("plan_required", "Choose a plan.")`. Available when product is live and active, and: SIM/eSIM → plan and its region are live and active and the country is in `region.countries`; WiFi → `region_for_country(code)` has a rate. A WiFi line ignores `region_plan_id`.
2. Unavailable → `removed_lines` with `name`; none left → existing `nothing_to_buy`.
3. WiFi lines kept: days from `check_dates`; `rate = max(region rates)`; `total_days = sum(days)`.
4. Unit price = plan price or `rate`; if ≠ `expected_unit_price` → `price_updates`. `line_total` = price × qty (× days for WiFi).
5. `delivery_fee = DELIVERY_FEE if 0 < total_days <= DELIVERY_FEE_MAX_DAYS else 0`; total = lines + fee.
6. WiFi line creates a `Booking` with `destination_country_codes=[code]`.

Snapshots: `variant_name_snapshot` = `"Japan 5GB · 7 days"` (country name + plan label) or `"Japan"` for Pocket WiFi (shown next to `product_name_snapshot`; changed after review so two products are distinguishable); `countries_snapshot=[code]`; `pricing_unit_snapshot` `per_day`/`per_plan`. Removed line `name` is the same string, or `""` when the product, plan or country is unknown.

Migration `0003` is hand-written, depends on `catalog.0003` and first runs a `RunPython` guard: if any `OrderLine` or `catalog.ProductVariant` row exists, raise `RuntimeError("Region pricing replaces product variants. This database still has variants or order lines; convert or remove them before migrating.")`. Then the schema operations (empty table, so the non-null `product` FK needs no default).

- [ ] **Step 1: Failing tests** in `orders/tests/test_checkout.py`; replace its variant tests. Helpers: `line(product, code, plan=None, price=..., **kw)`, and `wifi(price, code, start, end, **kw)` for a Pocket WiFi line.

```python
@pytest.fixture
def world(region_factory, product_factory):
    """Asia 1 (JP) 100/day, NA (US) 50, EU (FR) 10; one Pocket WiFi product."""

@pytest.mark.parametrize("trips,rate,fee,total", [
    ([("JP", 2), ("US", 2), ("FR", 2)], "100.00", "200.00", "800.00"),
    ([("JP", 2), ("US", 2), ("FR", 3)], "100.00", "200.00", "900.00"),
    ([("JP", 2), ("US", 2), ("FR", 4)], "100.00", "0.00", "800.00"),
    ([("FR", 30), ("JP", 2)], "100.00", "0.00", "3200.00"),
    ([("US", 2), ("FR", 2)], "50.00", "200.00", "400.00"),
])
def test_highest_rate_and_delivery_fee(auth_api, world, trips, rate, fee, total):
    # one line per trip, expected_unit_price=rate
    assert all(l["unit_price"] == rate for l in order["lines"])
    assert order["delivery_fee"] == fee and order["total_amount"] == total
    assert body["price_updates"] == []

def test_quantity_does_not_multiply_days(auth_api, world):  # JP, 3 days, qty 2
    assert (order["delivery_fee"], order["total_amount"]) == ("200.00", "800.00")

def test_esim_only_has_no_fee(...):   # plan 399 → total "399.00", fee "0.00", booking None, variant_name_snapshot "Japan 5GB · 7 days"
def test_esim_plus_wifi(...):         # 399 + JP 2 days → total "799.00"; eSIM unit_price stays "399.00"
def test_removed_line_does_not_set_the_rate_or_days(...):  # JP region deactivated; JP 5 days + US 2 days, expected 100
    # removed_lines == [{"name": "Japan Pocket WiFi"}]; US charged "50.00"; price_updates old 100.00 new 50.00; fee "200.00"; total "300.00"
def test_country_without_wifi_rate_removed(...)            # rate None → removed
def test_plan_from_region_not_covering_country_removed(...)  # plan of JP region with country_code "FR" → removed, nothing_to_buy 409
def test_inactive_or_deleted_plan_region_product_removed(...)  # parametrize each of the 6 states
def test_unknown_product_and_country_removed_with_empty_name(...)
def test_esim_without_plan_rejected(...)                   # 400, code "plan_required", no Order row
def test_changed_plan_price_is_reported(...)               # expected 349.00 → price_updates [{"name": "Japan 5GB · 7 days", "old_unit_price": "349.00", "new_unit_price": "399.00"}]
def test_later_region_edit_keeps_order(...)                # edit rate, countries, plan price → order line and total unchanged
```

Keep the existing login, quantity, bad-date, privacy, cancel and Xendit-failure tests, ported to the new lines.

- [ ] **Step 2:** Run → FAIL
- [ ] **Step 3:** Implement models, migration, checkout, serializers, fixtures
- [ ] **Step 4:** Port remaining tests: WiFi order totals in `payments/tests` gain the ₱200 fee only where nights <= 7 (`order_factory` default is 6); read `order.total_amount` rather than hard-coding. Full suite → PASS
- [ ] **Step 5:** `.venv/bin/python manage.py makemigrations --check --dry-run` → "No changes detected". Commit `feat: region-priced checkout with highest WiFi rate and delivery fee`

### Task 4: Booking is Pocket WiFi only (BE)

**Files:** Modify `bookings/views.py`, `bookings/urls.py`, `bookings/serializers.py`, `bookings/tests/test_traveler.py`.

**Produces:** Travelers can only list and read bookings. Removed: `CreateBookingView`, `BookingViewSet.partial_update`, `_require_per_plan`, `PAID_STATES`, `BookingInputSerializer`, the `order-lines/<uuid>/booking` route and PATCH. Staff booking edit unchanged. In `bookings/rules.py`, `check_destinations` stays (staff edit uses it).

- [ ] **Step 1: Failing tests**, replacing the create/patch tests

```python
def test_travelers_cannot_create_or_change_bookings(auth_api, order_factory):
    line = _paid(order_factory("wifi")).lines.get()
    assert auth_api.post(f"{V1}/order-lines/{line.id}/booking", {}, format="json").status_code == 404
    assert auth_api.patch(f"{V1}/bookings/{line.booking.id}", {}, format="json").status_code == 405

def test_esim_order_never_has_a_booking(auth_api, order_factory):
    _paid(order_factory())
    assert auth_api.get(f"{V1}/bookings").json()["results"] == []
```

Keep `test_bookings_private`, using a WiFi order.

- [ ] **Step 2:** Run → FAIL. **Step 3:** Delete the code. **Step 4:** Full suite → PASS. **Step 5:** Commit `feat: bookings are Pocket WiFi only`

### Task 5: Public catalog without regions; remove variants (BE)

**Files:** Modify `catalog/{models,views,serializers,urls,staff_views,staff_urls,signals,admin}.py`, `catalog/management/commands/seed_demo.py`, `conftest.py` (drop `variant_factory`), `schema.yml`, all `catalog/tests/*`, `payments/tests/test_review_fixes.py` (drop the variant price test; Task 2 covers it), `tests/test_admin.py`. Create `catalog/migrations/0004_delete_productvariant.py` (depends on `orders.0003`).

**Produces:**
- `GET /api/v1/destinations` → `Destination[] {country_code, country_name, slug, from_price, pocket_wifi_daily_rate: str|null, plans: Plan[]}`, `Plan {id, label, data_mb, validity_days, price}`. `plans` is `[]` unless an active SIM/eSIM product exists; rate is null unless an active Pocket WiFi product exists; a country with neither is left out. `from_price` = lowest of both. Sorted by country name; cached as now. Mark `# shortcut: every country carries its plans, split into a detail endpoint past ~500KB`.
- `GET /api/v1/products` / `products/<uuid>` → `Product {id, product_name, product_type, product_thumbnail_img, product_description}`; active, live only; filters `product_type`, `search`.
- `StaffProduct` loses `variants`; staff filters left: `product_type`, `is_active`, `search` (product name only).
- Deleted: `ProductVariant`, `VariantRegion`, `VARIANT_FIELDS`, variant/pack serializers and views, `multi-country-packs`, staff variant routes, `sellable_variants`, `filtered_variants`. `PricingUnit` stays (orders and bookings use it).
- `seed_demo`, idempotent by name: the three existing products; regions `Asia 1` (JP KR SG TH MY VN HK TW, ₱100), `North America` (US CA, ₱50), `Europe` (FR DE IT ES NL CH PT BE AT GR, ₱10), each with plans 5GB/7d ₱399, 10GB/14d ₱699, 14GB/30d ₱999, 30GB/3d ₱499.

- [ ] **Step 1: Failing tests** in `catalog/tests/test_public_api.py`

```python
def test_destination_shape_and_no_region_leak(api, plan_factory, region_factory, product_factory):
    r = region_factory(name="Secret Zone", countries=["JP", "KR"])
    p = plan_factory(region=r)
    product_factory("esim"); product_factory("pocket_wifi")
    res = api.get("/api/v1/destinations")
    assert [d["country_code"] for d in res.json()] == ["JP", "KR"]
    assert res.json()[0] == {"country_code": "JP", "country_name": "Japan", "slug": "japan", "from_price": "100.00", "pocket_wifi_daily_rate": "100.00",
        "plans": [{"id": str(p.id), "label": "5GB · 7 days", "data_mb": 5120, "validity_days": 7, "price": "399.00"}]}
    assert "Secret Zone" not in res.content.decode() and str(r.id) not in res.content.decode()

def test_no_wifi_product_hides_rate(...)      # only esim → rate None, from_price "399.00"
def test_no_sim_product_hides_plans(...)      # only pocket_wifi → plans [], from_price "100.00"
def test_inactive_region_plan_hidden(...)     # inactive/deleted region → []; inactive plan not listed
def test_products_have_no_prices(...)         # keys == the five above; inactive and deleted products hidden
def test_region_edit_clears_cache_and_calls_hook(...)  # port the existing cache test: change rate, then plan price
```

`test_seed.py`: seeding twice keeps 3 regions, 12 plans, 3 products.

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. Deleting `ProductVariant` is safe: the guard in `orders.0003` already ran.
- [ ] **Step 4:** Full suite → PASS; `makemigrations --check --dry-run` clean; `.venv/bin/python manage.py migrate` then `seed_demo` on the local database succeed; `grep -rniE "variant" --include=*.py catalog orders bookings payments | grep -v migrations` shows only `variant_name*`.
- [ ] **Step 5:** `.venv/bin/python manage.py spectacular --file schema.yml`. Commit `feat: region-free public catalog, remove product variants`

### Task 6: Admin — regions and plans (FE)

**Files:** `packages/api/src/schema.d.ts` (`npm run gen:api`), `packages/api/src/types.ts`. Under `apps/admin/src`: create `pages/regions/{RegionsList,RegionEditor,PlanForm,PlanTable}.tsx`, `pages/regions/regions.test.tsx`; modify `routes.tsx`, `layout/Shell.tsx`, `lib/options.ts`, `pages/products/{ProductEditor,ProductsList,products.test}.tsx`, `components/CountryMultiSelect.tsx`; delete `pages/products/{VariantForm,VariantTable,AppPreview}.tsx`.

**Produces:** types `Plan`, `StaffRegion`, `StaffPlan` (drop `Variant`, `StaffVariant`, `PackGroup`, `Pack`). Routes `/regions`, `/regions/new`, `/regions/:id`; sidebar item "Regions & prices" after Products, visible to marketing and admin.

- `RegionEditor` follows `ProductEditor` (create → redirect to edit, then a Plans card). Fields: Region name, `CountryMultiSelect`, "Pocket WiFi rate per day (PHP)" with hint "Empty = no Pocket WiFi in this region", Active. Help text: "Customers never see the region name." Empty rate is sent as `null`.
- `PlanForm` from `VariantForm`: Data (GB) with hint "Empty = unlimited", Validity (days), Price (PHP), Active. `toPlanPayload(v: PlanFormValues) => {data_mb, validity_days, price, is_active}`. Server field errors show on fields, as today.
- `PlanTable` from `VariantTable`: Plan (`label`), Price, Status, Edit/Delete with the existing `ConfirmDialog`.
- `RegionsList`: Region, Countries (name, or "N countries" with the full list in `title`; move `countriesLabel` here), WiFi/day, Plans count, Status; search + `Pager`.
- `ProductEditor`: the Plans card becomes "Prices come from [Regions & prices]" linking to `/regions`. `ProductsList`: drop Country/Coverage/Region filters and the Plans column; search placeholder "Name". `CountryMultiSelect`: drop the "multi-country pack" wording.

- [ ] **Step 1: Failing tests** in `regions.test.tsx`; move the country-picker tests over; delete variant tests

```tsx
test("plan payload converts GB; empty means unlimited", () => {
  expect(toPlanPayload({ data_gb: "5", validity_days: "7", price: "399", is_active: true })).toEqual({ data_mb: 5120, validity_days: 7, price: "399", is_active: true });
  expect(toPlanPayload({ data_gb: "", validity_days: "30", price: "999", is_active: true }).data_mb).toBeNull();
});
test("creating a region posts countries and rate, blank rate is null")  // request staff/regions POST json
test("country clash from the server shows under countries")            // "Japan is already in region Asia 1."
test("plan is deleted only after confirming")                          // DELETE staff/regions/r1/plans/p1
test("marketing sees Regions & prices in the sidebar")
test("product editor has no plan form and links to regions")
```

- [ ] **Step 2:** `npx vitest run apps/admin` → FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5:** Commit `feat(admin): manage regions and plans`

### Task 7: Store — cart model and totals (FE)

**Files:** Modify `apps/store/app/cart/{store.tsx,rental.ts,cart.test.tsx}`, `apps/store/app/checkout/usePlaceOrder.ts`, `apps/store/app/catalog/useAddToCart.ts`.

**Produces:**
```ts
interface CartLine {
  id: string;
  product: { id: string; product_name: string; product_type: string };
  country_code: string;
  plan?: Plan;            // SIM/eSIM
  daily_rate?: string;    // Pocket WiFi: the chosen country's rate
  quantity: number;
  start_date?: string; end_date?: string;
}
type NewLine = Omit<CartLine, "id" | "quantity">;
useCart().add(l: NewLine): void          // same product+country+plan → quantity + 1 (max 10); WiFi always a new line
isRental(l): boolean                     // product_type === "pocket_wifi"
lineName(l): string                      // "Japan 5GB · 7 days" | "Japan Pocket WiFi"
interface CartTotals { rate: number; days: number; deliveryFee: number; total: number; lineTotal(l: CartLine): number }
cartTotals(lines: CartLine[]): CartTotals
toApiLine(l: CartLine, rate: number): Record<string, unknown>   // matches Task 3's request line
```
`DELIVERY_FEE = 200`, `DELIVERY_FEE_MAX_DAYS = 7` in `rental.ts` with a comment that the server decides. `lineProblem` loses the country check. Remove `applyServerChanges` (nothing but its test uses it). `isLine` requires `product.id`, `country_code`, and `plan.price` or `daily_rate`, so carts saved before this release reset to empty.

- [ ] **Step 1: Failing tests** in `cart.test.tsx` (`wifi(code, rate, start, end, quantity = 1)`)

```tsx
test.each([
  [[["JP", 100, 2], ["US", 50, 2], ["FR", 10, 2]], 100, 200, 800],
  [[["JP", 100, 2], ["US", 50, 2], ["FR", 10, 3]], 100, 200, 900],
  [[["JP", 100, 2], ["US", 50, 2], ["FR", 10, 4]], 100, 0, 800],
  [[["FR", 10, 30], ["JP", 100, 2]], 100, 0, 3200],
])("highest rate and fee %#", (trips, rate, fee, total) => {
  expect(cartTotals(lines(trips))).toMatchObject({ rate, deliveryFee: fee, total });
});
test("two devices for 3 days pay the fee")            // total 800
test("eSIM only has no fee; eSIM + 2 WiFi days = 799")
test("no dates yet → days 0, no fee shown")
test("a cart saved before region pricing resets")     // [{ id, variant: {...}, quantity }] → []
test("same plan and country increments; another country is a new line; WiFi is always a new line")
test("WiFi api line sends the charged rate, not its own")  // EU rate 10 in a cart with 100 → expected_unit_price "100.00", no region_plan_id
test("plan api line")   // { product_id, country_code: "JP", region_plan_id, quantity: 1, expected_unit_price: "399.00" }
```

- [ ] **Step 2:** `npx vitest run apps/store/app/cart` → FAIL. **Step 3:** Implement; `usePlaceOrder` passes `cartTotals(lines).rate`. **Step 4:** the pure-logic tests PASS (CartView render tests come in Task 9). **Step 5:** Commit `feat(store): region-priced cart totals`

### Task 8: Store — products with country dropdown (FE)

**Files:** Under `apps/store/app`: create `catalog/ProductCard.tsx`, `routes/products.tsx`; modify `lib/catalog.ts`, `catalog/{DestinationView,DestinationCard,PopularDestinations,catalog.test}.tsx`, `routes/{destination,destinations,home}.tsx`, `routes.ts`, `components/{Header,Footer}.tsx`, `seo/{jsonld,prerender}.ts`, `seo/sitemap.test.ts`; delete `routes/multi-country.tsx`.

**Produces:**
- `lib/catalog.ts`: `fetchDestinations()`, `fetchProducts(): Promise<Product[]>`, `fetchDestinationPage(slug): {destination, destinations, products}`. Removed: variants, packs, `REGIONS`, `regionLabel`.
- `ProductCard({ product, destinations, initialCountry, onAdd, today })`: name, image, description; labelled `Country` select listing only countries that sell this type (SIM/eSIM: `plans.length`; WiFi: rate set). `initialCountry` not sold → starts on "Choose a country". Changing country clears the plan.
  - SIM/eSIM: plans as a radio group named "Plan" by `label`; price appears once picked; "Add to cart" disabled until then.
  - WiFi: "₱100 per day · Unlimited data", Start/End date inputs (the `DateField` from `CartView`, exported), "2 days · ₱200" from `rentalDays`; "Rent device" disabled until `lineProblem` is null.
- `/products`: every active product as `ProductCard`, no initial country. Header/Footer "Multi-country" → "Products"; `STATIC_PATHS` `/multi-country` → `/products`.
- `DestinationView({ destination, destinations, products, onAdd, today })`: type tabs kept; one `ProductCard` per product with this country preselected; "Good to know": "Pocket WiFi dates are final once ordered. eSIM and SIM days start when you activate."
- `DestinationCard`: no region/pack line. `PopularDestinations`: no region chips; `limit` and `query` unchanged. Home: no packs section; step 3 → `["3  Connect", "Pocket WiFi is booked for your dates; eSIM and SIM start on activation."]`. Destinations subtitle: "{n} countries covered by eSIM, SIM and Pocket WiFi."
- `productJsonLd(d: Destination)`: prices = plan prices plus the WiFi rate when set; `offerCount` = their number.
- Routes pass `today={todayISO()}`. `/products` and destination pages are pre-rendered, so `ProductCard` sets the date inputs' `min` in an effect after mount; otherwise the HTML freezes the build date and hydration mismatches.

- [ ] **Step 1: Failing tests** in `catalog.test.tsx`

```tsx
test("eSIM: picking a country and plan shows its price and adds it")     // onAdd({ product, country_code: "JP", plan })
test("changing country clears the chosen plan")
test("WiFi: country dropdown changes the daily rate and total")          // JP "₱100 per day", US "₱50 per day"; 2 days → "₱200"/"₱100"
test("WiFi: countries without a rate are not offered")
test("WiFi: Rent device stays disabled without valid dates")
test("destination page preselects its country")
test("no region text anywhere on destination card or page")
test("popular destinations filter by query")
```

- [ ] **Step 2:** `npx vitest run apps/store/app/catalog apps/store/app/seo` → FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5:** Commit `feat(store): products with country pricing, drop multi-country packs`

### Task 9: Store — cart, checkout and account screens (FE)

**Files:** Under `apps/store/app`: modify `cart/{CartView,cart.test}.tsx`, `checkout/{CheckoutView,PaymentResultView,checkout.test}.tsx`, `account/{OrderCard,account.test}.tsx`, `routes/{account.orders.$id,account.bookings,legal}.tsx`; delete `account/BookingForm.tsx`, `components/CountryPicker.tsx`. Admin: `apps/admin/src/pages/orders/OrderDetail.tsx` (delivery fee row; no "No travel dates yet" for SIM/eSIM).

**Consumes:** `cartTotals`, `lineName` (Task 7).

**Behaviour:**
- Cart and checkout summaries: each line; WiFi as "₱100 × 2 days"; when WiFi lines have different own rates, the note "Pocket WiFi is charged at the highest daily rate in your cart."; a "Delivery fee" row whenever the cart has WiFi days ("₱200" with "Free when you book more than 7 days", or "Free"); Total.
- Cart item: WiFi keeps editable dates; the country picker is gone. SIM/eSIM line text: "Starts when you activate".
- `CheckoutView`: go to `changed` also when `Number(res.order.total_amount) !== total`, with `total` captured before `place()` (it clears the cart). `ChangedView` always titles with the new total and shows the delivery fee when > 0. React keys use the index (ids are gone).
- `PaymentResultView` and `OrderCard`: no "Choose/Edit travel dates" links or "choose after payment" text; SIM/eSIM shows "Starts when you activate"; OrderCard shows the delivery fee when > 0. `account.orders.$id` always renders `OrderCard`. Bookings empty state: "No bookings yet. Pocket WiFi rentals appear here."
- Legal terms: "Pocket WiFi rental dates are final once ordered; contact support to change them. eSIM and SIM plan days start when the plan is activated. Pocket WiFi orders of 7 days or fewer in total have a ₱200 delivery fee."

- [ ] **Step 1: Failing tests**

```tsx
// cart.test.tsx
test("summary shows highest-rate note, delivery fee and total")  // JP 100 ×2d + US 50 ×2d → ₱200, ₱200, "₱200" fee, total ₱600
test("8 days shows Free delivery; 7 days still pays")
test("no note when all WiFi lines share a rate; no fee row without WiFi")
// checkout.test.tsx — mocked total_amount must now equal the displayed total in the no-change test
test("server total differs with no notices → review screen, no redirect")   // 599 vs 399 → "₱599", redirect only after Continue to pay
test("price update and removed lines render without ids")
// account.test.tsx — delete the three BookingForm tests and the Choose travel dates test
test("paid eSIM line shows Starts when you activate and no date links")
test("order card shows the delivery fee")
```

- [ ] **Step 2:** `npx vitest run apps/store` → FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5:** Commit `feat: delivery fee and highest rate in cart, checkout and orders`

### Task 10: Clean-up and end-to-end check (both)

**Files:** FE `packages/ui/src/{cards.tsx,index.ts,ui.test.tsx}`, `e2e/{admin,store-checkout}.spec.ts`.

- [ ] **Step 1:** In `cards.tsx` keep only `ProductType` and `TYPE_LABEL`; drop the card tests.
- [ ] **Step 2:** E2E: admin opens "Regions & prices" → "Asia 1" and sees its plans. Store: `/destinations/japan` → eSIM card → "5GB · 7 days" → Add to cart → existing sign-up flow; the mock returns `total_amount: "399.00"`, `delivery_fee: "0.00"`; expect `lines: [{ country_code: "JP", quantity: 1, expected_unit_price: "399.00" }]`.
- [ ] **Step 3:** `npm run typecheck` → no errors; `npm test` → all pass; `npm run build` with the backend running and seeded → succeeds; BE full suite → all pass.
- [ ] **Step 4:** `grep -rniE "variant|multi-country|packs|regionLabel" apps packages e2e --include=*.ts --include=*.tsx --exclude-dir=node_modules --exclude-dir=.react-router --exclude=schema.d.ts` → only `variant_name*` and `Button variant=` style props.
- [ ] **Step 5:** `npx playwright test` with both apps and a seeded backend. If it can't run (ports: the user's store dev port is 5175 locally), report it as not run.
- [ ] **Step 6:** Commit `chore: remove variant cards, update e2e`
