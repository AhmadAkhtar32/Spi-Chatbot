"""Business-data boundary. Only the fictional JSON provider exists today."""

import os
import secrets
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from demo_policy import AccessDenied, authorize_record, load_demo_data


Identity = tuple[dict, str]
KINDS = {
    "stock", "sales_orders", "purchase_orders",
    "credit_return_notes", "payroll", "tickets",
}


class DataSourceUnavailable(RuntimeError):
    """The selected source is unavailable; never fall back to sample data."""


@dataclass(frozen=True)
class BusinessRecord:
    record: dict
    details: dict
    source: str
    snapshot_at: str | None


class BusinessDataProvider(Protocol):
    """A future SPIA provider must return only authorized, bounded results.

    Identity comes from a verified server session. A live provider must
    translate that identity to SPIA's agreed authorization mechanism.
    """

    def metadata(self) -> dict:
        ...

    def get_record(
        self, identity: Identity, kind: str, record_id: str,
        warehouse_id: str | None = None,
    ) -> BusinessRecord | None:
        ...

    def get_candidates(
        self, identity: Identity, kind: str, limit: int = 6,
    ) -> list[dict]:
        ...


class DemoJsonProvider:
    """Read the existing cached snapshot; never regenerate the JSON file."""

    def __init__(self) -> None:
        try:
            data = load_demo_data()
            collections = KINDS | {"items", "warehouses", "parties"}
            if not isinstance(data, dict) or not isinstance(data.get("snapshot_at"), str):
                raise ValueError("Invalid snapshot metadata")
            for name in collections:
                rows = data.get(name)
                if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                    raise ValueError("Invalid snapshot collection")
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise DataSourceUnavailable("Demo data could not be loaded") from exc
        self._data = data

    def metadata(self) -> dict:
        return {
            "source": "fictional_demo_snapshot",
            "snapshot_at": self._data["snapshot_at"],
        }

    def _rows(self, kind: str) -> list[dict]:
        if kind not in KINDS:
            raise DataSourceUnavailable("Unsupported business record type")
        return self._data[kind]

    @staticmethod
    def _visible(identity: Identity, kind: str, record: dict) -> bool:
        try:
            authorize_record(identity[0], identity[1], kind, record)
            return True
        except AccessDenied:
            return False

    def _details(self, kind: str, record: dict) -> dict:
        if kind == "stock":
            item = next(
                (r for r in self._data["items"] if r.get("id") == record.get("item_id")), {}
            )
            warehouse = next(
                (r for r in self._data["warehouses"] if r.get("id") == record.get("warehouse_id")), {}
            )
            return {
                "item_name": item.get("name"),
                "unit": item.get("unit"),
                "warehouse_name": warehouse.get("name"),
            }
        if kind in {"sales_orders", "purchase_orders", "credit_return_notes"}:
            supplier = kind == "purchase_orders"
            key = "supplier_party_id" if supplier else "customer_party_id"
            party = next(
                (r for r in self._data["parties"] if r.get("id") == record.get(key)), {}
            )
            return {
                "party_name": party.get("name"),
                "party_role": "supplier" if supplier else "customer",
            }
        return {}

    def get_record(
        self, identity: Identity, kind: str, record_id: str,
        warehouse_id: str | None = None,
    ) -> BusinessRecord | None:
        for record in self._rows(kind):
            matches = (
                record.get("item_id") == record_id
                and record.get("warehouse_id") == warehouse_id
            ) if kind == "stock" else record.get("id") == record_id
            if matches and self._visible(identity, kind, record):
                return BusinessRecord(
                    record=deepcopy(record),
                    details=self._details(kind, record),
                    **self.metadata(),
                )
        return None

    def get_candidates(
        self, identity: Identity, kind: str, limit: int = 6,
    ) -> list[dict]:
        if not 1 <= limit <= 6:
            raise ValueError("Candidate limit must be between 1 and 6")
        visible = [r for r in self._rows(kind) if self._visible(identity, kind, r)]
        selected = secrets.SystemRandom().sample(visible, min(limit, len(visible)))
        return deepcopy(selected)


@lru_cache(maxsize=1)
def _demo_provider() -> DemoJsonProvider:
    return DemoJsonProvider()


def get_business_provider() -> BusinessDataProvider:
    """Read server configuration only. Live SPIA access is not implemented."""
    selected = os.environ.get("BUSINESS_DATA_SOURCE", "demo_json").strip().lower()
    if selected != "demo_json":
        raise DataSourceUnavailable("The selected business data source is not implemented")
    if os.environ.get("ENABLE_DEMO_SESSIONS") != "1":
        raise DataSourceUnavailable("The JSON source requires demo mode")
    return _demo_provider()