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

    surplus = {"Late": late_minutes, "Early": early_minutes}
    for kind in ("Late", "Early"):
        if surplus[kind] <= 0:
            continue
        preauth = _find_active_pre_authorization(
            attendance_doc.employee, attendance_doc.attendance_date, kind
        )
        if preauth and _consume_pre_authorization(preauth, attendance_doc.name):
            preauth_minutes = cint(frappe.db.get_value("Attendance Pre-Authorization", preauth, "minutes"))
            surplus[kind] = max(0, surplus[kind] - preauth_minutes)
            consumed.append(preauth)

    return surplus["Late"], surplus["Early"], consumed


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


def _build_penalty(
    *,
    employee: str,
    attendance: str,
    violation_date: str,
    penalty_status: str,
    shift_doc,
    config,
    policy: str,
    penalty_minutes: int,
    grace_consumed: int = 0,
    extra: dict | None = None,
) -> object | None:
    """Insert a Discipline Penalty row, or return ``None`` if a duplicate exists.

    Centralises the field assignment shared by grace-ledger and pre-auth-surplus
    flows: violation period, violation number, salary component, status, and the
    auto-process flag from settings.
    """
    if frappe.db.exists("Discipline Penalty", {"attendance": attendance, "docstatus": ("!=", 2)}):
        _log("info", "duplicate_discipline_penalty", attendance=attendance, employee=employee)
        return None

    penalty = frappe.new_doc("Discipline Penalty")
    penalty.employee = employee
    penalty.attendance = attendance
    penalty.violation_date = violation_date
    penalty.start_period = shift_doc.custom_period_start_date
    penalty.end_period = shift_doc.custom_period_end_date
    penalty.penalty_status = penalty_status
    penalty.violation_number = 1 + count_prior_violations(
        employee, shift_doc.custom_period_start_date, shift_doc.custom_period_end_date, penalty_status
    )
    penalty.attendance_penalty_policy = policy
    penalty.salary_component = shift_doc.custom_salary_component or config.salary_component or ""
    penalty.penalty_minutes = penalty_minutes
    penalty.grace_consumed = grace_consumed
    penalty.status = "Auto Processed" if cint(config.auto_process_attendance_penalty) else "Pending"

    for field, value in (extra or {}).items():
        setattr(penalty, field, value)

    penalty.insert(ignore_if_duplicate=True, ignore_permissions=True)
    return penalty


def _create_surplus_penalty(attendance_doc, surplus_minutes: int, pre_authorization: str) -> None:
    """Penalize minutes beyond the consumed pre-authorization. Skips the grace ledger."""
    config = frappe.get_cached_doc("Discipline HR Settings")
    shift_doc = frappe.get_cached_doc("Shift Type", attendance_doc.shift)
    surplus_policy = (
        shift_doc.get("custom_pre_authorization_surplus_policy") or config.pre_authorization_surplus_policy
    )
    if not surplus_policy:
        _log(
            "warning",
            "no_surplus_policy_configured",
            attendance=attendance_doc.name,
            pre_authorization=pre_authorization,
        )
        return

    penalty = _build_penalty(
        employee=attendance_doc.employee,
        attendance=attendance_doc.name,
        violation_date=str(attendance_doc.attendance_date),
        penalty_status=attendance_doc.status,
        shift_doc=shift_doc,
        config=config,
        policy=surplus_policy,
        penalty_minutes=surplus_minutes,
        extra={"attendance_pre_authorization": pre_authorization},
    )
    if penalty:
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
        return None

    shift_doc = frappe.get_cached_doc("Shift Type", ctx.shift_type)
    attendance = frappe.get_cached_doc("Attendance", ctx.attendance) if ctx.attendance else None

    return _build_penalty(
        employee=ctx.employee,
        attendance=ctx.attendance,
        violation_date=ctx.date or str(today()),
        penalty_status=attendance.status if attendance else "Present",
        shift_doc=shift_doc,
        config=config,
        policy=shift_doc.custom_attendance_penalty_policy or config.attendance_penalty_policy,
        penalty_minutes=ledger.penalty_minutes,
        grace_consumed=ledger.consumed_minutes,
        extra={"employee_grace_ledger": ledger.name},
    )


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
    _grace_rows = frappe.db.get_all(
        "Employee Grace Ledger",
        filters={
            "employee": ctx.employee,
            "period_start": shift.custom_period_start_date,
            "period_end": shift.custom_period_end_date,
        },
        fields=[{"SUM": "consumed_minutes", "as": "total_consumed"}],
    )
    prior_total = cint((_grace_rows[0].get("total_consumed") if _grace_rows else 0) or 0)
    prior_overflow = max(0, prior_total - allowed)
    new_total = prior_total + ctx.minutes
    new_overflow = max(0, new_total - allowed)

    ledger: EmployeeGraceLedger = frappe.new_doc("Employee Grace Ledger")
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
    return bool(
        frappe.db.exists(
            "Employee Grace Ledger",
            {"employee": ctx.employee, "attendance": ctx.attendance},
        )
    )


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
