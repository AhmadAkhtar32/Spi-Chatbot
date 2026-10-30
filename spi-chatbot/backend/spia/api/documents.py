"""Document APIs accept identifiers; values come from the server data source."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from spia.api.access import require_access_context
from spia.security.access_control import AccessDenied
from spia.security.store import SecurityConfigurationError
from spia.services.business import BusinessUnavailable
from spia.services.documents import generate_document, list_templates

router = APIRouter(
    prefix="/api/v1/documents",
    tags=["Document generation"],
)


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_id: Literal[
        "purchase_order",
        "credit_return_note",
    ]
    record_id: str = Field(
        pattern=r"^[A-Za-z0-9-]{1,64}$"
    )


def run(response, operation):
    response.headers["Cache-Control"] = "no-store"

    try:
        result = operation()

    except AccessDenied as exc:
        raise HTTPException(
            403,
            exc.code,
            headers={"Cache-Control": "no-store"},
        ) from None

    except (SecurityConfigurationError, BusinessUnavailable):
        raise HTTPException(
            503,
            "Document source or configuration unavailable",
            headers={"Cache-Control": "no-store"},
        ) from None

    if result is None:
        raise HTTPException(
            404,
            "Source record not found or unavailable",
            headers={"Cache-Control": "no-store"},
        )

    return result


@router.get("/templates")
def templates(
    response: Response,
    context=Depends(require_access_context),
):
    return run(
        response,
        lambda: list_templates(context),
    )


@router.post("/generate")
def generate(
    body: GenerateRequest,
    response: Response,
    context=Depends(require_access_context),
):
    return run(
        response,
        lambda: generate_document(
            context,
            body.template_id,
            body.record_id,
        ),
    )