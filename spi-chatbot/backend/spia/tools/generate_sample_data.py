"""Create reproducible, entirely fictional SPIA presentation data."""

from spia.core.paths import BACKEND_DIR

import json
from datetime import date, timedelta
from pathlib import Path


OUTPUT = BACKEND_DIR / "data/sample_data.json"
AS_OF = date(2026, 10, 15)
START = date(2026, 1, 1)


def sample_date(number: int) -> str:
    return (START + timedelta(days=(number * 11) % 280)).isoformat()


def scopes(parties=(), warehouses=(), employees=(), tickets=()):
    return {
        "party_ids": list(parties),
        "warehouse_ids": list(warehouses),
        "employee_ids": list(employees),
        "ticket_ids": list(tickets),
    }


def build_data():
    parties = [
        {"id": "PARTY-100", "name": "Example Dual Trading", "types": ["customer", "supplier"], "address": "Sample Address 100, Lahore"},
        {"id": "PARTY-200", "name": "Example Customer Co", "types": ["customer"], "address": "Sample Address 200, Karachi"},
        {"id": "PARTY-300", "name": "Example Supplier Co", "types": ["supplier"], "address": "Sample Address 300, Islamabad"},
    ]
    for number in range(4, 41):
        party_types = (["customer", "supplier"] if number % 5 == 0 else
                       ["customer"] if number % 2 == 0 else ["supplier"])
        parties.append({
            "id": f"PARTY-{number + 300:03d}",
            "name": f"Sample Business {number:03d}",
            "types": party_types,
            "address": f"Sample Address {number:03d}, Example City",
        })

    items = [
        {"id": "SKU-100", "name": "Sample Barcode Scanner", "unit": "pieces", "unit_price_pkr": 12500},
        {"id": "SKU-200", "name": "Sample Receipt Paper", "unit": "rolls", "unit_price_pkr": 580},
    ]
    item_names = ["Packing Tape", "Label Roll", "Scanner Cable", "Thermal Printer", "Storage Box", "Display Stand"]
    for number in range(3, 61):
        items.append({
            "id": f"SKU-{number + 200:03d}",
            "name": f"Sample {item_names[number % len(item_names)]} {number:03d}",
            "unit": "pieces" if number % 2 else "rolls",
            "unit_price_pkr": 250 + 125 * number,
        })

    warehouses = [
        {"id": "WH-LHR", "name": "Sample Lahore Warehouse"},
        {"id": "WH-KHI", "name": "Sample Karachi Warehouse"},
        {"id": "WH-ISB", "name": "Sample Islamabad Warehouse"},
        {"id": "WH-FSD", "name": "Sample Faisalabad Warehouse"},
    ]
    fixed_stock = {("SKU-100", "WH-LHR"): 14,
                   ("SKU-100", "WH-KHI"): 0,
                   ("SKU-200", "WH-LHR"): 86}
    stock = []
    for item_index, item in enumerate(items):
        for warehouse_index, warehouse in enumerate(warehouses):
            quantity = fixed_stock.get((item["id"], warehouse["id"]))
            if quantity is None:
                quantity = (item_index * 13 + warehouse_index * 19) % 150
                if (item_index + warehouse_index) % 17 == 0:
                    quantity = 0
            stock.append({"item_id": item["id"], "warehouse_id": warehouse["id"], "quantity_available": quantity})

    customers = [party["id"] for party in parties if "customer" in party["types"]]
    suppliers = [party["id"] for party in parties if "supplier" in party["types"]]

    sales_orders = [{
        "id": "SO-1001", "customer_party_id": "PARTY-100", "item_id": "SKU-100",
        "quantity": 2, "unit_price_pkr": 12500, "total_amount_pkr": 25000,
        "status": "Dispatched", "order_date": "2026-09-15",
    }, {
        "id": "SO-1002", "customer_party_id": "PARTY-200", "item_id": "SKU-200",
        "quantity": 10, "unit_price_pkr": 580, "total_amount_pkr": 5800,
        "status": "Pending approval", "order_date": "2026-10-05",
    }]
    for number in range(3, 601):
        item = items[(number * 7) % len(items)]
        quantity = 1 + (number * 3) % 15
        sales_orders.append({
            "id": f"SO-{1000 + number}",
            "customer_party_id": customers[(number * 7) % len(customers)],
            "item_id": item["id"], "quantity": quantity,
            "unit_price_pkr": item["unit_price_pkr"],
            "total_amount_pkr": quantity * item["unit_price_pkr"],
            "status": ["Pending approval", "Processing", "Dispatched", "Delivered"][number % 4],
            "order_date": sample_date(number),
        })

    purchase_orders = [{
        "id": "PO-2001", "supplier_party_id": "PARTY-100", "item_id": "SKU-200",
        "quantity": 100, "unit_price_pkr": 580, "total_amount_pkr": 58000,
        "status": "Approved", "order_date": "2026-09-20",
        "requested_delivery_date": "2026-10-02", "requested_by": "Sample Buyer",
    }, {
        "id": "PO-2002", "supplier_party_id": "PARTY-300", "item_id": "SKU-100",
        "quantity": 5, "unit_price_pkr": 12500, "total_amount_pkr": 62500,
        "status": "Received", "order_date": "2026-09-22",
        "requested_delivery_date": "2026-10-04", "requested_by": "Sample Buyer",
    }]
    for number in range(3, 451):
        item = items[(number * 11) % len(items)]
        quantity = 2 + (number * 5) % 48
        order_date = date.fromisoformat(sample_date(number + 9))
        purchase_orders.append({
            "id": f"PO-{2000 + number}",
            "supplier_party_id": suppliers[(number * 7) % len(suppliers)],
            "item_id": item["id"], "quantity": quantity,
            "unit_price_pkr": item["unit_price_pkr"],
            "total_amount_pkr": quantity * item["unit_price_pkr"],
            "status": ["Pending approval", "Approved", "Ordered", "Received"][number % 4],
            "order_date": order_date.isoformat(),
            "requested_delivery_date": (order_date + timedelta(days=12)).isoformat(),
            "requested_by": "Sample Buyer",
        })

    employees = [{"id": f"EMP-{1000 + number}", "name": f"Sample Employee {number:03d}"}
                 for number in range(1, 101)]
    periods = [f"2025-{month:02d}" for month in range(10, 13)] + [f"2026-{month:02d}" for month in range(1, 10)]
    payroll = []
    for number, employee in enumerate(employees, start=1):
        gross = 85000 if number == 1 else 95000 if number == 2 else 45000 + 500 * number
        for period in periods:
            payroll.append({
                "id": f"PAY-{period}-{employee['id'].split('-')[1]}",
                "employee_id": employee["id"], "period": period, "currency": "PKR",
                "gross": gross, "deductions": 5000, "net": gross - 5000,
                "status": "Paid",
            })

    tickets = []
    for number in range(1, 201):
        is_financial = number % 2 == 1
        party_id = "PARTY-100" if number == 1 else "PARTY-200" if number == 2 else parties[(number * 7) % len(parties)]["id"]
        tickets.append({
            "id": f"TCK-{3000 + number}", "party_id": party_id,
            "module": "financial" if is_financial else "inventory",
            "subject": "Voucher posting error" if number == 1 else "Stock report mismatch" if number == 2 else f"Sample incident {number:03d}",
            "status": "In progress" if number == 1 else "Resolved" if number == 2 else ["Open", "In progress", "Resolved"][number % 3],
            "assigned_user_id": "demo_support" if is_financial else "demo_inventory_support",
            "created_at": sample_date(number),
        })

    credit_return_notes = [{
        "id": "CRN-4001", "sales_order_id": "SO-1001", "customer_party_id": "PARTY-100",
        "item_id": "SKU-100", "quantity_returned": 1, "reason": "Sample transit damage",
        "credit_amount_pkr": 12500, "status": "Approved", "date": "2026-09-30",
        "approved_by": "Sample Manager",
    }]
    eligible = [order for order in sales_orders[2:] if order["status"] in ("Dispatched", "Delivered")]
    for number, order in enumerate(eligible[:99], start=2):
        return_date = min(AS_OF, date.fromisoformat(order["order_date"]) + timedelta(days=10))
        credit_return_notes.append({
            "id": f"CRN-{4000 + number}", "sales_order_id": order["id"],
            "customer_party_id": order["customer_party_id"], "item_id": order["item_id"],
            "quantity_returned": 1, "reason": "Sample customer return",
            "credit_amount_pkr": order["unit_price_pkr"],
            "status": "Approved", "date": return_date.isoformat(),
            "approved_by": "Sample Manager",
        })

    all_parties = [party["id"] for party in parties]
    all_warehouses = [warehouse["id"] for warehouse in warehouses]
    all_employees = [employee["id"] for employee in employees]
    support_tickets = [ticket["id"] for ticket in tickets if ticket["assigned_user_id"] == "demo_support"]
    inventory_tickets = [ticket["id"] for ticket in tickets if ticket["assigned_user_id"] == "demo_inventory_support"]
    users = [
        {"id": "demo_support", "role": "support", "surfaces": ["spia_tsplus"], "experts": ["support_expert"], "module_licenses": ["financial"], "permissions": ["tickets.read"], "scopes": scopes(tickets=support_tickets)},
        {"id": "demo_inventory_support", "role": "support", "surfaces": ["spia_tsplus"], "experts": ["support_expert"], "module_licenses": ["inventory"], "permissions": ["tickets.read"], "scopes": scopes(tickets=inventory_tickets)},
        {"id": "demo_implementation", "role": "implementation", "surfaces": ["spia_tsplus"], "experts": ["implementation_expert"], "module_licenses": ["financial", "inventory"], "permissions": [], "scopes": scopes()},
        {"id": "demo_operations", "role": "operations", "surfaces": ["spia_tsplus", "mobile"], "experts": [], "module_licenses": ["inventory", "sales", "purchasing"], "permissions": ["assistant.business_lookup", "stock.read", "sales_orders.read", "purchase_orders.read"], "scopes": scopes(parties=all_parties, warehouses=all_warehouses)},
        {"id": "demo_dual_party", "role": "business_partner", "surfaces": ["spia_tsplus", "mobile"], "experts": [], "module_licenses": ["sales", "purchasing"], "permissions": ["assistant.business_lookup", "sales_orders.read", "purchase_orders.read"], "scopes": scopes(parties=["PARTY-100"])},
        {"id": "demo_employee", "role": "employee", "surfaces": ["spia_tsplus"], "experts": [], "module_licenses": ["payroll"], "permissions": ["payroll.read_self"], "scopes": scopes(employees=["EMP-1001"])},
        {"id": "demo_hr", "role": "hr", "surfaces": ["spia_tsplus"], "experts": [], "module_licenses": ["payroll"], "permissions": ["payroll.read"], "scopes": scopes(employees=all_employees)},
        {"id": "demo_bi", "role": "bi_internal", "surfaces": ["spia_tsplus"], "experts": ["bi_expert"], "module_licenses": ["inventory", "sales", "purchasing"], "permissions": ["assistant.business_lookup", "stock.read", "sales_orders.read", "purchase_orders.read"], "scopes": scopes(parties=all_parties, warehouses=all_warehouses)},
        {"id": "demo_document_clerk", "role": "document_clerk", "surfaces": ["spia_tsplus"], "experts": ["document_generator"], "module_licenses": ["sales", "purchasing"], "permissions": ["documents.generate", "sales_orders.read", "purchase_orders.read"], "scopes": scopes(parties=all_parties)},
    ]
    scenarios = [
        {"user_id": "demo_operations", "surface": "spia_tsplus", "question": "Stock of SKU-100 in WH-LHR?", "expected": "ALLOW: 14 pieces (sample snapshot)"},
        {"user_id": "demo_operations", "surface": "mobile", "question": "Stock of SKU-100 in WH-KHI?", "expected": "ALLOW: 0 pieces (sample snapshot)"},
        {"user_id": "demo_dual_party", "surface": "mobile", "question": "Status of SO-1001?", "expected": "ALLOW: Dispatched; PARTY-100 is the customer"},
        {"user_id": "demo_dual_party", "surface": "mobile", "question": "Status of PO-2001?", "expected": "ALLOW: Approved; PARTY-100 is the supplier"},
        {"user_id": "demo_dual_party", "surface": "mobile", "question": "Status of SO-1002?", "expected": "DENY: record not found or inaccessible"},
        {"user_id": "demo_employee", "surface": "spia_tsplus", "question": "Show PAY-2026-09-1001", "expected": "ALLOW: own payslip; net PKR 80000"},
        {"user_id": "demo_employee", "surface": "spia_tsplus", "question": "Show PAY-2026-09-1002", "expected": "DENY: record not found or inaccessible"},
        {"user_id": "demo_hr", "surface": "spia_tsplus", "question": "Show PAY-2026-09-1002", "expected": "ALLOW: HR license; net PKR 90000"},
        {"user_id": "demo_support", "surface": "spia_tsplus", "question": "Status of TCK-3001?", "expected": "ALLOW: In progress"},
        {"user_id": "demo_support", "surface": "spia_tsplus", "question": "Status of TCK-3002?", "expected": "DENY: record not found or inaccessible"},
        {"user_id": "demo_support", "surface": "spia_tsplus", "question": "How do I set up a GL voucher type?", "expected": "DENY: support-only license"},
        {"user_id": "demo_implementation", "surface": "spia_tsplus", "question": "How do I set up a GL voucher type?", "expected": "ALLOW: document answer"},
        {"user_id": "demo_bi", "surface": "mobile", "question": "Open BI expert", "expected": "DENY: BI is SPIA/TSPlus only"},
        {"user_id": "demo_document_clerk", "surface": "spia_tsplus", "question": "Generate purchase order PO-2001", "expected": "ALLOW: purchase_order template from PO-2001"},
        {"user_id": "demo_document_clerk", "surface": "spia_tsplus", "question": "Generate return note CRN-4001", "expected": "ALLOW: credit_return_note template from SO-1001"},
    ]

    return {
        "notice": "FICTIONAL DEMO DATA ONLY. Static snapshot; never present as live SPIA data.",
        "dataset_version": "2.0", "snapshot_at": "2026-10-15T10:00:00+05:00",
        "tenant": {"id": "DEMO-CLIENT-001", "name": "Example SPIA Client", "address": "Sample Office, Example City"},
        "parties": parties, "items": items, "warehouses": warehouses, "stock": stock,
        "sales_orders": sales_orders, "purchase_orders": purchase_orders,
        "employees": employees, "payroll": payroll, "tickets": tickets,
        "credit_return_notes": credit_return_notes, "users": users,
        "document_examples": [
            {"template_id": "purchase_order", "source_type": "purchase_orders", "source_id": "PO-2001"},
            {"template_id": "credit_return_note", "source_type": "credit_return_notes", "source_id": "CRN-4001"},
        ],
        "scenarios": scenarios,
    }


def main():
    data = build_data()
    OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for section in ("parties", "items", "warehouses", "stock", "sales_orders",
                    "purchase_orders", "employees", "payroll", "tickets",
                    "credit_return_notes", "users", "scenarios"):
        print(f"{section}: {len(data[section])}")
    print(f"Generated: {OUTPUT}")


if __name__ == "__main__":
    main()