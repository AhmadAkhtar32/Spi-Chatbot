"""Protected business routes using a replaceable data provider.

These routes still use demo sessions. Production SPIA identity and the
live provider must be implemented before enabling real client data.
"""

import re
import secrets
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Response

from business_data_provider import DataSourceUnavailable, get_business_provider
from demo_policy import AccessDenied, authorize_record
from demo_routes import require_demo_identity


router = APIRouter(prefix="/api/demo/business", tags=["Demo business data"])

# Public module names and permissions are checked before looking up an ID.
# The existing authorize_record function then checks the individual record.
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
        return bool({"payroll.read", "payroll.read_self"} & set(user["permissions"]))
    return permission in user["permissions"]


def _is_visible(identity: tuple[dict, str], kind: str, record: dict) -> bool:
    user, surface = identity
    try:
        authorize_record(user, surface, kind, record)
        return True
    except AccessDenied:
        return False


def _require_feature(identity: tuple[dict, str], kind: str) -> None:
    if not _has_feature(identity[0], kind):
        _error(403, "This business feature is not available to your role")


def _read_record(
    response: Response, identity: tuple[dict, str], kind: str, record_id: str,
    warehouse_id: str | None = None,
) -> dict:
    _require_feature(identity, kind)
    _id(record_id)
    if warehouse_id is not None:
        _id(warehouse_id)

    try:
        result = get_business_provider().get_record(identity, kind, record_id, warehouse_id)
    except DataSourceUnavailable:
        _error(503, "Business data source is not configured or unavailable")

    # Recheck row permissions even if a future provider returns too much.
    if result is None or not _is_visible(identity, kind, result.record):
        _error(404, "Record not found or unavailable")
    response.headers["Cache-Control"] = "no-store"
    return {"kind": kind, **asdict(result)}


@router.get("/stock/{item_id}/{warehouse_id}")
def get_stock(
    item_id: str, warehouse_id: str, response: Response,
    identity: tuple[dict, str] = Depends(require_demo_identity),
):
    return _read_record(response, identity, "stock", item_id, warehouse_id)


@router.get("/sales-orders/{order_id}")
def get_sales_order(
    order_id: str, response: Response,
    identity: tuple[dict, str] = Depends(require_demo_identity),
):
    return _read_record(response, identity, "sales_orders", order_id)


@router.get("/purchase-orders/{order_id}")
def get_purchase_order(
    order_id: str, response: Response,
    identity: tuple[dict, str] = Depends(require_demo_identity),
):
    return _read_record(response, identity, "purchase_orders", order_id)


@router.get("/credit-return-notes/{note_id}")
def get_credit_return_note(
    note_id: str, response: Response,
    identity: tuple[dict, str] = Depends(require_demo_identity),
):
    return _read_record(response, identity, "credit_return_notes", note_id)


@router.get("/payroll/{payroll_id}")
def get_payroll(
    payroll_id: str, response: Response,
    identity: tuple[dict, str] = Depends(require_demo_identity),
):
    return _read_record(response, identity, "payroll", payroll_id)


@router.get("/tickets/{ticket_id}")
def get_ticket(
    ticket_id: str, response: Response,
    identity: tuple[dict, str] = Depends(require_demo_identity),
):
    return _read_record(response, identity, "tickets", ticket_id)


def _question(kind: str, record: dict) -> str:
    if kind == "stock":
        return f"What is the stock of {record['item_id']} in {record['warehouse_id']}?"
    if kind == "sales_orders":
        return f"What is the status of sales order {record['id']}?"
    if kind == "purchase_orders":
        return f"What is the status of purchase order {record['id']}?"
    if kind == "credit_return_notes":
        return f"What is the status of credit return note {record['id']}?"
    if kind == "payroll":
        return f"What is the payroll status for {record['id']}?"
    return f"What is the status of support ticket {record['id']}?"


def _target(kind: str, record: dict) -> str:
    if kind == "stock":
        return f"/api/demo/business/stock/{record['item_id']}/{record['warehouse_id']}"
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
    """Up to six prompts from authorized source records; never persisted."""
    response.headers["Cache-Control"] = "no-store"
    rng = secrets.SystemRandom()
    buckets: list[list[dict]] = []
    try:
        provider = get_business_provider()
        metadata = provider.metadata()
        for kind in FEATURES:
            if not _has_feature(identity[0], kind):
                continue
            candidates = provider.get_candidates(identity, kind, limit=6)
            visible = [r for r in candidates if _is_visible(identity, kind, r)]
            buckets.append([
                {"question": _question(kind, record), "kind": kind,
                 "target": _target(kind, record)}
                for record in visible[:6]
            ])
    except DataSourceUnavailable:
        _error(503, "Business data source is not configured or unavailable")

    rng.shuffle(buckets)
    selected: list[dict] = []
    for index in range(6):
        for bucket in buckets:
            if len(bucket) > index:
                selected.append(bucket[index])
                if len(selected) == 6:
                    return {"suggestions": selected, **metadata}
    return {"suggestions": selected, **metadata}