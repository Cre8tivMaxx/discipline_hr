from dataclasses import dataclass
from dataclasses import field as dc_field
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
    attendance_permission: str | None = dc_field(default=None)
    auto_created: int = 1


def _context_from_permission(doc) -> _AttendanceContext:
    return _AttendanceContext(
        employee=doc.employee,
        attendance=doc.attendance,
        minutes=doc.minutes,
        shift_type=doc.shift_type,
        date=str(doc.date),
        attendance_permission=doc.name,
        auto_created=doc.auto_created,
    )


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


def process_submitted_attendance_permission(doc):
    """Entry point called after an Attendance Permission is inserted.

    Validates the permission status and delegates to grace ledger creation.

    Args:
        doc: An ``AttendancePermissions`` document.
    """
    if not _should_continue_workflow(doc):
        return
    ctx = _context_from_permission(doc)
    _create_grace_ledger(ctx)


def process_attendance_without_permission(attendance_doc):
    """Create grace ledger and penalty directly from an Attendance doc.

    Called when ``split_permissions_and_penalties`` is enabled, bypassing the
    Attendance Permissions step entirely.

    Skips processing if a manual Attendance Permissions record already exists for
    this employee + date — the manual permission flow will handle the penalty.

    Args:
        attendance_doc: The submitted ``Attendance`` document.
    """
    if not attendance_doc.custom_penalty_minutes:
        return

    # Guard: if HR manually created an Attendance Permissions record for this
    # employee + date, that flow already created (or will create) the penalty.
    # Proceeding here would create a duplicate grace ledger + penalty.
    existing_permission = frappe.db.exists(
        "Attendance Permissions",
        {
            "employee": attendance_doc.employee,
            "date": attendance_doc.attendance_date,
            "status": ("in", ["Auto Processed", "Processed"]),
        },
    )
    if existing_permission:
        frappe.db.set_value(
            "Attendance Permissions",
            existing_permission,
            "attendance",
            attendance_doc.name,
            update_modified=False,
        )

        permission_minutes = frappe.db.get_value("Attendance Permissions", existing_permission, "minutes")
        extra_minutes = attendance_doc.custom_penalty_minutes - cint(permission_minutes)
        if extra_minutes > 0:
            _create_extra_minutes_penalty(attendance_doc, extra_minutes, existing_permission)

        _log(
            "info",
            "bypass_skipped_manual_permission",
            employee=attendance_doc.employee,
            date=str(attendance_doc.attendance_date),
            permission=existing_permission,
            attendance=attendance_doc.name,
        )
        return

    ctx = _context_from_attendance(attendance_doc)
    _create_grace_ledger(ctx)


def _create_extra_minutes_penalty(attendance_doc, extra_minutes, existing_permission):
    """Create a penalty for minutes exceeding an existing permission, bypassing grace ledger.

    Args:
        attendance_doc: The submitted ``Attendance`` document.
        extra_minutes: Number of penalty minutes beyond the permission.
        existing_permission: Name of the existing ``Attendance Permissions`` record.
    """
    config = frappe.get_cached_doc("Discipline HR Settings")
    if not config.extra_minutes_penalty_policy:
        _log(
            "warning",
            "no_extra_minutes_policy",
            attendance=attendance_doc.name,
            permission=existing_permission,
        )
        return

    shift_doc = frappe.get_cached_doc("Shift Type", attendance_doc.shift)

    penalty = frappe.new_doc("Discipline Penalty")
    penalty.employee = attendance_doc.employee
    penalty.attendance = attendance_doc.name
    penalty.attendance_permission = existing_permission
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
    penalty.attendance_penalty_policy = config.extra_minutes_penalty_policy
    penalty.salary_component = shift_doc.custom_salary_component or config.salary_component or ""
    penalty.penalty_minutes = extra_minutes
    penalty.grace_consumed = 0
    penalty.status = "Auto Processed" if config.auto_process_attendance_penalty else "Pending"
    penalty.insert(ignore_if_duplicate=True, ignore_permissions=True)
    _log(
        "info",
        "extra_minutes_penalty_created",
        employee=attendance_doc.employee,
        extra_minutes=extra_minutes,
        permission=existing_permission,
    )


def _create_attendance_penalty(ctx: _AttendanceContext, ledger, config):
    """Create a Discipline Penalty record from a grace ledger entry.

    Does nothing if ``ledger.penalty_minutes`` is zero. The penalty policy is
    taken from the shift, or falls back to the global Discipline HR Settings.

    Args:
        ctx: The ``_AttendanceContext`` carrying employee/attendance/date data.
        ledger: The ``EmployeeGraceLedger`` that was just inserted.
        config: The ``DisciplineHRSettings`` single doctype.
    """
    if ledger.penalty_minutes <= 0:
        _log(
            "info",
            "no_penalty_within_grace",
            employee=ctx.employee,
            remaining_grace_before_consume=ledger.remaining_minutes_before_consume,
            penalty_minutes=ledger.penalty_minutes,
        )
        return

    if frappe.db.exists("Discipline Penalty", {"attendance": ctx.attendance}):
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

    penalty.attendance_permission = ctx.attendance_permission
    penalty.attendance_penalty_policy = (
        shift_doc.custom_attendance_penalty_policy or config.attendance_penalty_policy
    )
    penalty.salary_component = shift_doc.custom_salary_component or config.salary_component or ""
    penalty.employee_grace_ledger = ledger.name
    penalty.grace_consumed = ledger.consumed_minutes
    penalty.penalty_minutes = ledger.penalty_minutes
    penalty.status = "Auto Processed" if config.auto_process_attendance_penalty else "Pending"
    penalty.insert(ignore_if_duplicate=True, ignore_permissions=True)
    return penalty


def _create_grace_ledger(ctx: _AttendanceContext):
    """Insert an Employee Grace Ledger entry and trigger penalty creation if needed.

    Sums up grace already consumed in the period, subtracts the current minutes,
    and sets ``penalty_minutes`` to the overflow (if any).

    Args:
        ctx: The ``_AttendanceContext`` carrying employee/attendance/shift data.
    """
    if _ignore_grace_ledger_duplicates(ctx):
        return

    shift = frappe.get_cached_doc("Shift Type", ctx.shift_type)
    ledger = cast(EmployeeGraceLedger, frappe.new_doc("Employee Grace Ledger"))
    _log("debug", "creating_grace_ledger", employee=ctx.employee, minutes=ctx.minutes)
    ledger.employee = ctx.employee
    ledger.attendance = ctx.attendance
    ledger.attendance_permission = ctx.attendance_permission
    ledger.period_start = shift.custom_period_start_date
    ledger.period_end = shift.custom_period_end_date
    ledger.allowed_minutes = shift.custom_total_allowed_grace_minutes
    ledger.consumed_minutes = ctx.minutes
    ledger.remarks = (
        f"Auto-created from {ctx.attendance_permission}" if ctx.attendance_permission else "Auto-created"
    )
    ledger.date = ctx.date
    consumed_so_far = (
        frappe.db.get_value(
            "Employee Grace Ledger",
            filters={
                "employee": ctx.employee,
                "period_start": shift.custom_period_start_date,
                "period_end": shift.custom_period_end_date,
                "discipline_penalty": ("is", "not set"),
            },
            fieldname="sum(consumed_minutes)",
        )
        or 0
    )
    ledger.remaining_minutes_before_consume = ledger.allowed_minutes - consumed_so_far

    ledger.remaining_minutes = max(0, ledger.remaining_minutes_before_consume - ledger.consumed_minutes)
    penalty_minutes = ledger.remaining_minutes_before_consume - ledger.consumed_minutes
    if penalty_minutes >= 0:
        _log("info", "no_violations_yet", employee=ctx.employee, ledger=str(ledger))
        ledger.penalty_minutes = 0
    else:
        ledger.penalty_minutes = abs(penalty_minutes)

    try:
        ledger.insert(ignore_permissions=True)
        _log("info", "ledger_inserted", employee=ctx.employee, ledger=ledger.name)
    except Exception:
        _log(
            "exception",
            "grace_ledger_creation_failed",
            employee=ctx.employee,
            attendance=ctx.attendance,
            permission=ctx.attendance_permission or "",
            date=ctx.date,
            minutes=ctx.minutes,
        )
        if ctx.attendance_permission:
            frappe.db.set_value(
                "Attendance Permissions",
                ctx.attendance_permission,
                "error_log",
                frappe.get_traceback(),
                update_modified=False,
            )
        elif ctx.attendance:
            frappe.db.set_value(
                "Attendance",
                ctx.attendance,
                "custom_error_log",
                frappe.get_traceback(),
                update_modified=False,
            )
        return
    try:
        config = frappe.get_cached_doc("Discipline HR Settings")
        if ctx.auto_created == 1 or config.penalize_manual_attendance_permissions == 1:
            _create_attendance_penalty(ctx, ledger, config)
    except Exception:
        _log(
            "exception",
            "discipline_penalty_creation_failed",
            employee=ctx.employee,
            attendance=ctx.attendance,
            permission=ctx.attendance_permission or "",
            date=ctx.date,
            minutes=ctx.minutes,
        )
        frappe.db.set_value(
            "Employee Grace Ledger",
            ledger.name,
            "error_log",
            frappe.get_traceback(),
            update_modified=False,
        )
    return ledger


def _should_continue_workflow(permission_doc):
    """Check whether the permission is ready to be processed.

    Returns ``False`` if required fields are missing or the status is not
    ``"Auto Processed"`` or ``"Processed"``.

    Args:
        permission_doc: The ``AttendancePermissions`` document to check.

    Returns:
        ``True`` if processing should continue, ``False`` otherwise.
    """
    if not permission_doc.minutes:
        _log(
            "warning",
            "workflow_stopped_missing_minutes",
            permission=permission_doc.name,
            minutes=permission_doc.minutes,
        )
        return False

    if permission_doc.status not in ["Auto Processed", "Processed"]:
        _log(
            "info",
            "workflow_stopped_invalid_status",
            permission=permission_doc.name,
            status=permission_doc.status,
        )
        return False
    return True


def _ignore_grace_ledger_duplicates(ctx: _AttendanceContext):
    """Return whether a grace ledger entry should be created for this context.

    returns ``False`` if a ledger already exists for the same employee and attendance.

    Args:
        ctx: The ``_AttendanceContext`` to check.

    Returns:
        ``True`` if safe to create a new ledger, ``False`` to skip.
    """
    if ctx.attendance:
        filters = {"employee": ctx.employee, "attendance": ctx.attendance}
    else:
        filters = {"employee": ctx.employee, "attendance_permission": ctx.attendance_permission}
    existing_ledger = frappe.db.exists("Employee Grace Ledger", filters)

    if existing_ledger:
        _log(
            "info",
            "grace_ledger_already_exists",
            employee=ctx.employee,
            attendance=ctx.attendance,
            permission=ctx.attendance_permission,
        )
        return True  # Yes ignore grace ledger duplicates

    return False  # There is no duplicates
