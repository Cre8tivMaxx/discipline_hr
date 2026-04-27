# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections import defaultdict
from typing import Any

import frappe
from frappe import _
from frappe.utils import getdate, today

STATUS_INDICATOR = {
    "Auto Processed": "color: var(--green-600); font-weight: 600;",
    "Processed": "color: var(--blue-500); font-weight: 600;",
    "Pending": "color: var(--orange-500); font-weight: 600;",
    "Rejected": "color: var(--red-500); font-weight: 600;",
}


def execute(filters: dict | None = None) -> tuple[list[dict], list[dict], None, dict, list[dict]]:
    filters = filters or {}
    _validate_filters(filters)

    columns = _columns()
    rows = _fetch_rows(filters)
    _enrich(rows)
    summary = _report_summary(rows)
    chart = _chart(rows)

    return columns, rows, None, chart, summary


def _validate_filters(filters: dict) -> None:
    if not filters.get("company"):
        frappe.throw(_("Company is required"))
    if not (filters.get("from_date") and filters.get("to_date")):
        frappe.throw(_("From Date and To Date are required"))


def _columns() -> list[dict]:
    return [
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
        {"label": _("Age (days)"), "fieldname": "age_days", "fieldtype": "Int", "width": 90},
        {"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100},
        {
            "label": _("Permission"),
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "Attendance Permissions",
            "width": 150,
        },
        {
            "label": _("Employee"),
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 130,
        },
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
        {
            "label": _("Department"),
            "fieldname": "department",
            "fieldtype": "Link",
            "options": "Department",
            "width": 140,
        },
        {
            "label": _("Shift"),
            "fieldname": "shift_type",
            "fieldtype": "Link",
            "options": "Shift Type",
            "width": 130,
        },
        {"label": _("Minutes"), "fieldname": "minutes", "fieldtype": "Int", "width": 90},
        {"label": _("Auto Created"), "fieldname": "auto_created", "fieldtype": "Check", "width": 90},
        {"label": _("Has Error"), "fieldname": "has_error", "fieldtype": "Check", "width": 90},
        {
            "label": _("Attendance"),
            "fieldname": "attendance",
            "fieldtype": "Link",
            "options": "Attendance",
            "width": 140,
        },
        {
            "label": _("Discipline Penalty"),
            "fieldname": "discipline_penalty",
            "fieldtype": "Link",
            "options": "Discipline Penalty",
            "width": 150,
        },
        {
            "label": _("Grace Ledger"),
            "fieldname": "grace_ledger",
            "fieldtype": "Link",
            "options": "Employee Grace Ledger",
            "width": 150,
        },
        {"label": _("Reason"), "fieldname": "reason", "fieldtype": "Data", "width": 200},
        {"label": _("Error Log"), "fieldname": "error_log", "fieldtype": "Data", "width": 220},
        {"label": _("Created On"), "fieldname": "creation", "fieldtype": "Datetime", "width": 150},
    ]


def _fetch_rows(filters: dict) -> list[dict]:
    conditions = ["ap.date BETWEEN %(from_date)s AND %(to_date)s", "emp.company = %(company)s"]
    params: dict[str, Any] = {
        "from_date": filters["from_date"],
        "to_date": filters["to_date"],
        "company": filters["company"],
    }

    if filters.get("status"):
        statuses = filters["status"] if isinstance(filters["status"], list) else [filters["status"]]
        conditions.append("ap.status IN %(statuses)s")
        params["statuses"] = tuple(statuses)
    if filters.get("department"):
        conditions.append("emp.department = %(department)s")
        params["department"] = filters["department"]
    if filters.get("shift"):
        conditions.append("ap.shift_type = %(shift)s")
        params["shift"] = filters["shift"]
    if filters.get("employee"):
        conditions.append("ap.employee = %(employee)s")
        params["employee"] = filters["employee"]
    if filters.get("auto_created"):
        conditions.append("ap.auto_created = 1")
    if filters.get("has_error"):
        conditions.append("(ap.error_log IS NOT NULL AND ap.error_log != '')")
    if filters.get("stuck_days"):
        conditions.append(
            "(ap.status = 'Pending' AND DATEDIFF(%(today)s, DATE(ap.creation)) >= %(stuck_days)s)"
        )
        params["today"] = today()
        params["stuck_days"] = int(filters["stuck_days"])

    where = " AND ".join(conditions)
    query = f"""
        SELECT
            ap.name,
            ap.status,
            ap.date,
            ap.creation,
            ap.employee,
            ap.employee_name,
            emp.department,
            ap.shift_type,
            ap.minutes,
            ap.auto_created,
            ap.attendance,
            ap.reason,
            ap.error_log,
            dp.name AS discipline_penalty,
            egl.name AS grace_ledger
        FROM `tabAttendance Permissions` ap
        LEFT JOIN `tabEmployee` emp ON emp.name = ap.employee
        LEFT JOIN `tabDiscipline Penalty` dp ON dp.attendance_permission = ap.name AND dp.docstatus < 2
        LEFT JOIN `tabEmployee Grace Ledger` egl ON egl.attendance_permission = ap.name
        WHERE {where}
        ORDER BY
            CASE ap.status WHEN 'Pending' THEN 0 WHEN 'Auto Processed' THEN 1 WHEN 'Processed' THEN 2 ELSE 3 END,
            ap.creation ASC
    """
    return frappe.db.sql(query, params, as_dict=True)


def _enrich(rows: list[dict]) -> None:
    """Compute derived fields and attach inline styles."""
    today_d = getdate(today())
    for r in rows:
        creation = r.get("creation")
        age = (today_d - getdate(creation)).days if creation else 0
        r["age_days"] = age
        r["has_error"] = 1 if (r.get("error_log") or "").strip() else 0

        if r.get("error_log"):
            r["error_log"] = (r["error_log"] or "").splitlines()[0][:120]

        status = r.get("status")
        if status in STATUS_INDICATOR:
            r["_style_status"] = STATUS_INDICATOR[status]

        if status == "Pending":
            if age >= 5:
                r["_style_age_days"] = "color: var(--red-500); font-weight: 700;"
            elif age >= 2:
                r["_style_age_days"] = "color: var(--orange-500); font-weight: 600;"

        if r["has_error"]:
            r["_style_error_log"] = "color: var(--red-500);"


def _report_summary(rows: list[dict]) -> list[dict]:
    if not rows:
        return []

    total = len(rows)
    pending = sum(1 for r in rows if r["status"] == "Pending")
    errors = sum(1 for r in rows if r.get("has_error"))
    auto_processed = sum(1 for r in rows if r["status"] == "Auto Processed")
    oldest_pending = max((r["age_days"] for r in rows if r["status"] == "Pending"), default=0)
    auto_pct = round((auto_processed / total) * 100, 1) if total else 0

    return [
        {"label": _("Pending"), "value": pending, "datatype": "Int", "indicator": "Orange"},
        {"label": _("With Errors"), "value": errors, "datatype": "Int", "indicator": "Red"},
        {"label": _("Oldest Pending (days)"), "value": oldest_pending, "datatype": "Int", "indicator": "Red"},
        {"label": _("Auto Processed %"), "value": auto_pct, "datatype": "Percent", "indicator": "Green"},
        {"label": _("Total"), "value": total, "datatype": "Int", "indicator": "Grey"},
    ]


def _chart(rows: list[dict]) -> dict | None:
    if not rows:
        return None

    by_date_status: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        d = str(r.get("date"))
        by_date_status[d][r["status"]] += 1

    dates = sorted(by_date_status.keys())
    statuses = ["Pending", "Auto Processed", "Processed", "Rejected"]
    datasets = [{"name": s, "values": [by_date_status[d].get(s, 0) for d in dates]} for s in statuses]

    return {
        "data": {"labels": dates, "datasets": datasets},
        "type": "bar",
        "colors": ["#FF8C42", "#2ECC71", "#3498DB", "#E74C3C"],
        "barOptions": {"stacked": True},
    }
