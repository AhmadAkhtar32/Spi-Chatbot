
FAKE_STOCK_DB = {
    "pepsi": 50,
    "coke": 120,
    "sprite": 0,
    "fanta": 18,
}

FAKE_ORDERS_DB = {
    "1234": {"status": "Shipped", "eta": "2 days"},
    "5678": {"status": "Processing", "eta": "5 days"},
}


def check_stock(item: str) -> str:
    """Look up the current stock quantity for a named item."""
    # TODO (real DB): cursor.execute(
    #     "SELECT qty FROM inv_stock WHERE item_name = :item", item=item
    # )
    qty = FAKE_STOCK_DB.get(item.lower())
    if qty is None:
        return f"No stock record found for '{item}' (placeholder data)."
    if qty == 0:
        return f"{item} is currently OUT OF STOCK (placeholder data)."
    return f"Stock of {item}: {qty} units (placeholder data)."


def get_order_status(order_id: str) -> str:
    """Look up the status of a given order ID."""
    # TODO (real DB): query SPI's order/header tables by order_id,
    # and enforce that the requesting customer owns this order_id
    # before returning anything.
    order = FAKE_ORDERS_DB.get(str(order_id).strip("#"))
    if not order:
        return f"No order found with ID #{order_id} (placeholder data)."
    return (
        f"Order #{order_id}: Status = {order['status']}, "
        f"ETA {order['eta']} (placeholder data)."
    )


def find_menu_location(task: str) -> str:
    """Business-navigation helper: tell the user which SPI screen/menu handles a task."""
    # TODO (real): this can eventually be backed by a small lookup table
    # of module -> menu path, maintained alongside the real SPI screens.
    known_paths = {
        "add stock": "Inventory > Stock Adjustment > Add Stock",
        "purchase order": "Purchase > Purchase Order > New PO",
        "check stock": "Inventory > Stock Status Report",
    }
    for key, path in known_paths.items():
        if key in task.lower():
            return f"Go to: {path} (placeholder navigation data)."
    return f"No navigation mapping found yet for '{task}' (placeholder data)."


# Registry: maps function name (string) -> actual Python function.
# The AI only ever sees the names/descriptions below (via the tool
# schema in app.py) — it calls this registry indirectly through us.
AVAILABLE_FUNCTIONS = {
    "check_stock": check_stock,
    "get_order_status": get_order_status,
    "find_menu_location": find_menu_location,
}
