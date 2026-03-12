from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import cast

import frappe
from frappe.utils import cint, today

from discipline_hr.discipline_hr.doctype.employee_grace_ledger.employee_grace_ledger import (
    EmployeeGraceLedger,
)
from discipline_hr.services.utils import logger


@dataclass
class _AttendanceContext:
    employee: str
    attendance: str | None
    minutes: float
    shift_type: str | None
    date: str
    attendance_permission: str | None = dc_field(default=None)


def _context_from_permission(doc) -> _AttendanceContext:
    return _AttendanceContext(
        employee=doc.employee,
        attendance=doc.attendance,
        minutes=doc.minutes,
        shift_type=doc.shift_type,
        date=str(doc.date),
        attendance_permission=doc.name,
    )


def _context_from_attendance(attendance_doc) -> _AttendanceContext:
    shift = frappe.get_cached_doc("Shift Type", attendance_doc.shift)
    minutes = max(cint(shift.custom_minimum_grace_minutes), attendance_doc.custom_penalty_minutes)
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
        {"employee": attendance_doc.employee, "date": attendance_doc.attendance_date},
    )
    if existing_permission:
        logger.info(
            "Bypass skipped for %s on %s: manual Attendance Permission %s exists",
            attendance_doc.employee,
            attendance_doc.attendance_date,
            existing_permission,
        )
        return

    ctx = _context_from_attendance(attendance_doc)
    _create_grace_ledger(ctx)


def _create_attendance_penalty(ctx: _AttendanceContext, ledger):
    """Create an Attendance Penalty record from a grace ledger entry.

    Does nothing if ``ledger.penalty_minutes`` is zero. The penalty policy is
    taken from the shift, or falls back to the global Discipline HR Settings.

    Args:
        ctx: The ``_AttendanceContext`` carrying employee/attendance/date data.
        ledger: The ``EmployeeGraceLedger`` that was just inserted.
    """
    if ledger.penalty_minutes <= 0:
        logger.info(
            "No attendance penalty created for %s. Remaining grace before consume: %s. penalty: %s.",
            ctx.employee,
            ledger.remaining_minutes_before_consume,
            ledger.penalty_minutes,
        )
        return

    if not ctx.shift_type:
        logger.warning("No shift type for %s on %s — cannot create penalty", ctx.employee, ctx.date)
        return

    shift_doc = frappe.get_cached_doc("Shift Type", ctx.shift_type)
    config = frappe.get_cached_doc("Discipline HR Settings")

    penalty = frappe.new_doc("Attendance Penalty")
    penalty.employee = ctx.employee
    penalty.violation_date = ctx.date or str(today())
    penalty.start_period = ledger.period_start
    penalty.end_period = ledger.period_end

    penalty.violation_number = 1 + frappe.db.count(
        "Attendance Penalty",
        {
            "employee": ctx.employee,
            "start_period": ledger.period_start,
            "end_period": ledger.period_end,
        },
    )

    if ctx.attendance:
        penalty.attendance = ctx.attendance
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


def _create_grace_ledger(ctx: _AttendanceContext):
    """Insert an Employee Grace Ledger entry and trigger penalty creation if needed.

    Sums up grace already consumed in the period, subtracts the current minutes,
    and sets ``penalty_minutes`` to the overflow (if any).

    Args:
        ctx: The ``_AttendanceContext`` carrying employee/attendance/shift data.
    """
    if not _ignore_grace_ledger_duplicates(ctx):
        return

    shift = frappe.get_cached_doc("Shift Type", ctx.shift_type)
    ledger = cast(EmployeeGraceLedger, frappe.new_doc("Employee Grace Ledger"))
    logger.debug(f"Creating grace ledger for {ctx.employee} ({ctx.minutes} minutes)")
    ledger.employee = ctx.employee
    ledger.attendance = ctx.attendance
    ledger.attendance_permission = ctx.attendance_permission
    ledger.period_start = shift.custom_period_start_date
    ledger.period_end = shift.custom_period_end_date
    ledger.allowed_minutes = shift.custom_total_allowed_grace_minutes
    ledger.consumed_minutes = ctx.minutes
    consumed_so_far = (
        frappe.db.get_value(
            "Employee Grace Ledger",
            filters={
                "employee": ctx.employee,
                "period_start": shift.custom_period_start_date,
                "period_end": shift.custom_period_end_date,
                "attendance_penalty": ("is", "not set"),
            },
            fieldname="sum(consumed_minutes)",
        )
        or 0
    )
    ledger.remaining_minutes_before_consume = ledger.allowed_minutes - consumed_so_far

    ledger.remaining_minutes = max(0, ledger.remaining_minutes_before_consume - ledger.consumed_minutes)
    penalty_minutes = ledger.remaining_minutes_before_consume - ledger.consumed_minutes
    if penalty_minutes >= 0:
        logger.info("No violations yet for ledger %s", ledger)
        ledger.penalty_minutes = 0
    else:
        ledger.penalty_minutes = abs(penalty_minutes)

    try:
        ledger.insert(ignore_permissions=True)
        logger.info("Ledger Inserted successfuly. %s", ledger)
        _create_attendance_penalty(ctx, ledger)
    except Exception:
        logger.exception("Couldn't create the grace ledger")
        frappe.log_error(
            title=f"Grace Ledger Creation Failed for {ctx.employee}",
            message=frappe.get_traceback(),
        )


def _should_continue_workflow(permission_doc):
    """Check whether the permission is ready to be processed.

    Returns ``False`` if required fields are missing or the status is not
    ``"Auto Processed"`` or ``"Processed"``.

    Args:
        permission_doc: The ``AttendancePermissions`` document to check.

    Returns:
        ``True`` if processing should continue, ``False`` otherwise.
    """
    if not permission_doc.employee or not permission_doc.minutes:
        logger.warning(
            "Workflow stopped for permission %s: missing required fields (employee=%s, minutes=%s)",
            permission_doc.name,
            permission_doc.employee,
            permission_doc.minutes,
        )
        return False

    if permission_doc.status not in ["Auto Processed", "Processed"]:
        logger.info(
            "Workflow Stopped for permission %s with status %s",
            permission_doc.name,
            permission_doc.status,
        )
        return False
    return True


def _ignore_grace_ledger_duplicates(ctx: _AttendanceContext):
    """Return whether a grace ledger entry should be created for this context.

    When the ``ignore_grace_ledger_duplicates`` setting is on, returns ``False``
    if a ledger already exists for the same employee and attendance.

    Args:
        ctx: The ``_AttendanceContext`` to check.

    Returns:
        ``True`` if safe to create a new ledger, ``False`` to skip.
    """
    ignore_duplicates = frappe.db.get_single_value("Discipline HR Settings", "ignore_grace_ledger_duplicates")
    if cint(ignore_duplicates) != 1:
        logger.debug("ignore duplicates deactivated")
        return True

    if ctx.attendance:
        filters = {"employee": ctx.employee, "attendance": ctx.attendance}
    else:
        filters = {"employee": ctx.employee, "attendance_permission": ctx.attendance_permission}

    existing_ledger = frappe.db.exists("Employee Grace Ledger", filters)

    if existing_ledger:
        logger.info(
            "Grace Ledger already exists for %s (attendance=%s, permission=%s)",
            ctx.employee,
            ctx.attendance,
            ctx.attendance_permission,
        )
        return False

    return True
