"""BI endpoints require a BI license and a signed SPIA demo surface."""

from datetime import date
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
)
from pydantic import BaseModel, Field, model_validator

from business_bi_provider import get_bi_provider
from business_data_provider import DataSourceUnavailable
from demo_policy import AccessDenied, authorize_expert
from demo_routes import require_demo_identity


router = APIRouter(
    prefix="/bi",
    tags=["Demo BI expert"],
)


class BIFilters(BaseModel):
    model_config = {"extra": "forbid"}

    area: Literal[
        "sales", "purchases", "stock"
    ] = "sales"

    date_from: date | None = None
    date_to: date | None = None

    status: str | None = Field(
        default=None,
        max_length=50,
    )

    party_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9-]+$",
    )

    warehouse_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9-]+$",
    )

    @model_validator(mode="after")
    def validate_filters(self):
        if (
            self.date_from
            and self.date_to
            and self.date_from > self.date_to
        ):
            raise ValueError(
                "date_from must not be after date_to"
            )

        if self.area == "stock":
            values = (
                self.date_from,
                self.date_to,
                self.status,
                self.party_id,
            )
            if any(value is not None for value in values):
                raise ValueError(
                    "Stock supports warehouse filtering only"
                )

        elif self.warehouse_id is not None:
            raise ValueError(
                "Warehouse filtering applies to stock only"
            )

        return self


def require_bi(
    identity=Depends(require_demo_identity),
):
    try:
        authorize_expert(
            identity[0],
            identity[1],
            "bi_expert",
        )
    except AccessDenied:
        raise HTTPException(
            status_code=403,
            detail=(
                "BI is available only to a licensed "
                "SPIA/TSplus user"
            ),
            headers={"Cache-Control": "no-store"},
        ) from None

    return identity


def run(operation):
    try:
        return operation()

    except AccessDenied:
        raise HTTPException(
            status_code=403,
            detail=(
                "This BI data area is not available "
                "to your role"
            ),
            headers={"Cache-Control": "no-store"},
        ) from None

    except DataSourceUnavailable:
        raise HTTPException(
            status_code=503,
            detail="BI data source is unavailable",
            headers={"Cache-Control": "no-store"},
        ) from None


@router.get("/summary")
def summary(
    response: Response,
    filters: Annotated[BIFilters, Query()],
    identity=Depends(require_bi),
):
    values = filters.model_dump()
    values["status"] = (
        (values["status"] or "").strip() or None
    )

    result = run(
        lambda: get_bi_provider().summary(
            identity,
            **values,
        )
    )

    response.headers["Cache-Control"] = "no-store"

    return {
        **result,
        "filters": values,
    }


@router.get("/suggestions")
def suggestions(
    response: Response,
    identity=Depends(require_bi),
):
    result = run(
        lambda: get_bi_provider().suggestions(identity)
    )

    response.headers["Cache-Control"] = "no-store"
    return result