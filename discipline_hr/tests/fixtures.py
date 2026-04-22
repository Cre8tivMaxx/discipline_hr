# Copyright (c) 2026, Abdelrahman Elsayed and Contributors
# See license.txt

import frappe


def ensure_fiscal_year(year: int) -> bool:
    """Ensure an active Fiscal Year covers `year`. Returns True if created."""
    mid = f"{year}-06-15"
    existing = frappe.db.exists(
        "Fiscal Year",
        {"year_start_date": ["<=", mid], "year_end_date": [">=", mid], "disabled": 0},
    )
    if existing:
        return False
    frappe.get_doc(
        {
            "doctype": "Fiscal Year",
            "year": str(year),
            "year_start_date": f"{year}-01-01",
            "year_end_date": f"{year}-12-31",
        }
    ).insert(ignore_permissions=True, ignore_if_duplicate=True)
    return True


def delete_fiscal_year(year: int) -> None:
    if frappe.db.exists("Fiscal Year", str(year)):
        frappe.delete_doc("Fiscal Year", str(year), force=True, ignore_permissions=True)
