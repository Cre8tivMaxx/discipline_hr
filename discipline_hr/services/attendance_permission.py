from typing import cast

import frappe
from frappe.utils import cint

from discipline_hr.discipline_hr.doctype.employee_grace_ledger.employee_grace_ledger import (
    EmployeeGraceLedger,
)
from discipline_hr.services.grace import calculate_consumed_grace_minutes
from discipline_hr.services.utils import logger


def process_submitted_attendance_permission(doc):
    if not _should_continue_workflow:
        return
    _create_grace_ledger(doc)


def _create_attendance_violation(permission_doc, ledger):
    # If no penalties to be applied
    if ledger.penalty_minutes <= 0:
        logger.info(
            "No attendance violation created for %s. Remaining grace before consume: %s. penalty: %s.",
            permission_doc.employee,
            ledger.remaining_minutes_before_consume,
            ledger.penalty_minutes,
        )
        return

    attendance = frappe.get_doc("Attendance", permission_doc.attendance)

    logger.debug(
        "Creating attendance violation for attendance %s",
        attendance,
    )

    if not attendance.shift:
        return
    violation = frappe.new_doc("Attendance Violation")
    violation.employee = permission_doc.employee
    violation.attendance = permission_doc.attendance
    violation.violation_date = permission_doc.date or attendance.attendance_date
    violation.deviation_minutes = cint(attendance.custom_late_entry_minutes) + cint(
        attendance.custom_early_exist_minutes
    )
    violation.start_period = ledger.period_start
    violation.end_period = ledger.period_end

    violation.violation_number = 1 + frappe.db.count(
        "Attendance Violation",
        {
            "employee": permission_doc.employee,
            "start_period": ledger.period_start,
            "end_period": ledger.period_end,
        },
    )

    shift_doc = frappe.get_cached_doc("Shift Type", attendance.shift)
    grace_consumed = min(cint(ledger.consumed_minutes), cint(ledger.remaining_minutes_before_consume))

    violation.grace_consumed = calculate_consumed_grace_minutes(
        late_entry_minutes=attendance.custom_late_entry_minutes,
        early_exit_minutes=attendance.custom_early_exist_minutes,
        shift_doc=shift_doc,
    )

    violation.grace_consumed = min(violation.grace_consumed, grace_consumed)
    violation.penalty_minutes = ledger.penalty_minutes
    violation.insert(ignore_if_duplicate=True, ignore_permissions=True)


def _create_grace_ledger(permission_doc):
    existing_ledger = frappe.db.exists(
        "Employee Grace Ledger",
        {
            "employee": permission_doc.employee,
            "attendance": permission_doc.attendance,
        },
    )
    if existing_ledger:
        logger.info("Grace Ledger already exists for attendance %s", permission_doc.attendance)

    shift = frappe.get_cached_doc("Shift Type", permission_doc.shift_type)
    ledger = cast(EmployeeGraceLedger, frappe.new_doc("Employee Grace Ledger"))
    logger.debug(
        f"Creating grace ledger for {permission_doc.employee} " f"({permission_doc.minutes} minutes)"
    )
    ledger.employee = permission_doc.employee
    ledger.attendance = permission_doc.attendance
    ledger.period_start = shift.custom_period_start_date
    ledger.period_end = shift.custom_period_end_date
    ledger.allowed_minutes = shift.custom_total_allowed_grace_minutes
    ledger.consumed_minutes = permission_doc.minutes
    ledger.remaining_minutes_before_consume = ledger.allowed_minutes - (
        sum(
            frappe.get_all(
                "Employee Grace Ledger",
                filters=[
                    ["employee", "=", permission_doc.employee],
                    ["period_start", "=", shift.custom_period_start_date],
                    ["period_end", "=", shift.custom_period_end_date],
                ],
                pluck="consumed_minutes",
            )
        )
        or 0
    )

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
        _create_attendance_violation(permission_doc, ledger)
    except Exception:
        logger.exception("Couldn't create the grace ledger")


def _should_continue_workflow(permission_doc):
    if not permission_doc.employee or not permission_doc.attendance or not permission_doc.minutes:
        return False

    if permission_doc.status != "Rejected":
        logger.info(
            "Workflow Stopped for permission %s with status %s",
            permission_doc.name,
            permission_doc.status,
        )
        return False
    return True
