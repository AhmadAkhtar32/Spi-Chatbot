"""Internal presentation profiles; licenses come from security.store.

The caller must supply a user obtained from a verified server session.
Never look up a user ID supplied directly by a browser request.
"""

from spia.core.paths import BACKEND_DIR

import json
from functools import lru_cache
from pathlib import Path


DATA_PATH = BACKEND_DIR / "data/sample_data.json"


class AccessDenied(Exception):
    """A feature or record is unavailable to the current sample user."""


@lru_cache(maxsize=1)
def load_sample_data() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def get_presenter_user(verified_user_id: str) -> dict:
    """Call only after the user's identity has been verified by the server."""
    for user in load_sample_data()["users"]:
        if user["id"] == verified_user_id:
            return user
    raise AccessDenied("Sample user unavailable")


def _require(condition: bool) -> None:
    if not condition:
        raise AccessDenied("Access denied")


def authorize_surface(user: dict, verified_surface: str) -> None:
    """The surface must come from a verified launch/session, not request JSON."""
    _require(verified_surface in user["surfaces"])


def authorize_expert(
    user: dict,
    verified_surface: str,
    expert: str,
    module: str | None = None,
) -> None:
    authorize_surface(user, verified_surface)
    _require(expert in user["experts"])
    if module is not None:
        _require(module in user["module_licenses"])
    if expert == "bi_expert":
        _require(verified_surface == "spia_tsplus")


def authorize_business_lookup(user: dict, verified_surface: str) -> None:
    authorize_surface(user, verified_surface)
    _require("assistant.business_lookup" in user["permissions"])


def authorize_record(
    user: dict,
    verified_surface: str,
    kind: str,
    record: dict,
) -> None:
    """Check feature, module and individual record ownership together."""
    authorize_surface(user, verified_surface)
    _require(isinstance(record, dict))
    permissions = user["permissions"]
    modules = user["module_licenses"]
    scope = user["scopes"]

    if kind == "stock":
        _require("stock.read" in permissions and "inventory" in modules)
        _require(record.get("warehouse_id") in scope["warehouse_ids"])
    elif kind == "sales_orders":
        _require("sales_orders.read" in permissions and "sales" in modules)
        _require(record.get("customer_party_id") in scope["party_ids"])
    elif kind == "purchase_orders":
        _require("purchase_orders.read" in permissions and "purchasing" in modules)
        _require(record.get("supplier_party_id") in scope["party_ids"])
    elif kind == "credit_return_notes":
        _require("sales_orders.read" in permissions and "sales" in modules)
        _require(record.get("customer_party_id") in scope["party_ids"])
    elif kind == "payroll":
        _require("payroll" in modules)
        _require("payroll.read" in permissions or "payroll.read_self" in permissions)
        _require(record.get("employee_id") in scope["employee_ids"])
    elif kind == "tickets":
        _require("support_expert" in user["experts"])
        _require("tickets.read" in permissions)
        _require(record.get("module") in modules)
        _require(record.get("id") in scope["ticket_ids"])
    else:
        raise AccessDenied("Unsupported record type")


def authorize_document(
    user: dict,
    verified_surface: str,
    template_id: str,
    record: dict,
) -> None:
    """Authorize the source record before filling a document template."""
    authorize_expert(user, verified_surface, "document_generator")
    _require("documents.generate" in user["permissions"])
    if template_id == "purchase_order":
        authorize_record(user, verified_surface, "purchase_orders", record)
    elif template_id == "credit_return_note":
        authorize_record(user, verified_surface, "credit_return_notes", record)
    else:
        raise AccessDenied("Unsupported document template")