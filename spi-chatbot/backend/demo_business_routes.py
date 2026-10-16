"""Read-only, role-scoped business APIs for the fictional SPIA demo.

Replace the data source with SPIA-approved APIs after the demo. Keep the
server-side session, feature, and record checks in front of that source.
"""

import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response

from demo_policy import AccessDenied, authorize_record, load_demo_data
from demo_routes import require_demo_identity


router = APIRouter(prefix="/api/demo/business", tags=["Demo business data"])
SOURCE = "fictional_demo_snapshot"

# Check the module and permission before looking up a record.
# authorize_record then checks access to that particular record.
FEATURES = {
    "stock": ("inventory", "stock.read"),
    "sales_orders": ("sales", "sales_orders.read"),
    "purchase_orders": ("purchasing", "purchase_orders.read"),
    "credit_return_notes": ("sales", "sales_orders.read"),
    "tickets": (None, "tickets.read"),
    "payroll": ("payroll", None),
}


def _error(status: int, detail: str) -> None:
    raise HTTPException(
        status_code=status,
        detail=detail,
        headers={"Cache-Control": "no-store"},
    )


def _id(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9-]{1,64}", value) is None:
        _error(404, "Record not found or unavailable")
    return value


def _has_feature(user: dict, kind: str) -> bool:
    module, permission = FEATURES[kind]

    if module is not None and module not in user["module_licenses"]:
        return False

    if kind == "tickets" and "support_expert" not in user["experts"]:
        return False

    if kind == "payroll":
        return bool(
            {"payroll.read", "payroll.read_self"} & set(user["permissions"])
        )

    return permission in user["permissions"]


def _is_visible(
    identity: tuple[dict, str],
    kind: str,
    record: dict,
) -> bool:
    user, surface = identity

    try:
        authorize_record(user, surface, kind, record)
        return True
    except AccessDenied:
        return False


def _require_feature(identity: tuple[dict, str], kind: str) -> None:
    if not _has_feature(identity[0], kind):
        _error(
            403,
            "This business feature is not available to your role",
        )


def _find_visible(
    identity: tuple[dict, str],
    kind: str,
    record_id: str,
    warehouse_id: str | None = None,
) -> dict:
    _require_feature(identity, kind)
    _id(record_id)

    if warehouse_id is not None:
        _id(warehouse_id)

    for record in load_demo_data()[kind]:
        if kind == "stock":
            matches = (
                record["item_id"] == record_id
                and record["warehouse_id"] == warehouse_id
            )
        else:
            matches = record["id"] == record_id

        if matches and _is_visible(identity, kind, record):
            return record

    # An inaccessible record and a nonexistent record get the same answer.
    _error(404, "Record not found or unavailable")


def _details(kind: str, record: dict, data: dict) -> dict:
    """Add names only after access to the underlying record is approved."""
    if kind == "stock":
        item = next(
            (x for x in data["items"] if x["id"] == record["item_id"]),
            None,
        )
        warehouse = next(
            (
                x for x in data["warehouses"]
                if x["id"] == record["warehouse_id"]
            ),
            None,
        )
        return {
            "item_name": item["name"] if item else None,
            "unit": item["unit"] if item else None,
            "warehouse_name": warehouse["name"] if warehouse else None,
        }

    if kind in {
        "sales_orders",
        "purchase_orders",
        "credit_return_notes",
    }:
        party_key = (
            "supplier_party_id"
            if kind == "purchase_orders"
            else "customer_party_id"
        )
        party = next(
            (x for x in data["parties"] if x["id"] == record[party_key]),
            None,
        )
        return {
            "party_name": party["name"] if party else None,
            "party_role": (
                "supplier"
                if kind == "purchase_orders"
                else "customer"
            ),
        }

    return {}


def _response(kind: str, record: dict, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    data = load_demo_data()

    return {
        "kind": kind,
        "record": record,
        "details": _details(kind, record, data),
        "source": SOURCE,
        "snapshot_at": data["snapshot_at"],
    }


@router.get("/stock/{item_id}/{warehouse_id}")
def get_stock(
    item_id: str,
    warehouse_id: str,
    response: Response,
    identity: tuple[dict, str] = Depends(require_demo_identity),
):
    record = _find_visible(
        identity,
        "stock",
        item_id,
        warehouse_id,
    )
    return _response("stock", record, response)


@router.get("/sales-orders/{order_id}")
def get_sales_order(
    order_id: str,
    response: Response,
    identity: tuple[dict, str] = Depends(require_demo_identity),
):
    record = _find_visible(identity, "sales_orders", order_id)
    return _response("sales_orders", record, response)


@router.get("/purchase-orders/{order_id}")
def get_purchase_order(
    order_id: str,
    response: Response,
    identity: tuple[dict, str] = Depends(require_demo_identity),
):
    record = _find_visible(identity, "purchase_orders", order_id)
    return _response("purchase_orders", record, response)


@router.get("/credit-return-notes/{note_id}")
def get_credit_return_note(
    note_id: str,
    response: Response,
    identity: tuple[dict, str] = Depends(require_demo_identity),
):
    record = _find_visible(
        identity,
        "credit_return_notes",
        note_id,
    )
    return _response("credit_return_notes", record, response)


@router.get("/payroll/{payroll_id}")
def get_payroll(
    payroll_id: str,
    response: Response,
    identity: tuple[dict, str] = Depends(require_demo_identity),
):
    record = _find_visible(identity, "payroll", payroll_id)
    return _response("payroll", record, response)


@router.get("/tickets/{ticket_id}")
def get_ticket(
    ticket_id: str,
    response: Response,
    identity: tuple[dict, str] = Depends(require_demo_identity),
):
    record = _find_visible(identity, "tickets", ticket_id)
    return _response("tickets", record, response)


def _question(kind: str, record: dict) -> str:
    if kind == "stock":
        return (
            f"What is the stock of {record['item_id']} "
            f"in {record['warehouse_id']}?"
        )

    if kind == "sales_orders":
        return f"What is the status of sales order {record['id']}?"

    if kind == "purchase_orders":
        return f"What is the status of purchase order {record['id']}?"

    if kind == "credit_return_notes":
        return (
            f"What is the status of credit return note "
            f"{record['id']}?"
        )

    if kind == "payroll":
        return f"What is the payroll status for {record['id']}?"

    return f"What is the status of support ticket {record['id']}?"


def _target(kind: str, record: dict) -> str:
    if kind == "stock":
        return (
            f"/api/demo/business/stock/"
            f"{record['item_id']}/{record['warehouse_id']}"
        )

    segment = {
        "sales_orders": "sales-orders",
        "purchase_orders": "purchase-orders",
        "credit_return_notes": "credit-return-notes",
        "payroll": "payroll",
        "tickets": "tickets",
    }[kind]

    return f"/api/demo/business/{segment}/{record['id']}"


@router.get("/suggestions")
def get_business_suggestions(
    response: Response,
    identity: tuple[dict, str] = Depends(require_demo_identity),
):
    """Choose up to six questions from records this user can read."""
    response.headers["Cache-Control"] = "no-store"
    data = load_demo_data()
    rng = secrets.SystemRandom()
    buckets: list[list[dict]] = []

    for kind in FEATURES:
        if not _has_feature(identity[0], kind):
            continue

        visible = [
            record
            for record in data[kind]
            if _is_visible(identity, kind, record)
        ]
        rng.shuffle(visible)

        buckets.append([
            {
                "question": _question(kind, record),
                "kind": kind,
                "target": _target(kind, record),
            }
            for record in visible[:6]
        ])

    rng.shuffle(buckets)
    selected: list[dict] = []

    # Take questions from different permitted areas when possible.
    for index in range(6):
        for bucket in buckets:
            if len(bucket) > index:
                selected.append(bucket[index])

                if len(selected) == 6:
                    return {
                        "suggestions": selected,
                        "source": SOURCE,
                        "snapshot_at": data["snapshot_at"],
                    }

    return {
        "suggestions": selected,
        "source": SOURCE,
        "snapshot_at": data["snapshot_at"],
    }