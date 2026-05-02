# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections import defaultdict
from typing import Any

import frappe
from frappe import _
from frappe.utils import getdate, today

STATUS_INDICATOR = {
    "Draft": "color: var(--text-muted);",
    "Pending Approval": "color: var(--orange-500); font-weight: 600;",
    "Approved": "color: var(--blue-500); font-weight: 600;",
    "Consumed": "color: var(--green-600); font-weight: 600;",
    "Rejected": "color: var(--red-500); font-weight: 600;",
    "Expired": "color: var(--text-muted); font-weight: 600;",
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
            "label": _("Pre-Authorization"),
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "Attendance Pre-Authorization",
            "width": 170,
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
        {"label": _("Kind"), "fieldname": "kind", "fieldtype": "Data", "width": 80},
        {"label": _("Minutes"), "fieldname": "minutes", "fieldtype": "Int", "width": 90},
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
        {"label": _("Reason"), "fieldname": "reason", "fieldtype": "Data", "width": 200},
        {"label": _("Created On"), "fieldname": "creation", "fieldtype": "Datetime", "width": 150},
    ]


def _fetch_rows(filters: dict) -> list[dict]:
    conditions = ["pa.date BETWEEN %(from_date)s AND %(to_date)s", "emp.company = %(company)s"]
    params: dict[str, Any] = {
        "from_date": filters["from_date"],
        "to_date": filters["to_date"],
        "company": filters["company"],
    }

    if filters.get("status"):
        statuses = filters["status"] if isinstance(filters["status"], list) else [filters["status"]]
        conditions.append("pa.status IN %(statuses)s")
        params["statuses"] = tuple(statuses)
    if filters.get("department"):
        conditions.append("emp.department = %(department)s")
        params["department"] = filters["department"]
    if filters.get("shift"):
        conditions.append("pa.shift_type = %(shift)s")
        params["shift"] = filters["shift"]
    if filters.get("employee"):
        conditions.append("pa.employee = %(employee)s")
        params["employee"] = filters["employee"]
    if filters.get("kind"):
        conditions.append("pa.kind = %(kind)s")
        params["kind"] = filters["kind"]
    if filters.get("stuck_days"):
        conditions.append(
            "(pa.status = 'Pending Approval' AND DATEDIFF(%(today)s, DATE(pa.creation)) >= %(stuck_days)s)"
        )
        params["today"] = today()
        params["stuck_days"] = int(filters["stuck_days"])

    where = " AND ".join(conditions)
    query = f"""
        SELECT
            pa.name,
            pa.status,
            pa.date,
            pa.creation,
            pa.employee,
            pa.employee_name,
            emp.department,
            pa.shift_type,
            pa.minutes,
            pa.kind,
            pa.attendance,
            pa.reason,
            dp.name AS discipline_penalty
        FROM `tabAttendance Pre-Authorization` pa
        LEFT JOIN `tabEmployee` emp ON emp.name = pa.employee
        LEFT JOIN `tabDiscipline Penalty` dp ON dp.attendance_pre_authorization = pa.name AND dp.docstatus < 2
        WHERE {where}
        ORDER BY
            CASE pa.status
                WHEN 'Pending Approval' THEN 0
                WHEN 'Approved' THEN 1
                WHEN 'Draft' THEN 2
                WHEN 'Consumed' THEN 3
                ELSE 4
            END,
            pa.creation ASC
    """
    return frappe.db.sql(query, params, as_dict=True)


def _enrich(rows: list[dict]) -> None:
    today_d = getdate(today())
    for r in rows:
        creation = r.get("creation")
        age = (today_d - getdate(creation)).days if creation else 0
        r["age_days"] = age

        status = r.get("status")
        if status in STATUS_INDICATOR:
            r["_style_status"] = STATUS_INDICATOR[status]

        if status == "Pending Approval":
            if age >= 5:
                r["_style_age_days"] = "color: var(--red-500); font-weight: 700;"
            elif age >= 2:
                r["_style_age_days"] = "color: var(--orange-500); font-weight: 600;"


def _report_summary(rows: list[dict]) -> list[dict]:
    if not rows:
        return []

    total = len(rows)
    pending = sum(1 for r in rows if r["status"] == "Pending Approval")
    approved = sum(1 for r in rows if r["status"] == "Approved")
    consumed = sum(1 for r in rows if r["status"] == "Consumed")
    oldest_pending = max((r["age_days"] for r in rows if r["status"] == "Pending Approval"), default=0)

    return [
        {"label": _("Pending Approval"), "value": pending, "datatype": "Int", "indicator": "Orange"},
        {"label": _("Approved"), "value": approved, "datatype": "Int", "indicator": "Blue"},
        {"label": _("Consumed"), "value": consumed, "datatype": "Int", "indicator": "Green"},
        {
            "label": _("Oldest Pending (days)"),
            "value": oldest_pending,
            "datatype": "Int",
            "indicator": "Red",
        },
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
    statuses = ["Pending Approval", "Approved", "Consumed", "Rejected", "Expired"]
    datasets = [{"name": s, "values": [by_date_status[d].get(s, 0) for d in dates]} for s in statuses]

    return {
        "data": {"labels": dates, "datasets": datasets},
        "type": "bar",
        "colors": ["#FF8C42", "#3498DB", "#2ECC71", "#E74C3C", "#95A5A6"],
        "barOptions": {"stacked": True},
    }
