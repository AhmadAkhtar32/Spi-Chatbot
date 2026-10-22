"""Permission-scoped BI calculations over the demo snapshot."""

import os
import secrets
from collections import defaultdict
from datetime import date
from decimal import (
    Decimal,
    DecimalException,
    InvalidOperation,
    ROUND_HALF_UP,
)
from functools import lru_cache

from business_data_provider import (
    DataSourceUnavailable,
    DemoJsonProvider,
)
from demo_policy import AccessDenied, authorize_expert


AREAS = {
    "sales": (
        "sales_orders",
        "sales",
        "sales_orders.read",
    ),
    "purchases": (
        "purchase_orders",
        "purchasing",
        "purchase_orders.read",
    ),
    "stock": (
        "stock",
        "inventory",
        "stock.read",
    ),
}


def area_allowed(user, area):
    _, module, permission = AREAS[area]
    return (
        module in user["module_licenses"]
        and permission in user["permissions"]
    )


def number(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError("Nonfinite number")
        return result
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DataSourceUnavailable(
            "Invalid numeric source value"
        ) from exc


def money(value):
    try:
        return str(
            value.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        )
    except DecimalException as exc:
        raise DataSourceUnavailable(
            "Invalid source monetary total"
        ) from exc


class DemoBIProvider(DemoJsonProvider):
    def summary(
        self,
        identity,
        *,
        area="sales",
        date_from=None,
        date_to=None,
        status=None,
        party_id=None,
        warehouse_id=None,
    ):
        authorize_expert(
            identity[0],
            identity[1],
            "bi_expert",
        )

        if (
            area not in AREAS
            or not area_allowed(identity[0], area)
        ):
            raise AccessDenied("BI area unavailable")

        kind = AREAS[area][0]
        rows = []
        wanted = (status or "").strip().casefold()

        party_key = (
            "supplier_party_id"
            if area == "purchases"
            else "customer_party_id"
        )

        for row in self._rows(kind):
            if not self._visible(identity, kind, row):
                continue

            if (
                warehouse_id is not None
                and row.get("warehouse_id") != warehouse_id
            ):
                continue

            if (
                party_id is not None
                and row.get(party_key) != party_id
            ):
                continue

            if (
                wanted
                and str(row.get("status", "")).casefold()
                != wanted
            ):
                continue

            if area != "stock":
                try:
                    ordered = date.fromisoformat(
                        row["order_date"]
                    )
                except (
                    KeyError,
                    TypeError,
                    ValueError,
                ) as exc:
                    raise DataSourceUnavailable(
                        "Invalid source order date"
                    ) from exc

                if date_from and ordered < date_from:
                    continue

                if date_to and ordered > date_to:
                    continue

            rows.append(row)

        result = (
            self._stock(rows)
            if area == "stock"
            else self._orders(rows, party_key)
        )

        return {
            "area": area,
            **result,
            **self.metadata(),
        }

    def _orders(self, rows, party_key):
        groups = {
            "status": {},
            "monthly": {},
            "parties": {},
        }

        parties = {
            row["id"]: row
            for row in self._data["parties"]
        }

        total = Decimal(0)

        for row in rows:
            amount = number(row.get("total_amount_pkr"))
            total += amount

            keys = {
                "status": str(
                    row.get("status", "Unknown")
                ),
                "monthly": row["order_date"][:7],
                "parties": row[party_key],
            }

            for group, key in keys.items():
                bucket = groups[group].setdefault(
                    key,
                    {
                        "count": 0,
                        "amount": Decimal(0),
                    },
                )
                bucket["count"] += 1
                bucket["amount"] += amount

        tables = {}

        for group, buckets in groups.items():
            keys = sorted(buckets)

            if group == "parties":
                keys = sorted(
                    keys,
                    key=lambda key: (
                        -buckets[key]["amount"],
                        key,
                    ),
                )[:5]

            tables[group] = [
                {
                    "id": key,
                    "label": (
                        parties.get(key, {}).get(
                            "name", key
                        )
                        if group == "parties"
                        else key
                    ),
                    "count": buckets[key]["count"],
                    "order_value_pkr": money(
                        buckets[key]["amount"]
                    ),
                }
                for key in keys
            ]

        average = (
            total / len(rows)
            if rows
            else Decimal(0)
        )

        return {
            "record_count": len(rows),
            "metrics": [
                {
                    "label": "Matching orders",
                    "value": len(rows),
                    "unit": "orders",
                },
                {
                    "label": "Total order value",
                    "value": money(total),
                    "unit": "PKR",
                },
                {
                    "label": "Average order value",
                    "value": money(average),
                    "unit": "PKR",
                },
            ],
            "tables": tables,
            "note": (
                "Order values include the selected statuses. "
                "They are not recognized revenue, payments "
                "or profit. Dates use order_date. "
                "Top parties show at most five results."
            ),
        }

    def _stock(self, rows):
        items = {
            row["id"]: row
            for row in self._data["items"]
        }
        warehouses = {
            row["id"]: row
            for row in self._data["warehouses"]
        }

        grouped = {}
        units = defaultdict(lambda: Decimal(0))
        unavailable = 0

        for row in rows:
            amount = number(
                row.get("quantity_available")
            )
            unit = items.get(
                row["item_id"], {}
            ).get("unit")

            if (
                not isinstance(unit, str)
                or not unit.strip()
            ):
                raise DataSourceUnavailable(
                    "Missing source stock unit"
                )

            units[unit] += amount
            empty = amount <= 0
            unavailable += int(empty)

            bucket = grouped.setdefault(
                row["warehouse_id"],
                {
                    "rows": 0,
                    "unavailable": 0,
                },
            )
            bucket["rows"] += 1
            bucket["unavailable"] += int(empty)

        return {
            "record_count": len(rows),
            "metrics": [
                {
                    "label": "Stock rows",
                    "value": len(rows),
                    "unit": "item/warehouse pairs",
                },
                {
                    "label": "Distinct items",
                    "value": len({
                        row["item_id"]
                        for row in rows
                    }),
                    "unit": "items",
                },
                {
                    "label": "Unavailable stock rows",
                    "value": unavailable,
                    "unit": "rows",
                },
            ],
            "tables": {
                "warehouses": [
                    {
                        "id": key,
                        "label": warehouses.get(
                            key, {}
                        ).get("name", key),
                        "count": grouped[key]["rows"],
                        "unavailable": grouped[key][
                            "unavailable"
                        ],
                    }
                    for key in sorted(grouped)
                ],
                "units": [
                    {
                        "label": key,
                        "available_quantity": str(
                            units[key]
                        ),
                    }
                    for key in sorted(units)
                ],
            },
            "note": (
                "Stock uses snapshot quantities, not "
                "historical balances. Unavailable means "
                "quantity_available <= 0. Quantities are "
                "grouped by unit; pieces and rolls "
                "are not combined."
            ),
        }

    def suggestions(self, identity):
        authorize_expert(
            identity[0],
            identity[1],
            "bi_expert",
        )

        buckets = []
        available = []
        rng = secrets.SystemRandom()

        for area in AREAS:
            if not area_allowed(identity[0], area):
                continue

            available.append(area)
            report = self.summary(
                identity,
                area=area,
            )

            if not report["record_count"]:
                continue

            if area == "stock":
                choices = [
                    (
                        "Summarize my permitted stock",
                        "summary",
                    ),
                    (
                        "Show unavailable stock by warehouse",
                        "warehouses",
                    ),
                    (
                        "Show stock quantities grouped by unit",
                        "units",
                    ),
                ]
            else:
                role = (
                    "customers"
                    if area == "sales"
                    else "suppliers"
                )

                choices = [
                    (
                        f"Summarize my {area} orders",
                        "summary",
                    ),
                    (
                        f"Show {area} order values by month",
                        "monthly",
                    ),
                    (
                        f"Show {area} orders by status",
                        "status",
                    ),
                    (
                        f"Show top {role} by order value",
                        "parties",
                    ),
                ]

            rng.shuffle(choices)

            bucket = [
                {
                    "question": question,
                    "area": area,
                    "view": view,
                }
                for question, view in choices
            ]

            if (
                area != "stock"
                and report["tables"]["parties"]
            ):
                party = report["tables"]["parties"][0]

                bucket.append({
                    "question": (
                        f"Summarize {area} orders "
                        f"for {party['label']}"
                    ),
                    "area": area,
                    "view": "summary",
                    "filters": {
                        "party_id": party["id"],
                    },
                })

            rng.shuffle(bucket)
            buckets.append(bucket)

        rng.shuffle(buckets)
        selected = []

        maximum = max(
            (len(bucket) for bucket in buckets),
            default=0,
        )

        for index in range(maximum):
            for bucket in buckets:
                if index < len(bucket):
                    selected.append(bucket[index])

        return {
            "suggestions": selected[:6],
            "available_areas": available,
            **self.metadata(),
        }


@lru_cache(maxsize=1)
def _demo_bi_provider():
    return DemoBIProvider()


def get_bi_provider():
    source = os.environ.get(
        "BUSINESS_DATA_SOURCE",
        "demo_json",
    ).strip().lower()

    if (
        source != "demo_json"
        or os.environ.get("ENABLE_DEMO_SESSIONS") != "1"
    ):
        raise DataSourceUnavailable(
            "BI source is not configured"
        )

    return _demo_bi_provider()