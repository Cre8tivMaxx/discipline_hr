# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections import defaultdict
from typing import Any

import frappe
from frappe import _


def execute(filters: dict | None = None) -> tuple[list[dict], list[dict], None, dict, list[dict]]:
    filters = filters or {}
    _validate_filters(filters)

    columns = _columns()
    rows = _fetch_rows(filters)
    data = _build_grouped_rows(rows, filters)
    summary = _report_summary(rows)
    chart = _chart(rows)

    return columns, data, None, chart, summary


def _validate_filters(filters: dict) -> None:
    # Drill-down filters narrow to a single voucher; the period/shift become
    # unnecessary because the EGL row carries that context already.
    has_voucher = any(filters.get(k) for k in ("attendance", "discipline_penalty"))
    if has_voucher:
        return

    if not filters.get("company"):
        frappe.throw(_("Company is required"))
    if not filters.get("shift"):
        frappe.throw(_("Shift is required"))
    if not (filters.get("period_start") and filters.get("period_end")):
        shift = frappe.get_cached_doc("Shift Type", filters["shift"])
        filters["period_start"] = shift.get("custom_period_start_date")
        filters["period_end"] = shift.get("custom_period_end_date")
    if not (filters.get("period_start") and filters.get("period_end")):
        frappe.throw(_("Selected Shift Type has no period configured"))


def _columns() -> list[dict]:
    return [
        {"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {
            "label": _("Employee"),
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 130,
        },
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
        {"label": _("Allowed"), "fieldname": "allowed", "fieldtype": "Int", "width": 80},
        {"label": _("Before"), "fieldname": "before", "fieldtype": "Int", "width": 80},
        {"label": _("Consumed"), "fieldname": "consumed", "fieldtype": "Int", "width": 90},
        {"label": _("Remaining"), "fieldname": "remaining", "fieldtype": "Int", "width": 90},
        {"label": _("Penalty Minutes"), "fieldname": "penalty_minutes", "fieldtype": "Int", "width": 110},
        {"label": _("Penalty Amount"), "fieldname": "penalty_amount", "fieldtype": "Currency", "width": 120},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
        {
            "label": _("Department"),
            "fieldname": "department",
            "fieldtype": "Link",
            "options": "Department",
            "width": 140,
        },
        {
            "label": _("Shift"),
            "fieldname": "shift",
            "fieldtype": "Link",
            "options": "Shift Type",
            "width": 130,
        },
        {"label": _("Period Start"), "fieldname": "period_start", "fieldtype": "Date", "width": 100},
        {"label": _("Period End"), "fieldname": "period_end", "fieldtype": "Date", "width": 100},
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
            "width": 140,
        },
    ]


def _fetch_rows(filters: dict) -> list[dict]:
    conditions: list[str] = []
    params: dict[str, Any] = {}

    drill_down = any(filters.get(k) for k in ("attendance", "discipline_penalty"))

    if filters.get("attendance"):
        conditions.append("egl.attendance = %(attendance)s")
        params["attendance"] = filters["attendance"]
    if filters.get("discipline_penalty"):
        conditions.append("egl.discipline_penalty = %(discipline_penalty)s")
        params["discipline_penalty"] = filters["discipline_penalty"]

    if filters.get("employee"):
        conditions.append("egl.employee = %(employee)s")
        params["employee"] = filters["employee"]

    if not drill_down:
        if filters.get("period_start") and filters.get("period_end"):
            conditions += ["egl.period_start = %(period_start)s", "egl.period_end = %(period_end)s"]
            params["period_start"] = filters["period_start"]
            params["period_end"] = filters["period_end"]
        if filters.get("shift"):
            conditions.append("att.shift = %(shift)s")
            params["shift"] = filters["shift"]
        if filters.get("company"):
            conditions.append("emp.company = %(company)s")
            params["company"] = filters["company"]
        if filters.get("department"):
            conditions.append("emp.department = %(department)s")
            params["department"] = filters["department"]

    if not conditions:
        return []

    where = " AND ".join(conditions)
    query = f"""
		SELECT
			egl.name                              AS egl_name,
			egl.date                              AS posting_date,
			egl.creation                          AS creation,
			egl.employee                          AS employee,
			egl.employee_name                     AS employee_name,
			emp.department                        AS department,
			egl.attendance                        AS attendance,
			att.shift                             AS shift,
			egl.period_start                      AS period_start,
			egl.period_end                        AS period_end,
			egl.allowed_minutes                   AS allowed,
			egl.remaining_minutes_before_consume  AS `before`,
			egl.consumed_minutes                  AS consumed,
			egl.remaining_minutes                 AS remaining,
			egl.penalty_minutes                   AS penalty_minutes,
			dp.penalty_amount                     AS penalty_amount,
			egl.discipline_penalty                AS discipline_penalty,
			dp.status                             AS status
		FROM `tabEmployee Grace Ledger` egl
		LEFT JOIN `tabAttendance` att            ON att.name = egl.attendance
		LEFT JOIN `tabEmployee` emp              ON emp.name = egl.employee
		LEFT JOIN `tabDiscipline Penalty` dp     ON dp.name = egl.discipline_penalty
		WHERE {where}
		ORDER BY egl.employee, egl.date, egl.creation
	"""
    return frappe.db.sql(query, params, as_dict=True)


def _build_grouped_rows(rows: list[dict], filters: dict) -> list[dict]:
    """Insert opening/closing bold rows around each employee's movement rows."""
    output: list[dict] = []
    by_employee: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_employee[r["employee"]].append(r)

    for employee, employee_rows in by_employee.items():
        first = employee_rows[0]
        allowed = first.get("allowed") or 0

        period_start = filters.get("period_start") or first.get("period_start")
        period_end = filters.get("period_end") or first.get("period_end")
        shift = filters.get("shift") or first.get("shift")

        opening = _opening_row(first, allowed, period_start, period_end, shift)
        output.append(opening)

        total_consumed = 0
        total_penalty_minutes = 0
        total_penalty_amount = 0.0
        final_remaining = allowed

        for r in employee_rows:
            _apply_row_style(r, allowed)
            output.append(r)
            total_consumed += r.get("consumed") or 0
            total_penalty_minutes += r.get("penalty_minutes") or 0
            total_penalty_amount += float(r.get("penalty_amount") or 0)
            final_remaining = r.get("remaining") if r.get("remaining") is not None else final_remaining

        output.append(
            _closing_row(
                employee=employee,
                employee_name=first.get("employee_name"),
                department=first.get("department"),
                allowed=allowed,
                total_consumed=total_consumed,
                total_penalty_minutes=total_penalty_minutes,
                total_penalty_amount=total_penalty_amount,
                final_remaining=final_remaining,
                period_start=period_start,
                period_end=period_end,
                shift=shift,
            )
        )

    return output


def _opening_row(first: dict, allowed: int, period_start: Any, period_end: Any, shift: str | None) -> dict:
    return {
        "posting_date": period_start,
        "employee": first.get("employee"),
        "employee_name": first.get("employee_name"),
        "department": first.get("department"),
        "attendance": "",
        "shift": shift,
        "period_start": period_start,
        "period_end": period_end,
        "allowed": allowed,
        "before": allowed,
        "consumed": 0,
        "remaining": allowed,
        "penalty_minutes": 0,
        "penalty_amount": 0,
        "discipline_penalty": "",
        "status": _("Opening"),
        "_bold": 1,
    }


def _closing_row(
    *,
    employee: str,
    employee_name: str | None,
    department: str | None,
    allowed: int,
    total_consumed: int,
    total_penalty_minutes: int,
    total_penalty_amount: float,
    final_remaining: int,
    period_start: Any,
    period_end: Any,
    shift: str | None,
) -> dict:
    return {
        "posting_date": period_end,
        "employee": employee,
        "employee_name": employee_name,
        "department": department,
        "attendance": "",
        "shift": shift,
        "period_start": period_start,
        "period_end": period_end,
        "allowed": allowed,
        "before": "",
        "consumed": total_consumed,
        "remaining": final_remaining,
        "penalty_minutes": total_penalty_minutes,
        "penalty_amount": total_penalty_amount,
        "discipline_penalty": "",
        "status": _("Total"),
        "_bold": 1,
    }


def _apply_row_style(row: dict, allowed: int) -> None:
    remaining = row.get("remaining") or 0
    if allowed > 0:
        ratio = remaining / allowed
        if remaining == 0:
            row["_style_remaining"] = "color: var(--red-500); font-weight: 600;"
        elif ratio < 0.5:
            row["_style_remaining"] = "color: var(--orange-500); font-weight: 600;"
        else:
            row["_style_remaining"] = "color: var(--green-600); font-weight: 600;"

    if (row.get("penalty_amount") or 0) > 0:
        row["_style_penalty_amount"] = "color: var(--red-500); font-weight: 600;"


def _report_summary(rows: list[dict]) -> list[dict]:
    if not rows:
        return []

    allowed_by_employee = {r["employee"]: (r.get("allowed") or 0) for r in rows}
    total_allowed = sum(allowed_by_employee.values())
    total_consumed = sum((r.get("consumed") or 0) for r in rows)
    total_penalty_minutes = sum((r.get("penalty_minutes") or 0) for r in rows)
    total_penalty_amount = sum(float(r.get("penalty_amount") or 0) for r in rows)
    violation_count = sum(1 for r in rows if (r.get("penalty_minutes") or 0) > 0)
    currency = frappe.defaults.get_global_default("currency") or "USD"

    return [
        {"label": _("Total Allowed (min)"), "value": total_allowed, "datatype": "Int", "indicator": "Blue"},
        {
            "label": _("Total Consumed (min)"),
            "value": total_consumed,
            "datatype": "Int",
            "indicator": "Orange",
        },
        {
            "label": _("Total Penalty Minutes"),
            "value": total_penalty_minutes,
            "datatype": "Int",
            "indicator": "Red",
        },
        {
            "label": _("Total Penalty Amount"),
            "value": total_penalty_amount,
            "datatype": "Currency",
            "currency": currency,
            "indicator": "Red",
        },
        {"label": _("Violation Count"), "value": violation_count, "datatype": "Int", "indicator": "Grey"},
    ]


def _chart(rows: list[dict]) -> dict | None:
    if not rows:
        return None

    consumed_by_employee: dict[str, int] = defaultdict(int)
    label_by_employee: dict[str, str] = {}
    for r in rows:
        emp = r["employee"]
        consumed_by_employee[emp] += r.get("consumed") or 0
        label_by_employee[emp] = r.get("employee_name") or emp

    ordered = sorted(consumed_by_employee.items(), key=lambda kv: kv[1], reverse=True)
    labels = [label_by_employee[emp] for emp, _ in ordered]
    values = [val for _, val in ordered]

    return {
        "data": {
            "labels": labels,
            "datasets": [{"name": _("Consumed Minutes"), "values": values}],
        },
        "type": "bar",
        "colors": ["#FF8C42"],
        "barOptions": {"stacked": False},
    }
