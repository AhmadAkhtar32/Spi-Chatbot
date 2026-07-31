"""
Document Generator — deliberately NOT powered by the AI model.
------------------------------------------------------------------
Every other expert in this app calls Gemini in some form. This one
doesn't, on purpose: Atif's brief for this expert says it should
"produce consistent, template-based deliverables." An LLM is a poor
fit for that — its wording can vary slightly between calls even given
identical input, which is the opposite of "consistent." A Purchase
Order should read exactly the same way every time it's generated from
the same data.

So this is plain, deterministic template filling: take a template with
{{placeholder}} tokens, replace each one with a real value, done. No
model call, no variability, no cost per generation.

Adding a new document type later means adding one more entry to
TEMPLATES and one more .txt file in templates/ — nothing else changes.
"""

import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# Registry describing each template's fields, so the frontend can build
# a form dynamically without hardcoding field names in two places.
TEMPLATES = [
    {
        "id": "purchase_order",
        "name": "Purchase Order",
        "description": "Standard PO document for a supplier order.",
        "file": "purchase_order.txt",
        "fields": [
            {"key": "po_number", "label": "PO Number", "type": "text"},
            {"key": "date", "label": "Date", "type": "date"},
            {"key": "supplier_name", "label": "Supplier Name", "type": "text"},
            {"key": "supplier_address", "label": "Supplier Address", "type": "text"},
            {"key": "item_description", "label": "Item Description", "type": "text"},
            {"key": "quantity", "label": "Quantity", "type": "text"},
            {"key": "unit_price", "label": "Unit Price", "type": "text"},
            {"key": "total_amount", "label": "Total Amount", "type": "text"},
            {"key": "delivery_date", "label": "Requested Delivery Date", "type": "date"},
            {"key": "requested_by", "label": "Requested By", "type": "text"},
        ],
    },
    {
        "id": "credit_return_note",
        "name": "Credit / Return Note (CRN)",
        "description": "Document for a customer return or credit adjustment.",
        "file": "credit_return_note.txt",
        "fields": [
            {"key": "crn_number", "label": "CRN Number", "type": "text"},
            {"key": "date", "label": "Date", "type": "date"},
            {"key": "customer_name", "label": "Customer Name", "type": "text"},
            {"key": "original_order_id", "label": "Original Order ID", "type": "text"},
            {"key": "item_description", "label": "Item Description", "type": "text"},
            {"key": "quantity_returned", "label": "Quantity Returned", "type": "text"},
            {"key": "reason", "label": "Reason for Return", "type": "text"},
            {"key": "credit_amount", "label": "Credit Amount", "type": "text"},
            {"key": "approved_by", "label": "Approved By", "type": "text"},
        ],
    },
]

_TEMPLATES_BY_ID = {t["id"]: t for t in TEMPLATES}


def list_templates() -> list[dict]:
    """Metadata only — no file content — for building a form on the frontend."""
    return [{"id": t["id"], "name": t["name"], "description": t["description"], "fields": t["fields"]} for t in TEMPLATES]


def generate_document(template_id: str, fields: dict) -> dict:
    """Fill a template with the given field values. Raises KeyError if the
    template_id doesn't exist, and leaves any {{token}} with no matching
    field value visibly unfilled (e.g. "{{missing_field}}") rather than
    silently guessing — a generator should never invent data."""
    template = _TEMPLATES_BY_ID.get(template_id)
    if not template:
        raise KeyError(f"Unknown template: {template_id}")

    template_path = TEMPLATES_DIR / template["file"]
    text = template_path.read_text(encoding="utf-8")

    def replace(match):
        key = match.group(1)
        return str(fields.get(key, match.group(0)))  # leave placeholder visible if missing

    filled = re.sub(r"\{\{(\w+)\}\}", replace, text)

    filename = f"{template_id}_{fields.get(template['fields'][0]['key'], 'document')}.txt"
    filename = re.sub(r"[^\w\-.]", "_", filename)  # keep it a safe filename

    return {"document_text": filled, "filename": filename}
