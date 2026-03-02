from typing import cast

import frappe
from frappe.utils import cint

from discipline_hr.discipline_hr.doctype.employee_grace_ledger.employee_grace_ledger import (
    EmployeeGraceLedger,
)
from discipline_hr.services.grace import calculate_consumed_grace_minutes
from discipline_hr.services.utils import logger


def process_submitted_attendance_permission(doc):
    if not _should_continue_workflow(doc):
        return
    _create_grace_ledger(doc)


def _create_attendance_penalty(permission_doc, ledger):
    # If no penalties to be applied
    if ledger.penalty_minutes <= 0:
        logger.info(
            "No attendance penalty created for %s. Remaining grace before consume: %s. penalty: %s.",
            permission_doc.employee,
            ledger.remaining_minutes_before_consume,
            ledger.penalty_minutes,
        )
        return

    attendance = frappe.get_doc("Attendance", permission_doc.attendance)

    logger.debug(
        "Creating attendance penalty for attendance %s",
        attendance,
    )

    if not attendance.shift:
        return
    penalty = frappe.new_doc("Attendance Penalty")
    penalty.employee = permission_doc.employee
    penalty.attendance = permission_doc.attendance
    penalty.violation_date = permission_doc.date or attendance.attendance_date
    penalty.deviation_minutes = cint(attendance.custom_late_entry_minutes) + cint(
        attendance.custom_early_exist_minutes
    )
    penalty.start_period = ledger.period_start
    penalty.end_period = ledger.period_end

    penalty.violation_number = 1 + frappe.db.count(
        "Attendance Penalty",
        {
            "employee": permission_doc.employee,
            "start_period": ledger.period_start,
            "end_period": ledger.period_end,
        },
    )

    shift_doc = frappe.get_cached_doc("Shift Type", attendance.shift)
    default_policy = frappe.get_single_value("Discipline HR Settings", "attendance_penalty_policy")
    penalty.attendance_penalty_policy = shift_doc.custom_attendance_penalty_policy or default_policy
    config = frappe.get_doc("Discipline HR Settings")
    penalty.attendance_permission = permission_doc.name
    penalty.salary_component = config.salary_component or ""
    penalty.employee_grace_ledger = ledger.name
    penalty.grace_consumed = ledger.consumed_minutes
    penalty.penalty_minutes = ledger.penalty_minutes
    penalty.insert(ignore_if_duplicate=True, ignore_permissions=True)


def _create_grace_ledger(permission_doc):
    if not _ignore_grace_ledger_duplicates(permission_doc):
        return

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
        _create_attendance_penalty(permission_doc, ledger)
    except Exception:
        logger.exception("Couldn't create the grace ledger")


def _should_continue_workflow(permission_doc):
    if not permission_doc.employee or not permission_doc.attendance or not permission_doc.minutes:
        return False

    if permission_doc.status not in ["Auto Processed", "Accepted"]:
        logger.info(
            "Workflow Stopped for permission %s with status %s",
            permission_doc.name,
            permission_doc.status,
        )
        return False
    return True


def _ignore_grace_ledger_duplicates(permission_doc):
    ignore_duplicates = frappe.db.get_single_value("Discipline HR Settings", "ignore_grace_ledger_duplicates")
    if cint(ignore_duplicates) != 1:
        logger.debug("ignore duplicates deactivated")
        return True

    existing_ledger = frappe.db.exists(
        "Employee Grace Ledger",
        {
            "employee": permission_doc.employee,
            "attendance": permission_doc.attendance,
        },
    )

    if existing_ledger:
        logger.info(
            "Grace Ledger already exists for attendance %s",
            permission_doc.attendance,
        )
        return False

    return True
