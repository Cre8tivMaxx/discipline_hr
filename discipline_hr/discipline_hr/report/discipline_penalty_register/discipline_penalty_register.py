# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

DOCSTATUS_LABEL = {0: "Draft", 1: "Submitted", 2: "Cancelled"}


def execute(filters: dict | None = None) -> tuple[list[dict], list[dict], None, None, list[dict]]:
    filters = filters or {}
    _validate_filters(filters)

    columns = _columns()
    rows = _fetch_rows(filters)
    _enrich(rows)
    summary = _report_summary(rows)

    return columns, rows, None, None, summary


def _validate_filters(filters: dict) -> None:
    if not filters.get("company"):
        frappe.throw(_("Company is required"))
    if not (filters.get("from_date") and filters.get("to_date")):
        frappe.throw(_("From Date and To Date are required"))


def _columns() -> list[dict]:
    return [
        {"label": _("Violation Date"), "fieldname": "violation_date", "fieldtype": "Date", "width": 110},
        {
            "label": _("Penalty"),
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "Discipline Penalty",
            "width": 150,
        },
        {"label": _("Docstatus"), "fieldname": "docstatus_label", "fieldtype": "Data", "width": 100},
        {"label": _("Type"), "fieldname": "penalty_status", "fieldtype": "Data", "width": 90},
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
        {"label": _("Violation #"), "fieldname": "violation_number", "fieldtype": "Int", "width": 90},
        {"label": _("Period Start"), "fieldname": "start_period", "fieldtype": "Date", "width": 100},
        {"label": _("Period End"), "fieldname": "end_period", "fieldtype": "Date", "width": 100},
        {
            "label": _("Shift"),
            "fieldname": "shift_type",
            "fieldtype": "Link",
            "options": "Shift Type",
            "width": 130,
        },
        {"label": _("Grace Consumed"), "fieldname": "grace_consumed", "fieldtype": "Int", "width": 110},
        {"label": _("Penalty Minutes"), "fieldname": "penalty_minutes", "fieldtype": "Int", "width": 110},
        {"label": _("Penalty Amount"), "fieldname": "penalty_amount", "fieldtype": "Currency", "width": 120},
        {
            "label": _("Salary Component"),
            "fieldname": "salary_component",
            "fieldtype": "Link",
            "options": "Salary Component",
            "width": 150,
        },
        {
            "label": _("Attendance Policy"),
            "fieldname": "attendance_penalty_policy",
            "fieldtype": "Link",
            "options": "Attendance Penalty Policy",
            "width": 150,
        },
        {
            "label": _("Absence Policy"),
            "fieldname": "absence_penalty_policy",
            "fieldtype": "Link",
            "options": "Absence Penalty Policy",
            "width": 150,
        },
        {
            "label": _("Attendance"),
            "fieldname": "attendance",
            "fieldtype": "Link",
            "options": "Attendance",
            "width": 140,
        },
        {
            "label": _("Permission"),
            "fieldname": "attendance_pre_authorization",
            "fieldtype": "Link",
            "options": "Attendance Pre-Authorization",
            "width": 150,
        },
        {
            "label": _("Grace Ledger"),
            "fieldname": "employee_grace_ledger",
            "fieldtype": "Link",
            "options": "Employee Grace Ledger",
            "width": 150,
        },
        {"label": _("Has Error"), "fieldname": "has_error", "fieldtype": "Check", "width": 90},
        {"label": _("Error Log"), "fieldname": "error_log", "fieldtype": "Data", "width": 220},
        {"label": _("Created On"), "fieldname": "creation", "fieldtype": "Datetime", "width": 150},
    ]


def _fetch_rows(filters: dict) -> list[dict]:
    conditions = ["dp.violation_date BETWEEN %(from_date)s AND %(to_date)s", "emp.company = %(company)s"]
    params: dict[str, Any] = {
        "from_date": filters["from_date"],
        "to_date": filters["to_date"],
        "company": filters["company"],
    }

    if filters.get("employee"):
        conditions.append("dp.employee = %(employee)s")
        params["employee"] = filters["employee"]
    if filters.get("department"):
        conditions.append("emp.department = %(department)s")
        params["department"] = filters["department"]
    if filters.get("shift"):
        conditions.append("att.shift = %(shift)s")
        params["shift"] = filters["shift"]
    if filters.get("salary_component"):
        conditions.append("dp.salary_component = %(salary_component)s")
        params["salary_component"] = filters["salary_component"]
    if filters.get("penalty_status"):
        conditions.append("dp.penalty_status = %(penalty_status)s")
        params["penalty_status"] = filters["penalty_status"]
    if filters.get("attendance_penalty_policy"):
        conditions.append("dp.attendance_penalty_policy = %(policy)s")
        params["policy"] = filters["attendance_penalty_policy"]
    if filters.get("docstatus") not in (None, ""):
        conditions.append("dp.docstatus = %(docstatus)s")
        params["docstatus"] = int(filters["docstatus"])
    if filters.get("has_error"):
        conditions.append("(dp.error_log IS NOT NULL AND dp.error_log != '')")

    where = " AND ".join(conditions)
    query = f"""
        SELECT
            dp.name,
            dp.docstatus,
            dp.violation_date,
            dp.penalty_status,
            dp.employee,
            dp.employee_name,
            emp.department,
            dp.violation_number,
            dp.start_period,
            dp.end_period,
            att.shift AS shift_type,
            dp.grace_consumed,
            dp.penalty_minutes,
            dp.penalty_amount,
            dp.salary_component,
            dp.attendance_penalty_policy,
            dp.absence_penalty_policy,
            dp.attendance,
            dp.attendance_pre_authorization,
            dp.employee_grace_ledger,
            dp.error_log,
            dp.creation
        FROM `tabDiscipline Penalty` dp
        LEFT JOIN `tabEmployee` emp ON emp.name = dp.employee
        LEFT JOIN `tabAttendance` att ON att.name = dp.attendance
        WHERE {where}
        ORDER BY dp.violation_date DESC, dp.creation DESC
    """
    return frappe.db.sql(query, params, as_dict=True)


def _enrich(rows: list[dict]) -> None:
    for r in rows:
        r["docstatus_label"] = DOCSTATUS_LABEL.get(r.get("docstatus"), "")
        r["has_error"] = 1 if (r.get("error_log") or "").strip() else 0

        if r.get("error_log"):
            r["error_log"] = (r["error_log"] or "").splitlines()[0][:120]

        if r["has_error"]:
            r["_style_error_log"] = "color: var(--red-500); font-weight: 600;"
            r["_style_name"] = "color: var(--red-500);"

        if r.get("docstatus") == 2:
            r["_style_docstatus_label"] = "color: var(--text-muted); text-decoration: line-through;"
            for fn in ("name", "employee_name", "penalty_amount"):
                r.setdefault(f"_style_{fn}", "color: var(--text-muted);")
        elif r.get("docstatus") == 0:
            r["_style_docstatus_label"] = "color: var(--orange-500); font-weight: 600;"
        else:
            r["_style_docstatus_label"] = "color: var(--green-600); font-weight: 600;"

        if (r.get("penalty_amount") or 0) > 0 and r.get("docstatus") != 2:
            r["_style_penalty_amount"] = "color: var(--red-500); font-weight: 600;"


def _report_summary(rows: list[dict]) -> list[dict]:
    if not rows:
        return []

    total = len(rows)
    submitted = sum(1 for r in rows if r.get("docstatus") == 1)
    cancelled = sum(1 for r in rows if r.get("docstatus") == 2)
    with_errors = sum(1 for r in rows if r.get("has_error"))
    total_amount = sum(float(r.get("penalty_amount") or 0) for r in rows if r.get("docstatus") != 2)
    total_minutes = sum((r.get("penalty_minutes") or 0) for r in rows if r.get("docstatus") != 2)
    currency = frappe.defaults.get_global_default("currency") or "USD"

    return [
        {"label": _("Total Penalties"), "value": total, "datatype": "Int", "indicator": "Grey"},
        {"label": _("Submitted"), "value": submitted, "datatype": "Int", "indicator": "Green"},
        {"label": _("Cancelled"), "value": cancelled, "datatype": "Int", "indicator": "Grey"},
        {"label": _("With Errors"), "value": with_errors, "datatype": "Int", "indicator": "Red"},
        {
            "label": _("Total Penalty Minutes"),
            "value": total_minutes,
            "datatype": "Int",
            "indicator": "Orange",
        },
        {
            "label": _("Total Penalty Amount"),
            "value": total_amount,
            "datatype": "Currency",
            "currency": currency,
            "indicator": "Red",
        },
    ]
