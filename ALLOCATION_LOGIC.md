# Allocation logic

The yield engine calculates a plan per date from `combined_inventory.db`.
`upgrade_reserves.py` reserves capacity before `yield_engine.py` applies online
release rules. BAR pricing still uses the existing matrix, raw remaining counts,
seasonal limits and configured BAR shift.

## PMS assignment behavior

An unassigned booking consumes its booked category, even when that category is
negative. Assigning a Premiere booking to a suite room number restores one
Premiere and consumes one suite. Therefore, **only negative balances in the
current snapshot need virtual upgrade reserves**. Recalculate from scratch on
every run; do not accumulate a separate history of upgrade deductions.

Example: Premiere -5 / Suite 8 requires five suite reserves, leaving three.
After one assignment, Premiere -4 / Suite 7 requires four reserves, still leaving
three. Actual room assignments have already been accounted for by the PMS.

## Capacity before sales

For each date, the planner first determines its scope:

- The default and production Deluxe/Premiere calculation manages only Deluxe Room and Premiere Room.
- The all-category calculation adds the 11 simple room types when `include_simple_rooms: true`.
- Negative balances and missing values outside the selected scope do not block the calculation.

For each in-scope date:

1. Validate finite, whole room counts (negative balances are allowed). Reject an
   incomplete combined snapshot instead of filling missing values with zero.
2. Deduct configured operational buffers and active manual room holds from
   positive remaining capacity.
3. Match existing negative balances to eligible upgrade destinations in the hotel
   tier order below, restricted to categories managed by this calculation.
   Positive Deluxe inventory never covers Premiere.
4. Use integral flow to avoid double counting a destination. Configured route
   order is the preference; rerouting is allowed to accommodate a more
   constrained source. These are virtual capacity reserves, not room assignments.
5. If any shortage cannot be covered, mark the date blocked, show the unresolved
   count, and propose zero online rooms for the categories that shortage touches:
   every short category that could be the uncovered one (after rerouting) and all
   of its upgrade destinations. The status lists them. Other categories cannot
   help those guests (upgrades only go up), so they still allocate normally - an
   oversold suite does not close Deluxe or Premiere. A blocked date can mean
   missing upgrade routes, insufficient inventory, or held capacity.
6. Reserve destination capacity for new override sales before direct sales.
7. Apply the release rules to residual capacity, then clamp to manual online caps.

**There is no 97% (or other hotel-occupancy) blanket closure for higher categories.**
They can remain open at 97%, 99% or 100% when capacity supports the allocation.
Occupancy still drives BAR demand bands and the existing Deluxe override trigger.
Occupancy outside the configured demand bins is rejected rather than silently skipped.

## Configuring upgrade routes and holds

All yield entry points load the same JSON policy at runtime:

- Default: `backend/app/scraper/data/allocation_policy.json` (tracked in git as of 2026-09-26, same as the rest of `backend/app/scraper/data/`).
- Alternative: set `ALLOCATION_POLICY_PATH` to a JSON file.
- If absent, defaults follow the hotel tier order, trying the nearest eligible higher category first:
  Deluxe → Deluxe Pool Access → Premiere → Premiere Lagoon Access → Family Premiere →
  Deluxe Suite → Premiere Suite → Anvaya Suite No Pool → Anvaya Suite Whirlpool →
  Beach Front Private Suite → Anvaya Suite Private Pool → Anvaya Residence → Anvaya Villa.
- **Beach Front Private Suite cannot upgrade anywhere.**
- **Premiere Lagoon Access can upgrade only to Anvaya Suite Whirlpool, then Beach Front Private Suite.**
- Villa has no higher destination. All other sources may use any higher tier.
- An explicit empty destination list disables a route. Unspecified sources retain
  their defaults. Custom routes may narrow/reorder eligible destinations but cannot
  bypass the tier order or category restrictions. Unknown rooms, duplicates and
  invalid counts are rejected.
- Database names remain unchanged: `The Anvaya Suite Whirpool` means Whirlpool,
  and `The Anvaya Suite With Pool` means Private Pool.

Illustrative configuration (choose actual routes according to hotel policy):

```json
{
  "routes": {
    "Deluxe Room": ["Premiere Room"],
    "Premiere Room": ["Premiere Room Lagoon Access", "Premiere Suite Room"],
    "Deluxe Suite Room": ["Premiere Suite Room"]
  },
  "buffers": {
    "Premiere Suite Room": 1
  },
  "holds": [
    {
      "room_type": "Beach Front Private Suite Room",
      "start_date": "2026-10-01",
      "end_date": "2026-10-03",
      "rooms": 2,
      "max_online": 0
    }
  ]
}
```

Destination lists are explicit and ordered, **not transitive**. Lagoon → Whirlpool
never grants Lagoon access to Whirlpool's other destinations. Defaults enumerate
all eligible higher categories, so skipping a sold-out tier requires no chaining.
The engine cannot infer bedding, accessibility, family capacity or promised amenities.

Buffers apply every night. Holds apply on each date from start through end,
inclusive. Overlapping held room counts add together; overlapping `max_online`
limits use the lowest cap. A `rooms` hold excludes physical capacity from both
upgrade reserves and sales. A `max_online: 0` lock prevents direct online sales
but leaves the room eligible for upgrades. Holds must represent **extra** capacity
to protect, not rooms already deducted by the PMS. Existing release-rule holdbacks
still apply in addition to these configured buffers/holds.

## Release rules after reserves

| Safe remaining | Tiered online release |
| --- | --- |
| ≤ 0 | 0 |
| 1–5 | min(2, remaining, room cap) |
| 6–10 | min(5, remaining, room cap) |
| 11–50 | min(10, remaining, room cap) |
| > 50 | min(30, remaining, room cap) |

Deluxe and Premiere use the tiered release. The Deluxe override retains its
existing trigger: raw Deluxe < 1, raw Deluxe + Premiere > 0, and occupancy < 70
or raw Premiere > 31 (custom configurations may change those thresholds).
It opens at most the configured amount (default 2), backed by unused Premiere
capacity. Those rooms are deducted **before** Premiere's direct release.
It does not introduce new Premiere override sales backed by higher categories.

| Other category | Release from safe remaining |
| --- | --- |
| Deluxe Pool Access, Premiere Lagoon Access, Premiere Suite | Tiered release |
| Deluxe Suite | ≥5 → 4; 4 → 3; 2–3 → 2; 1 → 1; otherwise 0 |
| Beach Front Private Suite | remaining − 1, except release 1 if only 1 remains |
| Family Premiere, Anvaya Suite Whirpool, Anvaya Suite No Pool | max(0, remaining − 1) |
| Anvaya Suite With Pool, Residence, Villa | All safe remaining |

The existing Deluxe Suite fallback may offer one additional room when raw Deluxe
Suite ≤ 0 and safe Premiere Suite > 3. It must reserve backing through configured
Deluxe Suite routes before allocating direct higher-category sales. Existing
Deluxe Suite oversells are accommodated first.

## Results and publishing scope

Each room has Remaining Inventory, Upgrade Reserve, Override Reserve, Operational
Hold and Safe Inventory columns. Upgrade Reserve covers existing negative
balances; Override Reserve covers proposed new borrowed sales. Safe Inventory is
the residual before release rules and online caps. A blocked category can still show
positive residual inventory; its proposed sales remain zero. Global Allocation Status and Unresolved Upgrade Rooms explain blocked dates.

The Yield management category selector displays these explanations. Exports
include all result columns. Select **Calculate allocations for all room
categories** to include higher-category online targets in custom yield output.
`/api/custom-yield` accepts
`include_simple_rooms: true`; omitted/false keeps Deluxe/Premiere-only output for
compatibility with existing automated pipelines. The existing `/api/yield` path also
uses Deluxe/Premiere-only scope. All-category calculation is available through the custom endpoint.
Diagnostics are always included.

Calculation alone does not change PMS/D-EDGE availability. Existing update tools
publish only their selected category scope. The automated pipelines still push
Deluxe/Premiere only; use the existing other-room updater for higher categories.
A Deluxe/Premiere-only push cannot protect higher-category availability that is
already live. Recalculate and review all affected categories together before
publishing. This change does not make separate provider writes atomic; refresh
source data, apply required reductions before dependent increases, and verify
provider results. No live PMS/D-EDGE calls are needed to test this logic.

## Source-data assumptions and limits

The existing combiner adds PMS remaining availability and D-EDGE `Left for sale`.
The CM processor must preserve the date column before numeric coercion; otherwise
all CM dates can become `1970-01-01` and fail to align with PMS. The processor now
protects that date column, and raw-file validation confirms the combined values
equal PMS plus CM Left for sale for every room and date in the supplied snapshot.
The provider accounting contract still needs operational verification: the addback
is valid only if PMS availability excludes the unsold online allotment added back
by the combiner.
The supplied room-assignment behavior establishes how upgrades move inventory,
but does not itself establish the allotment-addback contract.

The planner works with daily category totals. It cannot guarantee one continuous
room assignment across a multi-night stay, validate guest-specific requirements,
or observe changes after the source snapshot. Those require reservation/room-level
data and provider synchronization. A virtual reserve is a planning deduction only.
