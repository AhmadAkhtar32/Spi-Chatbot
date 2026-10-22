"""Business-data boundary. Only the fictional JSON provider exists today."""

import os
import secrets
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Protocol

from demo_policy import AccessDenied, authorize_record, load_demo_data


Identity = tuple[dict, str]

KINDS = {
    "stock",
    "sales_orders",
    "purchase_orders",
    "credit_return_notes",
    "payroll",
    "tickets",
}


class DataSourceUnavailable(RuntimeError):
    """The selected source is unavailable."""


@dataclass(frozen=True)
class BusinessRecord:
    record: dict
    details: dict
    source: str
    snapshot_at: str | None


@dataclass(frozen=True)
class BusinessPage:
    items: list[dict]
    total: int
    limit: int
    offset: int
    has_more: bool
    source: str
    snapshot_at: str | None


class BusinessDataProvider(Protocol):
    """Providers must return only authorized records and bounded pages."""

    def metadata(self) -> dict:
        ...

    def get_record(
        self,
        identity: Identity,
        kind: str,
        record_id: str,
        warehouse_id: str | None = None,
    ) -> BusinessRecord | None:
        ...

    def get_candidates(
        self,
        identity: Identity,
        kind: str,
        limit: int = 6,
    ) -> list[dict]:
        ...

    def search_stock(
        self,
        identity: Identity,
        *,
        q: str = "",
        warehouse_id: str | None = None,
        in_stock_only: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> BusinessPage:
        ...

    def search_orders(
        self,
        identity: Identity,
        kind: str,
        *,
        q: str = "",
        party_id: str | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> BusinessPage:
        ...


class DemoJsonProvider:
    """Read the existing cached snapshot without regenerating it."""

    def __init__(self) -> None:
        try:
            data = load_demo_data()
            collections = KINDS | {"items", "warehouses", "parties"}

            if (
                not isinstance(data, dict)
                or not isinstance(data.get("snapshot_at"), str)
            ):
                raise ValueError("Invalid snapshot metadata")

            for name in collections:
                rows = data.get(name)
                if not isinstance(rows, list) or any(
                    not isinstance(row, dict) for row in rows
                ):
                    raise ValueError("Invalid snapshot collection")

        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise DataSourceUnavailable(
                "Demo data could not be loaded"
            ) from exc

        self._data = data

    def metadata(self) -> dict:
        return {
            "source": "fictional_demo_snapshot",
            "snapshot_at": self._data["snapshot_at"],
        }

    def _rows(self, kind: str) -> list[dict]:
        if kind not in KINDS:
            raise DataSourceUnavailable(
                "Unsupported business record type"
            )
        return self._data[kind]

    @staticmethod
    def _visible(
        identity: Identity,
        kind: str,
        record: dict,
    ) -> bool:
        try:
            authorize_record(
                identity[0], identity[1], kind, record
            )
            return True
        except AccessDenied:
            return False

    def _details(self, kind: str, record: dict) -> dict:
        if kind == "stock":
            item = next(
                (
                    row
                    for row in self._data["items"]
                    if row.get("id") == record.get("item_id")
                ),
                {},
            )

            warehouse = next(
                (
                    row
                    for row in self._data["warehouses"]
                    if row.get("id") == record.get("warehouse_id")
                ),
                {},
            )

            return {
                "item_name": item.get("name"),
                "unit": item.get("unit"),
                "warehouse_name": warehouse.get("name"),
            }

        if kind in {
            "sales_orders",
            "purchase_orders",
            "credit_return_notes",
        }:
            supplier = kind == "purchase_orders"
            key = (
                "supplier_party_id"
                if supplier
                else "customer_party_id"
            )

            party = next(
                (
                    row
                    for row in self._data["parties"]
                    if row.get("id") == record.get(key)
                ),
                {},
            )

            return {
                "party_name": party.get("name"),
                "party_role": (
                    "supplier" if supplier else "customer"
                ),
            }

        return {}

    def get_record(
        self,
        identity: Identity,
        kind: str,
        record_id: str,
        warehouse_id: str | None = None,
    ) -> BusinessRecord | None:
        for record in self._rows(kind):
            if kind == "stock":
                matches = (
                    record.get("item_id") == record_id
                    and record.get("warehouse_id") == warehouse_id
                )
            else:
                matches = record.get("id") == record_id

            if matches and self._visible(identity, kind, record):
                return BusinessRecord(
                    record=deepcopy(record),
                    details=self._details(kind, record),
                    **self.metadata(),
                )

        return None

    def get_candidates(
        self,
        identity: Identity,
        kind: str,
        limit: int = 6,
    ) -> list[dict]:
        if not 1 <= limit <= 6:
            raise ValueError(
                "Candidate limit must be between 1 and 6"
            )

        visible = [
            record
            for record in self._rows(kind)
            if self._visible(identity, kind, record)
        ]

        selected = secrets.SystemRandom().sample(
            visible, min(limit, len(visible))
        )
        return deepcopy(selected)

    def search_stock(
        self,
        identity: Identity,
        *,
        q: str = "",
        warehouse_id: str | None = None,
        in_stock_only: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> BusinessPage:
        if not 1 <= limit <= 100 or offset < 0 or len(q) > 100:
            raise ValueError("Invalid stock search parameters")

        needle = q.strip().casefold()
        matches: list[dict] = []

        for record in self._rows("stock"):
            if not self._visible(identity, "stock", record):
                continue

            if (
                warehouse_id is not None
                and record.get("warehouse_id") != warehouse_id
            ):
                continue

            if (
                in_stock_only
                and record.get("quantity_available", 0) <= 0
            ):
                continue

            details = self._details("stock", record)

            if needle and not any(
                needle in str(value or "").casefold()
                for value in (
                    record.get("item_id"),
                    details.get("item_name"),
                )
            ):
                continue

            matches.append({
                "record": record,
                "details": details,
            })

        matches.sort(
            key=lambda item: (
                item["record"]["item_id"],
                item["record"]["warehouse_id"],
            )
        )

        total = len(matches)
        items = deepcopy(matches[offset:offset + limit])

        return BusinessPage(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=offset + len(items) < total,
            **self.metadata(),
        )

    def search_orders(
        self,
        identity: Identity,
        kind: str,
        *,
        q: str = "",
        party_id: str | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> BusinessPage:
        if kind not in {"sales_orders", "purchase_orders"}:
            raise DataSourceUnavailable(
                "Unsupported order type"
            )

        if not 1 <= limit <= 100 or offset < 0 or len(q) > 100:
            raise ValueError("Invalid order search parameters")

        if date_from and date_to and date_from > date_to:
            raise ValueError(
                "date_from must not be after date_to"
            )

        party_key = (
            "supplier_party_id"
            if kind == "purchase_orders"
            else "customer_party_id"
        )

        needle = q.strip().casefold()
        wanted_status = (status or "").strip().casefold()
        matches: list[dict] = []

        for record in self._rows(kind):
            # Apply permissions before filtering or counting.
            if not self._visible(identity, kind, record):
                continue

            if (
                party_id is not None
                and record.get(party_key) != party_id
            ):
                continue

            if (
                wanted_status
                and str(record.get("status", "")).casefold()
                != wanted_status
            ):
                continue

            try:
                ordered = date.fromisoformat(
                    record["order_date"]
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise DataSourceUnavailable(
                    "Invalid order date in data source"
                ) from exc

            if date_from and ordered < date_from:
                continue

            if date_to and ordered > date_to:
                continue

            details = self._details(kind, record)

            if needle and not any(
                needle in str(value or "").casefold()
                for value in (
                    record.get("id"),
                    record.get(party_key),
                    record.get("item_id"),
                    details.get("party_name"),
                )
            ):
                continue

            matches.append({
                "record": record,
                "details": details,
            })

        matches.sort(
            key=lambda item: (
                item["record"]["order_date"],
                item["record"]["id"],
            ),
            reverse=True,
        )

        total = len(matches)
        items = deepcopy(matches[offset:offset + limit])

        return BusinessPage(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=offset + len(items) < total,
            **self.metadata(),
        )


@lru_cache(maxsize=1)
def _demo_provider() -> DemoJsonProvider:
    return DemoJsonProvider()


def get_business_provider() -> BusinessDataProvider:
    selected = os.environ.get(
        "BUSINESS_DATA_SOURCE", "demo_json"
    ).strip().lower()

    if selected != "demo_json":
        raise DataSourceUnavailable(
            "The selected business data source is not implemented"
        )

    if os.environ.get("ENABLE_DEMO_SESSIONS") != "1":
        raise DataSourceUnavailable(
            "The JSON source requires demo mode"
        )

    return _demo_provider()