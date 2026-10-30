"""Scoped business reads. Only the local JSON source is implemented.

The future SPIA API adapter must enforce scopes in its upstream queries too.
Business records and answers are not stored in the document-answer cache.
"""

from spia.core.paths import BACKEND_DIR

import json
import os
import secrets
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from spia.security.access_control import (
    AccessDenied, Resource, allowed_fields,
    project_record, require_feature,
)
from spia.security.store import load_policy

AREAS = {
    "stock": "stock",
    "sales": "sales_orders",
    "purchases": "purchase_orders",
}

MODULES = {
    "stock": "inventory",
    "sales_orders": "sales",
    "purchase_orders": "purchasing",
    "credit_return_notes": "sales",
    "payroll": "payroll",
    "tickets": None,
}

SEGMENTS = {
    "stock": "stock",
    "sales_orders": "sales-orders",
    "purchase_orders": "purchase-orders",
    "credit_return_notes": "credit-return-notes",
    "payroll": "payroll",
    "tickets": "tickets",
}


class BusinessUnavailable(RuntimeError):
    pass


def _canonical(value):
    if isinstance(value, dict):
        return {
            key: _canonical(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return sorted(
            (_canonical(item) for item in value),
            key=lambda item: json.dumps(item, sort_keys=True),
        )

    return value


def _policy_value(policy):
    return _canonical(
        policy.model_dump(
            mode="json",
            exclude={"valid_until"},
        )
    )


class BusinessService:
    def __init__(self, context):
        self.context = context
        self.used = set()
        self._data = None

    @property
    def data(self):
        if self._data is None:
            self._load()
        return self._data

    def _load(self):
        selected = os.environ.get(
            "BUSINESS_DATA_SOURCE", "snapshot_json"
        )

        if selected not in {"snapshot_json", "snapshot_json"}:
            raise BusinessUnavailable(
                "Selected business source is not implemented"
            )

        path = Path(
            os.environ.get("BUSINESS_DATA_PATH")
            or BACKEND_DIR / "data/sample_data.json"
        )

        try:
            with path.open("rb") as file:
                raw = file.read(20 * 1024 * 1024 + 1)

            if len(raw) > 20 * 1024 * 1024:
                raise ValueError(
                    "Snapshot exceeds this adapter's size limit"
                )

            self._data = json.loads(raw)

            if (
                not isinstance(self._data, dict)
                or not isinstance(
                    self._data.get("snapshot_at"), str
                )
            ):
                raise ValueError("Invalid snapshot metadata")

            collections = {
                *MODULES,
                "items",
                "warehouses",
                "parties",
                "employees",
            }

            for kind in collections:
                if (
                    not isinstance(self.data.get(kind), list)
                    or any(
                        not isinstance(row, dict)
                        for row in self.data[kind]
                    )
                ):
                    raise ValueError("Invalid collection")

        except (
            OSError,
            ValueError,
            TypeError,
            UnicodeError,
        ):
            raise BusinessUnavailable(
                "Business snapshot is unavailable"
            ) from None

        try:
            self.indexes = {
                key: {
                    row.get("id"): row
                    for row in self.data[key]
                }
                for key in (
                    "items", "warehouses",
                    "parties", "employees",
                )
            }
        except (ValueError, TypeError):
            raise BusinessUnavailable(
                "Invalid lookup collection"
            ) from None

    def metadata(self):
        return {
            "source": "fictional_sample_snapshot",
            "snapshot_at": self.data["snapshot_at"],
        }

    def require(
        self,
        kind,
        feature=None,
        action="read",
        fields=frozenset(),
    ):
        feature = feature or (
            "support_expert"
            if kind == "tickets"
            else "business_lookup"
        )

        rules = [
            rule
            for rule in self.context.policy.rules
            if rule.feature == feature
            and rule.resource_type == kind
            and action in rule.actions
            and (
                MODULES[kind] is None
                or rule.module == MODULES[kind]
            )
        ]

        active = []
        error = AccessDenied("DATA_ACCESS_DENIED")

        for rule in rules:
            try:
                require_feature(
                    self.context.identity,
                    self.context.policy,
                    feature,
                    rule.module,
                )

                active.append(rule)
                self.used.add((feature, rule.module))

            except AccessDenied as exc:
                error = exc

        if not active:
            raise error

        available = {
            field
            for rule in active
            for field in rule.fields
        }

        if not fields <= available:
            raise AccessDenied("FIELD_ACCESS_DENIED")

        return feature, active

    def _labels(self, kind, raw):
        if kind == "stock":
            item = self.indexes["items"].get(
                raw.get("item_id"), {}
            )
            warehouse = self.indexes["warehouses"].get(
                raw.get("warehouse_id"), {}
            )
            return {
                "item_name": item.get("name"),
                "unit": item.get("unit"),
                "warehouse_name": warehouse.get("name"),
            }

        if kind == "payroll":
            employee = self.indexes["employees"].get(
                raw.get("employee_id"), {}
            )
            return {
                "employee_name": employee.get("name")
            }

        key = (
            "supplier_party_id"
            if kind == "purchase_orders"
            else (
                "party_id"
                if kind == "tickets"
                else "customer_party_id"
            )
        )

        party = self.indexes["parties"].get(
            raw.get(key), {}
        )

        result = {"party_name": party.get("name")}

        if kind != "tickets":
            result["party_role"] = (
                "supplier"
                if kind == "purchase_orders"
                else "customer"
            )

        return result

    def records(
        self,
        kind,
        *,
        feature=None,
        action="read",
        fields=frozenset(),
    ):
        feature, rules = self.require(
            kind, feature, action, fields
        )

        modules = {rule.module for rule in rules}
        attributes = {
            scope.attribute
            for rule in rules
            for scope in rule.scopes
        }

        result = []

        for raw in self.data[kind]:
            module = (
                raw.get("module")
                if kind == "tickets"
                else MODULES[kind]
            )

            if module not in modules:
                continue

            try:
                resource = Resource(
                    company_id=raw.get(
                        "company_id",
                        self.context.identity.company_id,
                    ),
                    resource_type=kind,
                    module=module,
                    classifications=["business"],
                    facts=[
                        {
                            "attribute": key,
                            "value": raw[key],
                        }
                        for key in attributes
                        if key in raw
                    ],
                )

                permitted = allowed_fields(
                    self.context.identity,
                    self.context.policy,
                    feature,
                    action,
                    resource,
                    requested_fields=fields,
                )

                labels = self._labels(kind, raw)

                safe = project_record(
                    self.context.identity,
                    self.context.policy,
                    feature,
                    action,
                    resource,
                    {**labels, **raw},
                )

            except AccessDenied as exc:
                if exc.code in {
                    "RESOURCE_DENIED",
                    "DATA_ACCESS_DENIED",
                }:
                    continue
                raise

            except (ValueError, TypeError):
                raise BusinessUnavailable(
                    "Invalid business record"
                ) from None

            result.append({
                "record": {
                    key: value
                    for key, value in safe.items()
                    if key in raw
                },
                "details": {
                    key: safe[key]
                    for key in labels
                    if key in permitted
                    and key in safe
                    and key not in raw
                },
            })

        return result

    def finish(self, result):
        fresh = load_policy(self.context.identity)

        for feature, module in self.used:
            require_feature(
                self.context.identity,
                fresh,
                feature,
                module,
            )

        if (
            _policy_value(fresh)
            != _policy_value(self.context.policy)
        ):
            raise AccessDenied("ACCESS_CHANGED")

        return {
            **result,
            **self.metadata(),
        }

    @staticmethod
    def filtered(items, kind, filters):
        result = []
        party_key = (
            "supplier_party_id"
            if kind == "purchase_orders"
            else "customer_party_id"
        )

        for item in items:
            record = item["record"]

            if any(
                filters.get(key) is not None
                and record.get(key) != filters[key]
                for key in (
                    "warehouse_id",
                    "employee_id",
                    "period",
                    "module",
                )
            ):
                continue

            if (
                filters.get("party_id") is not None
                and record.get(party_key)
                != filters["party_id"]
            ):
                continue

            if (
                filters.get("status")
                and str(
                    record.get("status", "")
                ).casefold()
                != filters["status"].casefold()
            ):
                continue

            if (
                filters.get("in_stock_only")
                and record.get(
                    "quantity_available", 0
                ) <= 0
            ):
                continue

            date_key = {
                "payroll": "period",
                "tickets": "created_at",
                "credit_return_notes": "date",
            }.get(kind, "order_date")

            value = record.get(date_key)

            if (
                filters.get("date_from")
                or filters.get("date_to")
            ):
                if value is None:
                    continue

                try:
                    recorded = date.fromisoformat(
                        value + "-01"
                        if kind == "payroll"
                        else value
                    )
                except (ValueError, TypeError):
                    raise BusinessUnavailable(
                        "Invalid business record date"
                    ) from None

                if (
                    filters.get("date_from")
                    and recorded < filters["date_from"]
                ):
                    continue

                if (
                    filters.get("date_to")
                    and recorded > filters["date_to"]
                ):
                    continue

            needle = filters.get(
                "q", ""
            ).strip().casefold()

            if needle and not any(
                needle in str(value).casefold()
                for value in (
                    *record.values(),
                    *item["details"].values(),
                )
            ):
                continue

            result.append(item)

        return result

    def search(
        self,
        kind,
        filters,
        fields=frozenset(),
    ):
        rows = self.filtered(
            self.records(kind, fields=fields),
            kind,
            filters,
        )

        date_key = {
            "payroll": "period",
            "tickets": "created_at",
            "credit_return_notes": "date",
        }.get(kind, "order_date")

        rows.sort(
            key=lambda item: (
                str(item["record"].get(date_key, "")),
                str(item["record"].get(
                    "id",
                    item["record"].get("item_id", ""),
                )),
                str(item["record"].get(
                    "warehouse_id", ""
                )),
                json.dumps(item, sort_keys=True),
            ),
            reverse=kind != "stock",
        )

        offset = filters["offset"]
        limit = filters["limit"]
        page = rows[offset:offset + limit]

        return self.finish({
            "kind": kind,
            "items": page,
            "total": len(rows),
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(page) < len(rows),
            "filters": filters,
        })

    def detail(
        self,
        kind,
        record_id,
        warehouse=None,
        fields=frozenset(),
    ):
        for item in self.records(
            kind, fields=fields
        ):
            record = item["record"]

            key = (
                "item_id"
                if kind == "stock"
                else "id"
            )

            if (
                record.get(key) == record_id
                and (
                    kind != "stock"
                    or record.get("warehouse_id")
                    == warehouse
                )
            ):
                return self.finish({
                    "kind": kind,
                    **item,
                })

        return None

    def suggestions(self):
        buckets = []

        for kind, segment in SEGMENTS.items():
            try:
                rows = self.records(kind)

            except AccessDenied as exc:
                if exc.code in {
                    "DATA_ACCESS_DENIED",
                    "MODULE_EXPIRED",
                    "MODULE_INACTIVE",
                    "PACKAGE_EXPIRED",
                    "PACKAGE_INACTIVE",
                    "FEATURE_NOT_ASSIGNED",
                }:
                    continue
                raise

            choices = []

            for item in rows:
                row = item["record"]

                if kind == "stock":
                    required = {
                        "item_id",
                        "warehouse_id",
                        "quantity_available",
                    }

                    if not required <= row.keys():
                        continue

                    target = (
                        f"stock/{row['item_id']}/"
                        f"{row['warehouse_id']}"
                    )
                    question = (
                        f"What is the stock of "
                        f"{row['item_id']} in "
                        f"{row['warehouse_id']}?"
                    )

                else:
                    if not {
                        "id", "status"
                    } <= row.keys():
                        continue

                    target = (
                        f"{segment}/{row['id']}"
                    )

                    label = {
                        "sales_orders": "sales order",
                        "purchase_orders": "purchase order",
                        "credit_return_notes": "credit return note",
                        "payroll": "payroll",
                        "tickets": "support ticket",
                    }[kind]

                    question = (
                        f"What is the status of "
                        f"{label} {row['id']}?"
                    )

                choices.append({
                    "question": question,
                    "kind": kind,
                    "target": (
                        "/api/v1/business/" + target
                    ),
                })

            secrets.SystemRandom().shuffle(choices)
            buckets.append(choices[:6])

        if not self.used:
            raise AccessDenied("DATA_ACCESS_DENIED")

        secrets.SystemRandom().shuffle(buckets)

        selected = [
            bucket[index]
            for index in range(6)
            for bucket in buckets
            if index < len(bucket)
        ]

        return self.finish({
            "suggestions": selected[:6],
        })

    def bi(self, area, filters):
        kind = AREAS[area]

        required = (
            frozenset({
                "item_id",
                "warehouse_id",
                "quantity_available",
            })
            if area == "stock"
            else frozenset()
        )

        items = self.filtered(
            self.records(
                kind,
                feature="bi_expert",
                action="summarize",
                fields=required,
            ),
            kind,
            filters,
        )

        rows = [
            item["record"] for item in items
        ]

        def number(value):
            try:
                result = Decimal(str(value))
                if not result.is_finite():
                    raise ValueError(
                        "Nonfinite number"
                    )
                return result

            except (ValueError, InvalidOperation):
                raise BusinessUnavailable(
                    "Invalid business quantity or amount"
                ) from None

        if area == "stock":
            required = {
                "item_id",
                "warehouse_id",
                "quantity_available",
            }

            if any(
                not required <= row.keys()
                for row in rows
            ):
                raise AccessDenied(
                    "FIELD_ACCESS_DENIED"
                )

            warehouses = defaultdict(
                lambda: [0, 0]
            )

            for row in rows:
                bucket = warehouses[
                    row["warehouse_id"]
                ]
                bucket[0] += 1
                bucket[1] += (
                    number(
                        row["quantity_available"]
                    ) <= 0
                )

            tables = {
                "warehouses": [
                    {
                        "id": key,
                        "label": key,
                        "count": values[0],
                        "unavailable": values[1],
                    }
                    for key, values
                    in sorted(warehouses.items())
                ],
            }

            metrics = [
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
                    "value": sum(
                        values[1]
                        for values
                        in warehouses.values()
                    ),
                    "unit": "rows",
                },
            ]

            units = defaultdict(
                lambda: Decimal(0)
            )

            if all(
                "unit" in item["details"]
                for item in items
            ):
                for item in items:
                    unit = item["details"]["unit"]

                    if (
                        not isinstance(unit, str)
                        or not unit.strip()
                    ):
                        raise BusinessUnavailable(
                            "Invalid stock unit"
                        )

                    units[unit] += number(
                        item["record"][
                            "quantity_available"
                        ]
                    )

            tables["units"] = [
                {
                    "label": key,
                    "available_quantity": str(value),
                }
                for key, value
                in sorted(units.items())
            ]

            labels = {
                item["record"]["warehouse_id"]:
                    item["details"].get(
                        "warehouse_name",
                        item["record"]["warehouse_id"],
                    )
                for item in items
            }

            for row in tables["warehouses"]:
                row["label"] = labels[row["id"]]

            monetary = False

        else:
            party_key = (
                "supplier_party_id"
                if area == "purchases"
                else "customer_party_id"
            )

            groups = {
                "status": defaultdict(list),
                "monthly": defaultdict(list),
                "parties": defaultdict(list),
            }

            monetary = bool(rows) and all(
                "total_amount_pkr" in row
                for row in rows
            )

            for row in rows:
                keys = (
                    ("status", row.get("status")),
                    (
                        "monthly",
                        row.get(
                            "order_date", ""
                        )[:7],
                    ),
                    ("parties", row.get(party_key)),
                )

                for group, key in keys:
                    if key:
                        groups[group][key].append(row)

            def entry(key, records):
                out = {
                    "id": key,
                    "label": key,
                    "count": len(records),
                }

                if monetary:
                    amount = sum(
                        (
                            number(
                                record[
                                    "total_amount_pkr"
                                ]
                            )
                            for record in records
                        ),
                        Decimal(0),
                    )

                    out["order_value_pkr"] = str(
                        amount.quantize(
                            Decimal("0.01")
                        )
                    )

                return out

            tables = {
                group: [
                    entry(key, records)
                    for key, records
                    in sorted(buckets.items())
                ]
                for group, buckets
                in groups.items()
            }

            labels = {
                item["record"][party_key]:
                    item["details"].get(
                        "party_name",
                        item["record"][party_key],
                    )
                for item in items
                if party_key in item["record"]
            }

            for row in tables["parties"]:
                row["label"] = labels[row["id"]]

            tables["parties"].sort(
                key=lambda row: (
                    (
                        -number(
                            row["order_value_pkr"]
                        )
                        if monetary
                        else -row["count"]
                    ),
                    row["id"],
                )
            )

            tables["parties"] = (
                tables["parties"][:5]
            )

            metrics = [{
                "label": "Matching orders",
                "value": len(rows),
                "unit": "orders",
            }]

            if monetary:
                total = sum(
                    (
                        number(
                            row["total_amount_pkr"]
                        )
                        for row in rows
                    ),
                    Decimal(0),
                )

                metrics += [
                    {
                        "label": "Total order value",
                        "value": str(
                            total.quantize(
                                Decimal("0.01")
                            )
                        ),
                        "unit": "PKR",
                    },
                    {
                        "label": "Average order value",
                        "value": str(
                            (
                                total / len(rows)
                            ).quantize(
                                Decimal("0.01")
                            )
                        ),
                        "unit": "PKR",
                    },
                ]

        return self.finish({
            "area": area,
            "record_count": len(rows),
            "metrics": metrics,
            "tables": tables,
            "financial_values_included": monetary,
            "filters": filters,
            "note": (
                "Only permitted records and fields "
                "are used. Order values are not "
                "recognized revenue, payments or profit."
            ),
        })

    def bi_suggestions(self):
        selected = []
        areas = []

        for area in AREAS:
            try:
                report = self.bi(area, {})
            except AccessDenied:
                continue

            areas.append(area)

            if not report["record_count"]:
                continue

            choices = [
                (
                    f"Summarize my permitted {area}",
                    "summary",
                )
            ]

            if area == "stock":
                choices.append((
                    "Show unavailable stock by warehouse",
                    "warehouses",
                ))

                if report["tables"]["units"]:
                    choices.append((
                        "Show permitted quantities by unit",
                        "units",
                    ))

                for row in report["tables"]["warehouses"]:
                    selected.append({
                        "question": (
                            "Summarize stock in "
                            + row["id"]
                        ),
                        "area": area,
                        "view": "summary",
                        "filters": {
                            "warehouse_id": row["id"],
                        },
                    })

            else:
                label = (
                    "order values"
                    if report["financial_values_included"]
                    else "order counts"
                )

                choices += [
                    (
                        f"Show {area} {label} by month",
                        "monthly",
                    ),
                    (
                        f"Show {area} orders by status",
                        "status",
                    ),
                    (
                        f"Show top parties by {label}",
                        "parties",
                    ),
                ]

                for row in report["tables"]["parties"]:
                    selected.append({
                        "question": (
                            f"Summarize {area} orders "
                            f"for {row['id']}"
                        ),
                        "area": area,
                        "view": "summary",
                        "filters": {
                            "party_id": row["id"],
                        },
                    })

            selected += [
                {
                    "question": question,
                    "area": area,
                    "view": view,
                }
                for question, view in choices
            ]

        if not areas:
            raise AccessDenied(
                "DATA_ACCESS_DENIED"
            )

        secrets.SystemRandom().shuffle(selected)

        return self.finish({
            "suggestions": selected[:6],
            "available_areas": areas,
        })