"""Fill original document templates from authorized server records."""
import re
import base64
from decimal import Decimal, InvalidOperation

from spia.core.paths import BACKEND_DIR
from spia.security.access_control import (
    AccessDenied, Resource, allowed_fields,
)
from spia.services.business import BusinessService, BusinessUnavailable

FEATURE = "document_generator"

TEMPLATES = {
    "purchase_order": {
        "name": "Purchase Order",
        "kind": "purchase_orders",
        "fields": frozenset(
            "id order_date supplier_party_id item_id quantity "
            "unit_price_pkr total_amount_pkr "
            "requested_delivery_date requested_by".split()
        ),
        "money": {"unit_price_pkr", "total_amount_pkr"},
    },
    "credit_return_note": {
        "name": "Credit / Return Note",
        "kind": "credit_return_notes",
        "fields": frozenset(
            "id date customer_party_id sales_order_id item_id "
            "quantity_returned reason credit_amount_pkr approved_by".split()
        ),
        "money": {"credit_amount_pkr"},
    },
}

LABELS = {
    "purchase_orders": {
        "supplier_name", "supplier_address", "item_description",
    },
    "credit_return_notes": {
        "customer_name", "item_description",
    },
}

MAPPING = {
    "purchase_order": {
        "po_number": "id",
        "date": "order_date",
        "supplier_name": "supplier_name",
        "supplier_address": "supplier_address",
        "item_description": "item_description",
        "quantity": "quantity",
        "unit_price": "unit_price_pkr",
        "total_amount": "total_amount_pkr",
        "delivery_date": "requested_delivery_date",
        "requested_by": "requested_by",
    },
    "credit_return_note": {
        "crn_number": "id",
        "date": "date",
        "customer_name": "customer_name",
        "original_order_id": "sales_order_id",
        "item_description": "item_description",
        "quantity_returned": "quantity_returned",
        "reason": "reason",
        "credit_amount": "credit_amount_pkr",
        "approved_by": "approved_by",
    },
}

MODULES = {
    "purchase_orders": "purchasing",
    "credit_return_notes": "sales",
}


def _authorize(service, spec):
    for action in ("read", "generate"):
        service.require(
            spec["kind"],
            feature=FEATURE,
            action=action,
            fields=spec["fields"] | LABELS[spec["kind"]],
        )


def list_templates(context):
    service = BusinessService(context)
    available = []

    for template_id, spec in TEMPLATES.items():
        try:
            _authorize(service, spec)
        except AccessDenied:
            continue

        available.append({
            "id": template_id,
            "name": spec["name"],
            "source_type": spec["kind"],
        })

    if not available:
        raise AccessDenied("DOCUMENT_GENERATION_DENIED")

    return service.finish({"templates": available})


def _record(service, spec, record_id, action):
    rows = [
        item["record"]
        for item in service.records(
            spec["kind"],
            feature=FEATURE,
            action=action,
        )
        if item["record"].get("id") == record_id
    ]

    if not rows:
        return None
    if len(rows) != 1:
        raise BusinessUnavailable("Duplicate source record")
    if not spec["fields"] <= rows[0].keys():
        raise AccessDenied("FIELD_ACCESS_DENIED")

    row = rows[0]
    attributes = {
        scope.attribute
        for rule in service.context.policy.rules
        for scope in rule.scopes
    }

    resource = Resource(
        company_id=service.context.identity.company_id,
        resource_type=spec["kind"],
        module=MODULES[spec["kind"]],
        classifications=["business"],
        facts=[
            {"attribute": key, "value": row[key]}
            for key in attributes if key in row
        ],
    )

    allowed_fields(
        service.context.identity,
        service.context.policy,
        FEATURE,
        action,
        resource,
        requested_fields=frozenset(LABELS[spec["kind"]]),
    )

    party_key = (
        "supplier_party_id"
        if spec["kind"] == "purchase_orders"
        else "customer_party_id"
    )
    party = service.indexes["parties"].get(row[party_key])
    item = service.indexes["items"].get(row["item_id"])

    for linked in (party, item):
        if linked is None:
            raise BusinessUnavailable("Related source record is missing")
        if linked.get(
            "company_id",
            service.context.identity.company_id,
        ) != service.context.identity.company_id:
            raise AccessDenied("RESOURCE_DENIED")

    prefix = (
        "supplier"
        if spec["kind"] == "purchase_orders"
        else "customer"
    )
    row[prefix + "_name"] = party.get("name")
    row["item_description"] = item.get("name")

    if spec["kind"] == "purchase_orders":
        row["supplier_address"] = party.get("address")

    return row


def _text(value):
    if (
        type(value) not in (str, int, float, bool)
        or len(str(value)) > 2000
    ):
        raise BusinessUnavailable("Invalid document field")

    return re.sub(r"[\r\n\x00-\x1f\x7f]+", " ", str(value))




def _document_pdf(document, title):
    """Render company wording on a compact, content-height receipt page."""
    from io import BytesIO
    import textwrap
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen.canvas import Canvas

    try:
        document.encode("cp1252")
    except UnicodeEncodeError:
        raise BusinessUnavailable(
            "This template needs a Unicode PDF font before it can be printed"
        ) from None

    font_size = 10.5
    columns = 60
    margin = 20
    leading = 15

    char_width = stringWidth(
        "M", "Courier", font_size
    )
    content_width = columns * char_width
    width = content_width + 2 * margin
    lines = document.expandtabs(8).strip().splitlines()

    def separator(line):
        value = line.strip()
        return len(value) >= 3 and (
            set(value) == {"="}
            or set(value) == {"-"}
        )

    field_pattern = re.compile(r"^([^:]+):\s*(.*)$")

    labels = [
        match.group(1).strip()
        for line in lines
        if (
            match := field_pattern.match(line.strip())
        )
    ]

    value_column = max(
        (len(label) + 2 for label in labels),
        default=20,
    )

    if value_column > columns - 16:
        raise BusinessUnavailable(
            "Template labels exceed the receipt layout"
        )

    def wrapped(value, count):
        return textwrap.wrap(
            value,
            width=count,
            break_long_words=True,
            break_on_hyphens=False,
        ) or [""]

    rows = []
    header = True
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        index += 1

        if not line:
            header = False
            rows.append(("space", "", "", 8))

        elif separator(line):
            rows.append(("rule", "", "", 10))

        elif header:
            size = 12 if line.isupper() else 9.5
            limit = max(
                1,
                int(content_width / (size * 0.6)),
            )

            for part in wrapped(line, limit):
                kind = (
                    "heading"
                    if line.isupper()
                    else "company"
                )
                rows.append((kind, part, "", 19))

        elif (match := field_pattern.match(line)):
            label = match.group(1).strip()
            value = match.group(2).strip()

            for position, part in enumerate(
                wrapped(value, columns - value_column)
            ):
                rows.append((
                    "field",
                    label + ":" if position == 0 else "",
                    part,
                    leading,
                ))

        elif line.isupper():
            for part in wrapped(line, columns):
                rows.append((
                    "section", part, "", leading
                ))

        else:
            paragraph = [line]

            while index < len(lines):
                following = lines[index].strip()

                if (
                    not following
                    or separator(following)
                    or field_pattern.match(following)
                    or following.isupper()
                ):
                    break

                paragraph.append(following)
                index += 1

            for part in wrapped(
                " ".join(paragraph), columns
            ):
                rows.append((
                    "paragraph", part, "", leading
                ))

    height = (
        2 * margin
        + sum(row[3] for row in rows)
    )

    if not rows or height > 14400:
        raise BusinessUnavailable(
            "Document exceeds the receipt page limit"
        )

    output = BytesIO()
    pdf = Canvas(
        output,
        pagesize=(width, height),
        pageCompression=1,
    )
    pdf.setTitle(title)
    pdf.setAuthor("SPIA Assistant")

    top = height - margin

    for kind, first, second, row_height in rows:
        baseline = top - (
            12 if kind == "heading" else font_size
        )
        pdf.setFillColorRGB(0.12, 0.15, 0.2)

        if kind == "rule":
            pdf.setStrokeColorRGB(0.55, 0.58, 0.63)
            pdf.setLineWidth(0.5)
            pdf.line(
                margin,
                top - 5,
                width - margin,
                top - 5,
            )

        elif kind in {
            "heading", "company", "section"
        }:
            size = (
                12 if kind == "heading"
                else 9.5 if kind == "company"
                else font_size
            )
            font = (
                "Courier"
                if kind == "company"
                else "Courier-Bold"
            )
            pdf.setFont(font, size)
            pdf.drawCentredString(
                width / 2, baseline, first
            )

        elif kind == "field":
            pdf.setFont(
                "Courier-Bold", font_size
            )
            pdf.drawString(
                margin, baseline, first
            )
            pdf.setFont("Courier", font_size)
            pdf.drawString(
                margin + value_column * char_width,
                baseline,
                second,
            )

        elif kind == "paragraph":
            pdf.setFont("Courier", font_size)
            pdf.drawString(
                margin, baseline, first
            )

        top -= row_height

    pdf.showPage()
    pdf.save()
    return output.getvalue()


def generate_document(context, template_id, record_id):
    spec = TEMPLATES[template_id]
    service = BusinessService(context)
    _authorize(service, spec)

    read = _record(service, spec, record_id, "read")
    generated = _record(service, spec, record_id, "generate")

    if read is None or generated is None:
        return None

    required = spec["fields"] | LABELS[spec["kind"]]
    if any(read[key] != generated[key] for key in required):
        raise AccessDenied("ACCESS_CHANGED")

    values = {
        placeholder: _text(generated[field])
        for placeholder, field in MAPPING[template_id].items()
    }

    for key in spec["money"]:
        try:
            amount = Decimal(str(generated[key]))
            if not amount.is_finite():
                raise ValueError("Non-finite amount")
            placeholder = next(
                name
                for name, field in MAPPING[template_id].items()
                if field == key
            )
            values[placeholder] = format(amount, ".2f")
        except (InvalidOperation, ValueError, ArithmeticError):
            raise BusinessUnavailable("Invalid document amount") from None

    path = BACKEND_DIR / "templates" / (template_id + ".txt")

    try:
        with path.open("r", encoding="utf-8-sig") as file:
            template = file.read(65537)

        tokens = set(re.findall(r"\{\{(\w+)\}\}", template))
        if len(template) > 65536 or tokens != set(values):
            raise ValueError("Template fields do not match its contract")

    except (OSError, ValueError, UnicodeError):
        raise BusinessUnavailable(
            "Document template is unavailable"
        ) from None

    document = re.sub(
        r"\{\{(\w+)\}\}",
        lambda match: values[match[1]],
        template,
    )
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", record_id)

    # Check access before rendering and again before returning.
    service.finish({})
    pdf = _document_pdf(
        document,
        spec["name"] + " " + record_id,
    )

    return service.finish({
        "document_text": document,
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "filename": f"{template_id}_{safe_id}.pdf",
        "template_id": template_id,
        "record_id": record_id,
        **service.metadata(),
    })