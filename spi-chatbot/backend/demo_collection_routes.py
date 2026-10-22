"""Collection endpoints mounted under the existing business router."""

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

from business_collection_provider import get_collection_provider
from business_data_provider import DataSourceUnavailable
from demo_routes import require_demo_identity


ID_PATTERN = r"^[A-Za-z0-9-]+$"


class SearchFilters(BaseModel):
    model_config = {"extra": "forbid"}

    q: str = Field(default="", max_length=100)
    status: str | None = Field(
        default=None,
        max_length=50,
    )
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class PayrollFilters(SearchFilters):
    employee_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=ID_PATTERN,
    )

    period: str | None = Field(
        default=None,
        pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$",
    )

    @model_validator(mode="after")
    def validate_period(self):
        if self.period is not None:
            date.fromisoformat(self.period + "-01")
        return self


class DatedFilters(SearchFilters):
    date_from: date | None = None
    date_to: date | None = None

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


class TicketFilters(DatedFilters):
    module: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class CreditReturnFilters(DatedFilters):
    party_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=ID_PATTERN,
    )


def create_collection_router(
    require_feature,
    page_response,
):
    """Reuse existing permission and page checks."""

    router = APIRouter()

    def search(response, identity, kind, filters):
        require_feature(identity, kind)

        values = filters.model_dump()
        values["q"] = values["q"].strip()
        values["status"] = (
            (values["status"] or "").strip() or None
        )

        if values.get("module") is not None:
            values["module"] = values["module"].casefold()

        try:
            page = get_collection_provider().search_collection(
                identity,
                kind,
                **values,
            )

        except DataSourceUnavailable:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Business data source is not configured "
                    "or unavailable"
                ),
                headers={"Cache-Control": "no-store"},
            ) from None

        # Recheck record permissions and page boundaries.
        result = page_response(
            response,
            identity,
            kind,
            page,
            values,
        )

        # Verify these filters also narrowed the returned rows.
        for item in page.items:
            for key in ("employee_id", "period", "module"):
                if (
                    values.get(key) is not None
                    and item["record"].get(key) != values[key]
                ):
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "Business data source returned "
                            "an invalid page"
                        ),
                        headers={"Cache-Control": "no-store"},
                    )

        return result

    @router.get("/payroll")
    def search_payroll(
        response: Response,
        filters: Annotated[PayrollFilters, Query()],
        identity: tuple[dict, str] = Depends(
            require_demo_identity
        ),
    ):
        return search(
            response,
            identity,
            "payroll",
            filters,
        )

    @router.get("/tickets")
    def search_tickets(
        response: Response,
        filters: Annotated[TicketFilters, Query()],
        identity: tuple[dict, str] = Depends(
            require_demo_identity
        ),
    ):
        return search(
            response,
            identity,
            "tickets",
            filters,
        )

    @router.get("/credit-return-notes")
    def search_credit_return_notes(
        response: Response,
        filters: Annotated[CreditReturnFilters, Query()],
        identity: tuple[dict, str] = Depends(
            require_demo_identity
        ),
    ):
        return search(
            response,
            identity,
            "credit_return_notes",
            filters,
        )

    return router