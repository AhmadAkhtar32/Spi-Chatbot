"""Business APIs using signed licenses and server-side record/field rules."""

import re
from datetime import date
from typing import Annotated, Literal

from fastapi import (
    APIRouter, Depends, HTTPException, Query, Response,
)
from pydantic import (
    BaseModel, ConfigDict, Field, model_validator,
)

from spia.security.access_control import AccessDenied
from spia.api.access import require_access_context
from spia.services.business import (
    BusinessService, BusinessUnavailable, SEGMENTS,
)
from spia.security.store import SecurityConfigurationError

router = APIRouter(
    prefix="/api/v1/business",
    tags=["Business data"],
)

bi_router = APIRouter(
    prefix="/bi",
    tags=["BI expert"],
)

KINDS = {
    segment: kind
    for kind, segment in SEGMENTS.items()
}

ID = r"^[A-Za-z0-9-]{1,64}$"


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str = Field(default="", max_length=100)
    fields: str | None = Field(
        default=None, max_length=500
    )
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class StockFilters(Filters):
    warehouse_id: str | None = Field(
        default=None, pattern=ID
    )
    in_stock_only: bool = False


class DatedFilters(Filters):
    status: str | None = Field(
        default=None, max_length=50
    )
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def dates(self):
        if (
            self.date_from
            and self.date_to
            and self.date_from > self.date_to
        ):
            raise ValueError("Invalid date range")
        return self


class OrderFilters(DatedFilters):
    party_id: str | None = Field(
        default=None, pattern=ID
    )


class TicketFilters(DatedFilters):
    module: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_-]{1,64}$",
    )


class PayrollFilters(Filters):
    status: str | None = Field(
        default=None, max_length=50
    )
    employee_id: str | None = Field(
        default=None, pattern=ID
    )
    period: str | None = Field(
        default=None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    )

    @model_validator(mode="after")
    def valid_period(self):
        if self.period:
            date.fromisoformat(
                self.period + "-01"
            )
        return self


class BIFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area: Literal[
        "sales", "purchases", "stock"
    ] = "sales"

    status: str | None = Field(
        default=None, max_length=50
    )
    party_id: str | None = Field(
        default=None, pattern=ID
    )
    warehouse_id: str | None = Field(
        default=None, pattern=ID
    )
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def dates(self):
        if (
            self.date_from
            and self.date_to
            and self.date_from > self.date_to
        ):
            raise ValueError("Invalid date range")

        if self.area == "stock" and any(
            value is not None
            for value in (
                self.status,
                self.party_id,
                self.date_from,
                self.date_to,
            )
        ):
            raise ValueError(
                "Stock supports warehouse filtering only"
            )

        if (
            self.area != "stock"
            and self.warehouse_id is not None
        ):
            raise ValueError(
                "Warehouse filtering applies to stock only"
            )

        return self


def run(response, operation):
    response.headers["Cache-Control"] = "no-store"

    try:
        return operation()

    except AccessDenied as exc:
        raise HTTPException(
            403,
            exc.code,
            headers={"Cache-Control": "no-store"},
        ) from None

    except (
        BusinessUnavailable,
        SecurityConfigurationError,
        ArithmeticError,
    ):
        raise HTTPException(
            503,
            "Business data or security configuration is unavailable",
            headers={"Cache-Control": "no-store"},
        ) from None


def requested(value):
    fields = frozenset(
        item.strip()
        for item in (value or "").split(",")
        if item.strip()
    )

    if any(
        re.fullmatch(
            r"[A-Za-z0-9_]{1,128}", item
        ) is None
        for item in fields
    ):
        raise HTTPException(
            422, "Invalid requested field"
        )

    return fields


@router.get("/suggestions")
def suggestions(
    response: Response,
    context=Depends(require_access_context),
):
    return run(
        response,
        lambda: BusinessService(
            context
        ).suggestions(),
    )


@bi_router.get("/summary")
def bi_summary(
    response: Response,
    filters: Annotated[BIFilters, Query()],
    context=Depends(require_access_context),
):
    values = filters.model_dump(
        exclude={"area"}
    )

    return run(
        response,
        lambda: BusinessService(context).bi(
            filters.area,
            values,
        ),
    )


@bi_router.get("/suggestions")
def bi_suggestions(
    response: Response,
    context=Depends(require_access_context),
):
    return run(
        response,
        lambda: BusinessService(
            context
        ).bi_suggestions(),
    )


router.include_router(bi_router)


@router.get("/stock/{item_id}/{warehouse_id}")
def stock_detail(
    item_id: str,
    warehouse_id: str,
    response: Response,
    context=Depends(require_access_context),
    fields: str | None = Query(
        default=None, max_length=500
    ),
):
    return detail(
        "stock",
        item_id,
        warehouse_id,
        response,
        context,
        fields,
    )


def detail(
    kind,
    record_id,
    warehouse,
    response,
    context,
    fields,
):
    if any(
        re.fullmatch(ID, value) is None
        for value in (record_id, warehouse)
        if value is not None
    ):
        raise HTTPException(
            404,
            "Record not found or unavailable",
        )

    selected = requested(fields)

    result = run(
        response,
        lambda: BusinessService(context).detail(
            kind,
            record_id,
            warehouse,
            selected,
        ),
    )

    if result is None:
        raise HTTPException(
            404,
            "Record not found or unavailable",
            headers={"Cache-Control": "no-store"},
        )

    return result


def search(kind, response, filters, context):
    values = filters.model_dump(
        exclude_unset=True
    )

    selected = requested(
        values.pop("fields", None)
    )

    values.setdefault("limit", filters.limit)
    values.setdefault("offset", filters.offset)

    if values.get("status"):
        values["status"] = values["status"].strip()

    return run(
        response,
        lambda: BusinessService(context).search(
            kind,
            values,
            selected,
        ),
    )


def collection_endpoint(kind):
    model = {
        "stock": StockFilters,
        "payroll": PayrollFilters,
        "tickets": TicketFilters,
    }.get(kind, OrderFilters)

    def endpoint(
        response: Response,
        filters: Annotated[model, Query()],
        context=Depends(require_access_context),
    ):
        return search(
            kind,
            response,
            filters,
            context,
        )

    return endpoint


def detail_endpoint(kind):
    def endpoint(
        record_id: str,
        response: Response,
        context=Depends(require_access_context),
        fields: str | None = Query(
            default=None, max_length=500
        ),
    ):
        return detail(
            kind,
            record_id,
            None,
            response,
            context,
            fields,
        )

    return endpoint


for segment, kind in KINDS.items():
    router.add_api_route(
        "/" + segment,
        collection_endpoint(kind),
        methods=["GET"],
        name="search_" + kind,
    )

    if kind != "stock":
        router.add_api_route(
            "/" + segment + "/{record_id}",
            detail_endpoint(kind),
            methods=["GET"],
            name="get_" + kind,
        )