"""Service layer for the Attendance Pre-Authorization model.

The flow is now driven entirely from a submitted Attendance:

1. ``apply_pre_authorization_and_penalty`` runs on ``Attendance.before_submit``.
2. It resolves Approved pre-authorizations matching the (employee, date, slice).
3. Matching minutes are consumed atomically; surplus minutes are penalized via
   the ``pre_authorization_surplus_policy`` configured in Discipline HR Settings.
4. When no pre-auth applies, the original grace-ledger flow runs unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import frappe
from frappe.utils import cint, today

from discipline_hr.discipline_hr.doctype.employee_grace_ledger.employee_grace_ledger import (
    EmployeeGraceLedger,
)
from discipline_hr.services.utils import _log, count_prior_violations


@dataclass
class _AttendanceContext:
    employee: str
    attendance: str | None
    minutes: float
    shift_type: str | None
    date: str


def _context_from_attendance(attendance_doc) -> _AttendanceContext:
    shift = frappe.get_cached_doc("Shift Type", attendance_doc.shift)
    minutes = max(cint(shift.custom_minimum_grace_minutes), cint(attendance_doc.custom_penalty_minutes))
    return _AttendanceContext(
        employee=attendance_doc.employee,
        attendance=attendance_doc.name,
        minutes=minutes,
        shift_type=attendance_doc.shift,
        date=str(attendance_doc.attendance_date),
    )


def apply_pre_authorization_and_penalty(doc, method=None):
    """Resolve pre-auth, then write a grace ledger or surplus penalty for a submitted Attendance."""
    if not cint(doc.custom_penalty_minutes):
        return

    try:
        late = cint(doc.custom_late_after_grace_minutes)
        early = cint(doc.custom_early_after_grace_minutes)

        surplus_late, surplus_early, consumed = _apply_preauth_and_compute_remainder(doc, late, early)

        if consumed:
            doc.custom_attendance_pre_authorization = consumed[0]
            surplus = surplus_late + surplus_early
            if surplus > 0:
                _create_surplus_penalty(doc, surplus, consumed[0])
            return

        ctx = _context_from_attendance(doc)
        _create_grace_ledger(ctx)
    except Exception:
        _log(
            "exception",
            "pre_authorization_pipeline_failed",
            attendance=doc.name,
            employee=doc.employee,
        )
        frappe.db.set_value(
            "Attendance",
            doc.name,
            "custom_error_log",
            frappe.get_traceback(),
            update_modified=False,
        )


def _apply_preauth_and_compute_remainder(
    attendance_doc, late_minutes: int, early_minutes: int
) -> tuple[int, int, list[str]]:
    """Consume matching Approved pre-auths atomically.

    Returns ``(surplus_late, surplus_early, consumed_names)``. A pre-auth with
    ``kind=Both`` is consumed once against the combined late+early minutes; a
    ``kind=Late`` or ``kind=Early`` pre-auth is consumed against its own slice.

    Atomicity comes from a guarded SQL UPDATE: two concurrent submits race on
    the same ``WHERE status='Approved'`` predicate and only one wins.
    """
    consumed: list[str] = []

    both = _find_active_pre_authorization(attendance_doc.employee, attendance_doc.attendance_date, "Both")
    if both:
        preauth_minutes = cint(frappe.db.get_value("Attendance Pre-Authorization", both, "minutes"))
        if _consume_pre_authorization(both, attendance_doc.name):
            total = late_minutes + early_minutes
            covered = min(total, preauth_minutes)
            late_covered = min(late_minutes, covered)
            early_covered = covered - late_covered
            consumed.append(both)
            return (late_minutes - late_covered, early_minutes - early_covered, consumed)

    surplus_late = late_minutes
    if late_minutes > 0:
        late_preauth = _find_active_pre_authorization(
            attendance_doc.employee, attendance_doc.attendance_date, "Late"
        )
        if late_preauth and _consume_pre_authorization(late_preauth, attendance_doc.name):
            preauth_minutes = cint(
                frappe.db.get_value("Attendance Pre-Authorization", late_preauth, "minutes")
            )
            surplus_late = max(0, late_minutes - preauth_minutes)
            consumed.append(late_preauth)

    surplus_early = early_minutes
    if early_minutes > 0:
        early_preauth = _find_active_pre_authorization(
            attendance_doc.employee, attendance_doc.attendance_date, "Early"
        )
        if early_preauth and _consume_pre_authorization(early_preauth, attendance_doc.name):
            preauth_minutes = cint(
                frappe.db.get_value("Attendance Pre-Authorization", early_preauth, "minutes")
            )
            surplus_early = max(0, early_minutes - preauth_minutes)
            consumed.append(early_preauth)

    return surplus_late, surplus_early, consumed


def _find_active_pre_authorization(employee: str, date, kind: str) -> str | None:
    """Return an Approved pre-auth name matching the slice, or ``None``."""
    return frappe.db.get_value(
        "Attendance Pre-Authorization",
        {
            "employee": employee,
            "date": date,
            "kind": kind,
            "status": "Approved",
        },
        "name",
    )


def _consume_pre_authorization(name: str, attendance: str) -> bool:
    """Atomically flip status Approved → Consumed. Returns True if this caller won the race."""
    frappe.db.sql(
        """
        UPDATE `tabAttendance Pre-Authorization`
        SET status = 'Consumed', attendance = %(attendance)s, modified = NOW()
        WHERE name = %(name)s AND status = 'Approved'
        """,
        {"name": name, "attendance": attendance},
    )
    affected = frappe.db._cursor.rowcount
    if affected:
        _log("info", "pre_authorization_consumed", pre_authorization=name, attendance=attendance)
    return bool(affected)


def _create_surplus_penalty(attendance_doc, surplus_minutes: int, pre_authorization: str) -> None:
    """Penalize minutes beyond the consumed pre-authorization. Skips the grace ledger."""
    config = frappe.get_cached_doc("Discipline HR Settings")
    shift_doc = frappe.get_cached_doc("Shift Type", attendance_doc.shift)
    surplus_policy = (
        shift_doc.get("custom_pre_authorization_surplus_policy")
        or config.pre_authorization_surplus_policy
    )
    if not surplus_policy:
        _log(
            "warning",
            "no_surplus_policy_configured",
            attendance=attendance_doc.name,
            pre_authorization=pre_authorization,
        )
        return

    if frappe.db.exists(
        "Discipline Penalty",
        {"attendance": attendance_doc.name, "docstatus": ("!=", 2)},
    ):
        _log("info", "duplicate_surplus_penalty_skipped", attendance=attendance_doc.name)
        return

    penalty = frappe.new_doc("Discipline Penalty")
    penalty.employee = attendance_doc.employee
    penalty.attendance = attendance_doc.name
    penalty.attendance_pre_authorization = pre_authorization
    penalty.violation_date = str(attendance_doc.attendance_date)
    penalty.start_period = shift_doc.custom_period_start_date
    penalty.end_period = shift_doc.custom_period_end_date
    penalty.penalty_status = attendance_doc.status
    penalty.violation_number = 1 + count_prior_violations(
        attendance_doc.employee,
        shift_doc.custom_period_start_date,
        shift_doc.custom_period_end_date,
        attendance_doc.status,
    )
    penalty.attendance_penalty_policy = surplus_policy
    penalty.salary_component = shift_doc.custom_salary_component or config.salary_component or ""
    penalty.penalty_minutes = surplus_minutes
    penalty.grace_consumed = 0
    penalty.status = "Auto Processed" if cint(config.auto_process_attendance_penalty) else "Pending"
    penalty.insert(ignore_if_duplicate=True, ignore_permissions=True)
    _log(
        "info",
        "surplus_penalty_created",
        employee=attendance_doc.employee,
        surplus_minutes=surplus_minutes,
        pre_authorization=pre_authorization,
    )


def _create_attendance_penalty(ctx: _AttendanceContext, ledger, config):
    """Create a Discipline Penalty from a grace ledger entry, when grace is exhausted."""
    if ledger.penalty_minutes <= 0:
        _log(
            "info",
            "no_penalty_within_grace",
            employee=ctx.employee,
            remaining_grace_before_consume=ledger.remaining_minutes_before_consume,
            penalty_minutes=ledger.penalty_minutes,
        )
        return

    if frappe.db.exists(
        "Discipline Penalty",
        {"attendance": ctx.attendance, "docstatus": ("!=", 2)},
    ):
        _log(
            "info",
            "duplicate_discipline_penalty",
            employee=ctx.employee,
            date=ctx.date,
            attendance=ctx.attendance,
        )
        return

    shift_doc = frappe.get_cached_doc("Shift Type", ctx.shift_type)
    attendance = frappe.get_cached_doc("Attendance", ctx.attendance) if ctx.attendance else None

    penalty = frappe.new_doc("Discipline Penalty")
    penalty.employee = ctx.employee
    penalty.violation_date = ctx.date or str(today())
    penalty.start_period = ledger.period_start
    penalty.end_period = ledger.period_end

    if attendance:
        penalty.attendance = attendance.name
    penalty.penalty_status = attendance.status if attendance else "Present"
    penalty.violation_number = 1 + count_prior_violations(
        ctx.employee,
        ledger.period_start,
        ledger.period_end,
        penalty.penalty_status,
    )

    penalty.attendance_penalty_policy = (
        shift_doc.custom_attendance_penalty_policy or config.attendance_penalty_policy
    )
    penalty.salary_component = shift_doc.custom_salary_component or config.salary_component or ""
    penalty.employee_grace_ledger = ledger.name
    penalty.grace_consumed = ledger.consumed_minutes
    penalty.penalty_minutes = ledger.penalty_minutes
    penalty.status = "Auto Processed" if cint(config.auto_process_attendance_penalty) else "Pending"
    penalty.insert(ignore_if_duplicate=True, ignore_permissions=True)
    return penalty


def _create_grace_ledger(ctx: _AttendanceContext):
    """Insert an Employee Grace Ledger entry and trigger penalty creation if needed.

    Penalty math (delta-of-cumulative-overflow):
        prior_total    = SUM(consumed_minutes from prior rows in this period)
        prior_overflow = max(0, prior_total - allowed)
        new_total      = prior_total + this.consumed_minutes
        new_overflow   = max(0, new_total - allowed)
        penalty_minutes = new_overflow - prior_overflow

    This bills each attendance only for the minutes it pushes the employee
    further past the period's grace pool — no compensating ledger rows needed.
    """
    if _ignore_grace_ledger_duplicates(ctx):
        return

    shift = frappe.get_cached_doc("Shift Type", ctx.shift_type)
    allowed = cint(shift.custom_total_allowed_grace_minutes)
    prior_total = cint(
        frappe.db.get_value(
            "Employee Grace Ledger",
            filters={
                "employee": ctx.employee,
                "period_start": shift.custom_period_start_date,
                "period_end": shift.custom_period_end_date,
            },
            fieldname="sum(consumed_minutes)",
        )
        or 0
    )
    prior_overflow = max(0, prior_total - allowed)
    new_total = prior_total + ctx.minutes
    new_overflow = max(0, new_total - allowed)

    ledger = cast(EmployeeGraceLedger, frappe.new_doc("Employee Grace Ledger"))
    _log("debug", "creating_grace_ledger", employee=ctx.employee, minutes=ctx.minutes)
    ledger.employee = ctx.employee
    ledger.attendance = ctx.attendance
    ledger.period_start = shift.custom_period_start_date
    ledger.period_end = shift.custom_period_end_date
    ledger.allowed_minutes = allowed
    ledger.consumed_minutes = ctx.minutes
    ledger.remaining_minutes_before_consume = max(0, allowed - prior_total)
    ledger.remaining_minutes = max(0, allowed - new_total)
    ledger.penalty_minutes = new_overflow - prior_overflow
    ledger.remarks = "Auto-created from Attendance"
    ledger.date = ctx.date

    try:
        ledger.insert(ignore_permissions=True)
        _log("info", "ledger_inserted", employee=ctx.employee, ledger=ledger.name)
    except Exception:
        _log(
            "exception",
            "grace_ledger_creation_failed",
            employee=ctx.employee,
            attendance=ctx.attendance,
            date=ctx.date,
            minutes=ctx.minutes,
        )
        if ctx.attendance:
            frappe.db.set_value(
                "Attendance",
                ctx.attendance,
                "custom_error_log",
                frappe.get_traceback(),
                update_modified=False,
            )
        return

    insert_attendance_penalty(ledger, ctx)
    return ledger


def _ignore_grace_ledger_duplicates(ctx: _AttendanceContext) -> bool:
    """Skip ledger creation when an entry for this attendance already exists."""
    if not ctx.attendance:
        return False
    existing = frappe.db.exists(
        "Employee Grace Ledger",
        {"employee": ctx.employee, "attendance": ctx.attendance},
    )
    if existing:
        _log(
            "info",
            "grace_ledger_already_exists",
            employee=ctx.employee,
            attendance=ctx.attendance,
        )
        return True
    return False


def insert_attendance_penalty(doc: EmployeeGraceLedger, ctx: _AttendanceContext) -> None:
    try:
        config = frappe.get_cached_doc("Discipline HR Settings")
        penalty = _create_attendance_penalty(ctx, doc, config)
        if penalty is not None:
            frappe.db.set_value(
                "Employee Grace Ledger",
                doc.name,
                "discipline_penalty",
                penalty.name,
                update_modified=False,
            )
        frappe.db.set_value("Employee Grace Ledger", doc.name, "error_log", None, update_modified=False)
    except Exception:
        _log(
            "exception",
            "discipline_penalty_creation_failed",
            employee=ctx.employee,
            attendance=ctx.attendance,
            date=ctx.date,
            minutes=ctx.minutes,
        )
        frappe.db.set_value(
            "Employee Grace Ledger",
            doc.name,
            "error_log",
            frappe.get_traceback(),
            update_modified=False,
        )


def retry_discipline_penalty(doc: EmployeeGraceLedger) -> None:
    """Re-run penalty creation for an existing grace ledger entry."""
    frappe.db.set_value("Employee Grace Ledger", doc.name, "error_log", None, update_modified=False)
    doc.reload()
    if not doc.attendance:
        _log("warning", "grace_ledger_retry_skipped_no_attendance", ledger=doc.name)
        return
    ctx = _context_from_attendance(frappe.get_doc("Attendance", doc.attendance))
    insert_attendance_penalty(doc, ctx)
