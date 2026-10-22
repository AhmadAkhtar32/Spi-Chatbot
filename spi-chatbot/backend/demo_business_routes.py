"""Protected business endpoints using the demo data provider."""

import re
import secrets
from dataclasses import asdict
from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
)
from pydantic import BaseModel, Field, model_validator

from business_data_provider import (
    DataSourceUnavailable,
    get_business_provider,
)
from demo_policy import AccessDenied, authorize_record
from demo_routes import require_demo_identity


router = APIRouter(
    prefix="/api/demo/business",
    tags=["Demo business data"],
)

FEATURES = {
    "stock": ("inventory", "stock.read"),
    "sales_orders": ("sales", "sales_orders.read"),
    "purchase_orders": ("purchasing", "purchase_orders.read"),
    "credit_return_notes": ("sales", "sales_orders.read"),
    "tickets": (None, "tickets.read"),
    "payroll": ("payroll", None),
}


class OrderFilters(BaseModel):
    model_config = {"extra": "forbid"}

    q: str = Field(default="", max_length=100)

    party_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9-]+$",
    )

    status: str | None = Field(
        default=None,
        max_length=50,
    )

    date_from: date | None = None
    date_to: date | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.date_from
            and self.date_to
            and self.date_from > self.date_to
        ):
            raise ValueError(
                "date_from must not be after date_to"
            )
        return self


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

    if (
        module is not None
        and module not in user["module_licenses"]
    ):
        return False

    if (
        kind == "tickets"
        and "support_expert" not in user["experts"]
    ):
        return False

    if kind == "payroll":
        return bool(
            {"payroll.read", "payroll.read_self"}
            & set(user["permissions"])
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


def _require_feature(
    identity: tuple[dict, str],
    kind: str,
) -> None:
    if not _has_feature(identity[0], kind):
        _error(
            403,
            "This business feature is not available to your role",
        )


def _read_record(
    response: Response,
    identity: tuple[dict, str],
    kind: str,
    record_id: str,
    warehouse_id: str | None = None,
) -> dict:
    _require_feature(identity, kind)
    _id(record_id)

    if warehouse_id is not None:
        _id(warehouse_id)

    try:
        result = get_business_provider().get_record(
            identity, kind, record_id, warehouse_id
        )
    except DataSourceUnavailable:
        _error(
            503,
            "Business data source is not configured or unavailable",
        )

    if result is None or not _is_visible(
        identity, kind, result.record
    ):
        _error(404, "Record not found or unavailable")

    response.headers["Cache-Control"] = "no-store"
    return {"kind": kind, **asdict(result)}


def _page_response(
    response: Response,
    identity,
    kind: str,
    page,
    filters: dict,
):
    party_key = (
        "supplier_party_id"
        if kind == "purchase_orders"
        else "customer_party_id"
    )

    invalid = (
        page.limit != filters["limit"]
        or page.offset != filters["offset"]
        or page.total < len(page.items)
        or len(page.items) > filters["limit"]
        or page.has_more
        != (page.offset + len(page.items) < page.total)
    )

    for item in page.items:
        record = (
            item.get("record")
            if isinstance(item, dict)
            else None
        )

        if not _is_visible(identity, kind, record):
            invalid = True
            break

        if (
            filters.get("warehouse_id") is not None
            and record.get("warehouse_id")
            != filters["warehouse_id"]
        ):
            invalid = True

        if (
            filters.get("party_id") is not None
            and record.get(party_key) != filters["party_id"]
        ):
            invalid = True

    if invalid:
        _error(
            503,
            "Business data source returned an invalid page",
        )

    response.headers["Cache-Control"] = "no-store"

    return {
        "kind": kind,
        **asdict(page),
        "filters": filters,
    }


@router.get("/stock")
def search_stock(
    response: Response,
    identity: tuple[dict, str] = Depends(
        require_demo_identity
    ),
    q: str = Query(default="", max_length=100),
    warehouse_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9-]+$",
    ),
    in_stock_only: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    _require_feature(identity, "stock")
    q = q.strip()

    try:
        page = get_business_provider().search_stock(
            identity,
            q=q,
            warehouse_id=warehouse_id,
            in_stock_only=in_stock_only,
            limit=limit,
            offset=offset,
        )
    except DataSourceUnavailable:
        _error(
            503,
            "Business data source is not configured or unavailable",
        )

    filters = {
        "q": q,
        "warehouse_id": warehouse_id,
        "in_stock_only": in_stock_only,
        "limit": limit,
        "offset": offset,
    }

    result = _page_response(
        response, identity, "stock", page, filters
    )

    result["filters"] = {
        key: value
        for key, value in filters.items()
        if key not in {"limit", "offset"}
    }

    return result


def _search_orders(
    response: Response,
    identity,
    kind: str,
    filters: OrderFilters,
):
    _require_feature(identity, kind)

    values = filters.model_dump()
    values["q"] = values["q"].strip()
    values["status"] = (
        (values["status"] or "").strip() or None
    )

    try:
        page = get_business_provider().search_orders(
            identity, kind, **values
        )
    except DataSourceUnavailable:
        _error(
            503,
            "Business data source is not configured or unavailable",
        )

    return _page_response(
        response, identity, kind, page, values
    )


@router.get("/sales-orders")
def search_sales_orders(
    response: Response,
    filters: Annotated[OrderFilters, Query()],
    identity: tuple[dict, str] = Depends(
        require_demo_identity
    ),
):
    return _search_orders(
        response, identity, "sales_orders", filters
    )


@router.get("/purchase-orders")
def search_purchase_orders(
    response: Response,
    filters: Annotated[OrderFilters, Query()],
    identity: tuple[dict, str] = Depends(
        require_demo_identity
    ),
):
    return _search_orders(
        response, identity, "purchase_orders", filters
    )


@router.get("/stock/{item_id}/{warehouse_id}")
def get_stock(
    item_id: str,
    warehouse_id: str,
    response: Response,
    identity: tuple[dict, str] = Depends(
        require_demo_identity
    ),
):
    return _read_record(
        response, identity, "stock", item_id, warehouse_id
    )


@router.get("/sales-orders/{order_id}")
def get_sales_order(
    order_id: str,
    response: Response,
    identity: tuple[dict, str] = Depends(
        require_demo_identity
    ),
):
    return _read_record(
        response, identity, "sales_orders", order_id
    )


@router.get("/purchase-orders/{order_id}")
def get_purchase_order(
    order_id: str,
    response: Response,
    identity: tuple[dict, str] = Depends(
        require_demo_identity
    ),
):
    return _read_record(
        response, identity, "purchase_orders", order_id
    )


@router.get("/credit-return-notes/{note_id}")
def get_credit_return_note(
    note_id: str,
    response: Response,
    identity: tuple[dict, str] = Depends(
        require_demo_identity
    ),
):
    return _read_record(
        response, identity, "credit_return_notes", note_id
    )


@router.get("/payroll/{payroll_id}")
def get_payroll(
    payroll_id: str,
    response: Response,
    identity: tuple[dict, str] = Depends(
        require_demo_identity
    ),
):
    return _read_record(
        response, identity, "payroll", payroll_id
    )


@router.get("/tickets/{ticket_id}")
def get_ticket(
    ticket_id: str,
    response: Response,
    identity: tuple[dict, str] = Depends(
        require_demo_identity
    ),
):
    return _read_record(
        response, identity, "tickets", ticket_id
    )


def _question(kind: str, record: dict) -> str:
    if kind == "stock":
        return (
            f"What is the stock of {record['item_id']} "
            f"in {record['warehouse_id']}?"
        )

    if kind == "sales_orders":
        return (
            f"What is the status of sales order "
            f"{record['id']}?"
        )

    if kind == "purchase_orders":
        return (
            f"What is the status of purchase order "
            f"{record['id']}?"
        )

    if kind == "credit_return_notes":
        return (
            f"What is the status of credit return note "
            f"{record['id']}?"
        )

    if kind == "payroll":
        return (
            f"What is the payroll status for "
            f"{record['id']}?"
        )

    return (
        f"What is the status of support ticket "
        f"{record['id']}?"
    )


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
    identity: tuple[dict, str] = Depends(
        require_demo_identity
    ),
):
    """Build up to six suggestions from authorized records."""

    response.headers["Cache-Control"] = "no-store"
    rng = secrets.SystemRandom()
    buckets: list[list[dict]] = []

    try:
        provider = get_business_provider()
        metadata = provider.metadata()

        for kind in FEATURES:
            if not _has_feature(identity[0], kind):
                continue

            candidates = provider.get_candidates(
                identity, kind, limit=6
            )

            visible = [
                record
                for record in candidates
                if _is_visible(identity, kind, record)
            ]

            buckets.append([
                {
                    "question": _question(kind, record),
                    "kind": kind,
                    "target": _target(kind, record),
                }
                for record in visible[:6]
            ])

    except DataSourceUnavailable:
        _error(
            503,
            "Business data source is not configured or unavailable",
        )

    rng.shuffle(buckets)
    selected: list[dict] = []

    for index in range(6):
        for bucket in buckets:
            if len(bucket) > index:
                selected.append(bucket[index])

                if len(selected) == 6:
                    return {
                        "suggestions": selected,
                        **metadata,
                    }

    return {
        "suggestions": selected,
        **metadata,
    }

from demo_collection_routes import create_collection_router

router.include_router(
    create_collection_router(_require_feature, _page_response)
)

from demo_bi_routes import router as demo_bi_router

router.include_router(demo_bi_router)
