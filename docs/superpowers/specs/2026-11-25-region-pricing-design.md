# Region pricing — design

> **Updated 2026-11-25:** the highest-price rule was removed for now (every Pocket WiFi item pays its own plan's price), the per-region daily rate became Pocket WiFi plans, and region names are shown in the Multi-Country Explorer. See `plans/2026-11-25-wifi-plans-and-store-redesign.md`.

Covers `air-roam-be` and `air-roam-fe`. Status: approved 2026-11-25.

## Why

Staff want one place to set prices. Today GB, validity, price and countries are repeated on every product variant. They move to a **Region** that staff create. Customers never see regions; they choose a product and a country.

## What was decided (by you)

1. **Product** has no price, GB or validity.
2. **Region** is created by staff: custom name, one or more countries. Plans are created inside the region: GB, days, price, all custom (e.g. 5GB 7 days, 10GB 14 days, 14GB 30 days, 30GB 3 days).
3. **SIM/eSIM**: every SIM and eSIM product automatically offers all plans of the chosen country's region. No variant step in admin.
4. **Pocket WiFi**: no variants, unlimited data. The customer picks a country from a dropdown; the price is that country's region daily rate × days. This is the only product with a booking.
5. **Highest price**: with several Pocket WiFi items in one checkout, every item is charged the highest region daily rate among them (if NA > Asia 1, the NA rate is used and shown at checkout).
6. **Delivery fee**: ₱200 if total booked days across the checkout are 7 or fewer; free above 7.
7. Region names are never shown to customers. Products are.

## Worked examples (these are the acceptance numbers)

| Checkout | Rate used | Days | WiFi | Fee | Total |
|---|---|---|---|---|---|
| Asia 1 ₱100 + NA ₱50 + EU ₱10, 2 days each | 100 | 6 | 600 | 200 | **₱800** |
| Same, but the EU item is 3 days | 100 | 7 | 700 | 200 | **₱900** |
| Same, but the EU item is 4 days | 100 | 8 | 800 | 0 | **₱800** |
| EU ₱10 × 30 days + Asia 1 ₱100 × 2 days | 100 | 32 | 3,200 | 0 | **₱3,200** |
| One Asia 1 item, 3 days, 2 devices | 100 | 3 | 600 | 200 | **₱800** |
| One eSIM plan ₱399 | – | – | – | 0 | **₱399** |
| eSIM ₱399 + one Asia 1 item × 2 days | 100 | 2 | 200 | 200 | **₱799** |

## Calls made here (correct any)

- Days are end date − start date (Dec 12 → Dec 14 = 2 days), as today.
- Quantity multiplies the price, not the day count.
- The fee and the highest-price rule look only at Pocket WiFi. SIM/eSIM have no dates, so they add no days; an order without WiFi pays no fee.
- One country and one date range per WiFi cart item; a three-country trip is three items.
- SIM and eSIM share the same region plans and prices.
- A country belongs to at most one **active** region.
- A region with no WiFi rate doesn't rent WiFi. A region with no active plans sells no SIM/eSIM.
- SIM/eSIM booking goes away (no choosing dates after payment; no booking record). Plan days start on activation.
- Orders snapshot name, country, price, days and fee, so later edits never change past orders.
- ₱200 and 7 days are constants in code, not editable in admin.

## Removed, because regions are hidden

- Store: the Multi-country page and packs, region filter chips, region text on destination cards. A **Products** page takes the Multi-country menu slot.
- Plan badge ("Best value") and "Featured on home". Neither was in the request; only the badge was visible to customers.
- API: `multi-country-packs`, staff variants, traveler booking create/edit. Any mobile app build using these must change too.

## Approaches considered

1. **Automatic: the region owns plans, products offer all of them** — picked by you. One place to edit.
2. Variant = product + region — more control per product, extra step for every plan. Not picked.
3. Variant holds GB/days, region holds a price grid — blank cells can't be sold and it splits validity from region. Dropped.

## How it works

```
Region ── countries[], pocket_wifi_daily_rate (blank = no WiFi), is_active
  └── RegionPlan ── data_mb (blank = unlimited), validity_days, price, is_active
Product ── name, type, image, description, is_active        (no prices)

SIM/eSIM line = product + country + plan          Pocket WiFi line = product + country + dates
price         = plan.price × qty                  price            = highest rate × days × qty
```

The server does all pricing. The store shows the same calculation and, if the server's total differs (price changed, item gone), stops and shows the new total before payment.

A cart item is removed at checkout, with a notice, when: the product/plan/region is inactive or deleted, the plan's region doesn't cover the country, or the country has no WiFi rate. Removed items don't count toward the highest rate or the days.

### Screens

```
ADMIN  Regions                         STORE  eSIM / SIM card
Name [Asia 1]                          Country [Japan ▼]
Countries [JP ×][KR ×][+ add]          (5GB · 7 days) (10GB · 14 days)
Pocket WiFi rate/day [100]             ₱399                [Add to cart]
Plans
  5GB   7 days  ₱399  Edit Delete      STORE  Pocket WiFi card
  10GB 14 days  ₱699  Edit Delete      Country [Japan ▼]  ₱100 per day
  [Add plan]                           [Dec 12] → [Dec 14]
                                       2 days · ₱200       [Rent device]
CART / CHECKOUT SUMMARY
Japan Pocket WiFi   ₱100 × 2 days   ₱200
USA Pocket WiFi     ₱100 × 2 days   ₱200
"Pocket WiFi is charged at the highest daily rate in your cart."
Delivery fee                        ₱200   (or "Free")
Total                               ₱600
```

## Existing data

The local database has no products or orders. The migration **stops with a message** if it finds old order lines or variants, instead of deleting them. A database with real data needs a separate conversion.

## Non-goals

Editable fee, per-product plan choice, per-customer SIM/eSIM dates, several countries in one WiFi item, blocking overlapping WiFi dates, stock/device counts.

## Anti-goals

The customer being charged a total they weren't shown; a region name or id appearing in any public response; past orders changing when staff edit a region.
