"""Scoped searches for demo payroll, tickets and credit-return notes."""

import os
from copy import deepcopy
from datetime import date
from functools import lru_cache

from business_data_provider import (
    BusinessPage,
    DataSourceUnavailable,
    DemoJsonProvider,
    Identity,
)


COLLECTIONS = {
    "payroll",
    "tickets",
    "credit_return_notes",
}


class DemoCollectionProvider(DemoJsonProvider):
    """Reuse the JSON provider and its record access checks."""

    def __init__(self):
        super().__init__()

        employees = self._data.get("employees")
        if not isinstance(employees, list) or any(
            not isinstance(row, dict) for row in employees
        ):
            raise DataSourceUnavailable(
                "Invalid employee collection"
            )

        self._employees = {
            row.get("id"): row for row in employees
        }

        self._parties = {
            row.get("id"): row
            for row in self._data["parties"]
        }

    def _search_details(self, kind, record):
        if kind == "payroll":
            employee = self._employees.get(
                record.get("employee_id"), {}
            )
            return {
                "employee_name": employee.get("name"),
            }

        key = (
            "party_id"
            if kind == "tickets"
            else "customer_party_id"
        )

        party = self._parties.get(record.get(key), {})
        details = {"party_name": party.get("name")}

        if kind == "credit_return_notes":
            details["party_role"] = "customer"

        return details

    @staticmethod
    def _record_date(kind, record):
        try:
            if kind == "payroll":
                return date.fromisoformat(
                    record["period"] + "-01"
                )

            key = (
                "created_at"
                if kind == "tickets"
                else "date"
            )
            return date.fromisoformat(record[key])

        except (KeyError, TypeError, ValueError) as exc:
            raise DataSourceUnavailable(
                "Invalid source record date"
            ) from exc

    def search_collection(
        self,
        identity: Identity,
        kind: str,
        *,
        q: str = "",
        status: str | None = None,
        employee_id: str | None = None,
        period: str | None = None,
        module: str | None = None,
        party_id: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> BusinessPage:
        if kind not in COLLECTIONS:
            raise DataSourceUnavailable(
                "Unsupported collection"
            )

        if (
            not 1 <= limit <= 100
            or offset < 0
            or len(q) > 100
        ):
            raise ValueError(
                "Invalid collection search parameters"
            )

        if date_from and date_to and date_from > date_to:
            raise ValueError(
                "date_from must not be after date_to"
            )

        needle = q.strip().casefold()
        wanted_status = (status or "").strip().casefold()
        matches = []

        for record in self._rows(kind):
            # Permissions apply before filtering and counting.
            if not self._visible(identity, kind, record):
                continue

            if (
                employee_id is not None
                and record.get("employee_id") != employee_id
            ):
                continue

            if (
                period is not None
                and record.get("period") != period
            ):
                continue

            if (
                module is not None
                and record.get("module") != module
            ):
                continue

            if (
                party_id is not None
                and record.get("customer_party_id") != party_id
            ):
                continue

            if (
                wanted_status
                and str(record.get("status", "")).casefold()
                != wanted_status
            ):
                continue

            recorded = self._record_date(kind, record)

            if date_from and recorded < date_from:
                continue

            if date_to and recorded > date_to:
                continue

            details = self._search_details(kind, record)

            if kind == "payroll":
                fields = (
                    record.get("id"),
                    record.get("employee_id"),
                    record.get("period"),
                    details.get("employee_name"),
                )

            elif kind == "tickets":
                fields = (
                    record.get("id"),
                    record.get("subject"),
                    record.get("module"),
                    record.get("party_id"),
                    details.get("party_name"),
                )

            else:
                fields = (
                    record.get("id"),
                    record.get("sales_order_id"),
                    record.get("item_id"),
                    record.get("customer_party_id"),
                    record.get("reason"),
                    details.get("party_name"),
                )

            if needle and not any(
                needle in str(value or "").casefold()
                for value in fields
            ):
                continue

            matches.append((
                recorded,
                {
                    "record": record,
                    "details": details,
                },
            ))

        matches.sort(
            key=lambda entry: (
                entry[0],
                entry[1]["record"]["id"],
            ),
            reverse=True,
        )

        total = len(matches)

        items = deepcopy([
            entry[1]
            for entry in matches[offset:offset + limit]
        ])

        return BusinessPage(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=offset + len(items) < total,
            **self.metadata(),
        )


@lru_cache(maxsize=1)
def _demo_collection_provider():
    return DemoCollectionProvider()


def get_collection_provider():
    selected = os.environ.get(
        "BUSINESS_DATA_SOURCE", "demo_json"
    ).strip().lower()

    if selected != "demo_json":
        raise DataSourceUnavailable(
            "Selected collection source is not implemented"
        )

    if os.environ.get("ENABLE_DEMO_SESSIONS") != "1":
        raise DataSourceUnavailable(
            "The JSON source requires demo mode"
        )

    return _demo_collection_provider()