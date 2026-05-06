# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe import _


def execute(filters: dict | None = None) -> tuple[list[dict], list[dict], None, dict, list[dict]]:
    filters = filters or {}
    _validate_filters(filters)

    columns = _columns()
    rows = _fetch_rows(filters)
    summary = _report_summary(rows)
    chart = _chart(rows)

    return columns, rows, None, chart, summary


def _validate_filters(filters: dict) -> None:
    if not filters.get("company"):
        frappe.throw(_("Company is required"))
    if not (filters.get("period_start") and filters.get("period_end")):
        if filters.get("shift"):
            shift = frappe.get_cached_doc("Shift Type", filters["shift"])
            filters["period_start"] = shift.get("custom_period_start_date")
            filters["period_end"] = shift.get("custom_period_end_date")
    if not (filters.get("period_start") and filters.get("period_end")):
        frappe.throw(_("Period Start and Period End are required (or pick a Shift with a configured period)"))


def _columns() -> list[dict]:
    return [
        {
            "label": _("Employee"),
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 130,
        },
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
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
        {"label": _("Period Start"), "fieldname": "period_start", "fieldtype": "Date", "width": 100},
        {"label": _("Period End"), "fieldname": "period_end", "fieldtype": "Date", "width": 100},
        {
            "label": _("Salary Component"),
            "fieldname": "salary_component",
            "fieldtype": "Link",
            "options": "Salary Component",
            "width": 150,
        },
        {"label": _("Total Violations"), "fieldname": "total_violations", "fieldtype": "Int", "width": 110},
        {"label": _("Late"), "fieldname": "late_violations", "fieldtype": "Int", "width": 80},
        {"label": _("Absent"), "fieldname": "absent_violations", "fieldtype": "Int", "width": 80},
        {
            "label": _("Penalty Minutes"),
            "fieldname": "total_penalty_minutes",
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "label": _("Penalty Amount"),
            "fieldname": "total_penalty_amount",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "label": _("Salary Slip"),
            "fieldname": "salary_slip",
            "fieldtype": "Link",
            "options": "Salary Slip",
            "width": 150,
        },
    ]


def _fetch_rows(filters: dict) -> list[dict]:
    conditions = [
        "dp.start_period <= %(period_end)s",
        "dp.end_period >= %(period_start)s",
        "emp.company = %(company)s",
    ]
    params: dict[str, Any] = {
        "period_start": filters["period_start"],
        "period_end": filters["period_end"],
        "company": filters["company"],
    }

    if filters.get("docstatus") not in (None, ""):
        conditions.append("dp.docstatus = %(docstatus)s")
        params["docstatus"] = int(filters["docstatus"])
    else:
        conditions.append("dp.docstatus < 2")

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

    where = " AND ".join(conditions)
    query = f"""
        SELECT
            dp.employee,
            dp.employee_name,
            emp.department,
            att.shift AS shift_type,
            dp.start_period AS period_start,
            dp.end_period   AS period_end,
            dp.salary_component,
            COUNT(*)                                                       AS total_violations,
            SUM(CASE WHEN dp.penalty_status = 'Present' THEN 1 ELSE 0 END) AS late_violations,
            SUM(CASE WHEN dp.penalty_status = 'Absent'  THEN 1 ELSE 0 END) AS absent_violations,
            SUM(COALESCE(dp.penalty_minutes, 0))                           AS total_penalty_minutes,
            SUM(COALESCE(dp.penalty_amount, 0))                            AS total_penalty_amount,
            (
                SELECT ss.name FROM `tabSalary Slip` ss
                WHERE ss.employee = dp.employee
                  AND ss.start_date <= dp.end_period
                  AND ss.end_date   >= dp.start_period
                  AND ss.docstatus = 1
                ORDER BY ss.start_date DESC
                LIMIT 1
            ) AS salary_slip
        FROM `tabDiscipline Penalty` dp
        LEFT JOIN `tabEmployee` emp ON emp.name = dp.employee
        LEFT JOIN `tabAttendance` att ON att.name = dp.attendance
        WHERE {where}
        GROUP BY dp.employee, dp.start_period, dp.end_period, dp.salary_component, att.shift
        ORDER BY total_penalty_amount DESC, dp.employee
    """
    rows = frappe.db.sql(query, params, as_dict=True)

    for r in rows:
        if (r.get("total_penalty_amount") or 0) > 0:
            r["_style_total_penalty_amount"] = "color: var(--red-500); font-weight: 600;"
        if (r.get("absent_violations") or 0) > 0:
            r["_style_absent_violations"] = "color: var(--red-500); font-weight: 600;"

    return rows


def _report_summary(rows: list[dict]) -> list[dict]:
    if not rows:
        return []

    employees = {r["employee"] for r in rows}
    total_minutes = sum((r.get("total_penalty_minutes") or 0) for r in rows)
    total_amount = sum(float(r.get("total_penalty_amount") or 0) for r in rows)
    avg_amount = round(total_amount / len(employees), 2) if employees else 0
    currency = frappe.defaults.get_global_default("currency") or "USD"

    return [
        {
            "label": _("Employees with Penalties"),
            "value": len(employees),
            "datatype": "Int",
            "indicator": "Grey",
        },
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
        {
            "label": _("Avg per Employee"),
            "value": avg_amount,
            "datatype": "Currency",
            "currency": currency,
            "indicator": "Blue",
        },
    ]


def _chart(rows: list[dict]) -> dict | None:
    if not rows:
        return None

    by_employee: dict[str, float] = {}
    label_by_employee: dict[str, str] = {}
    for r in rows:
        emp = r["employee"]
        by_employee[emp] = by_employee.get(emp, 0.0) + float(r.get("total_penalty_amount") or 0)
        label_by_employee[emp] = r.get("employee_name") or emp

    top = sorted(by_employee.items(), key=lambda kv: kv[1], reverse=True)[:10]
    labels = [label_by_employee[e] for e, _v in top]
    values = [round(v, 2) for _e, v in top]

    return {
        "data": {
            "labels": labels,
            "datasets": [{"name": _("Penalty Amount"), "values": values}],
        },
        "type": "bar",
        "colors": ["#E74C3C"],
        "barOptions": {"stacked": False},
    }
