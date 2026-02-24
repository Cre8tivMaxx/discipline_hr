from typing import cast

import frappe
from frappe.utils import cint

from discipline_hr import error_logger, logger
from discipline_hr.discipline_hr.doctype.employee_grace_ledger.employee_grace_ledger import (
    EmployeeGraceLedger,
)
from discipline_hr.services.grace import calculate_consumed_grace_minutes


def process_submitted_attendance_permission(doc):
    logger.debug(doc)
    if not doc.employee or not doc.attendance or not doc.minutes:
        return

    attendance = frappe.get_doc("Attendance", doc.attendance)
    _create_attendance_violation(doc, attendance)
    _create_grace_ledger(doc)


def _create_attendance_violation(permission_doc, attendance):
    if not attendance.shift:
        return
    violation = frappe.new_doc("Attendance Violation")
    violation.employee = permission_doc.employee
    violation.attendance = permission_doc.attendance
    violation.violation_date = permission_doc.date or attendance.attendance_date
    violation.deviation_minutes = cint(attendance.custom_late_entry_minutes) + cint(
        attendance.custom_early_exist_minutes
    )

    shift_doc = frappe.get_cached_doc("Shift Type", attendance.shift)
    violation.grace_consumed = calculate_consumed_grace_minutes(
        attendance.custom_late_entry_minutes,
        attendance.custom_early_exist_minutes,
        shift_doc,
    )
    violation.penalty_minutes = permission_doc.minutes
    violation.insert(ignore_if_duplicate=True, ignore_permissions=True)


def _create_grace_ledger(permission_doc):
    shift = frappe.get_cached_doc("Shift Type", permission_doc.shift_type)
    ledger = cast(EmployeeGraceLedger, frappe.new_doc("Employee Grace Ledger"))
    logger.info(f"ledger created {ledger}")
    ledger.employee = permission_doc.employee
    ledger.attendance = permission_doc.attendance
    ledger.period_start = shift.custom_period_start_date
    ledger.period_end = shift.custom_period_end_date
    ledger.allowed_minutes = shift.custom_total_allowed_grace_minutes
    ledger.consumed_minutes = permission_doc.minutes
    previous_minutes = (
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

    ledger.remaining_minutes = max(0, ledger.allowed_minutes - ledger.consumed_minutes - previous_minutes)

    try:
        ledger.insert(ignore_permissions=True)
        logger.info("Ledger Inserted successfuly.")
    except Exception as e:
        logger.error(f"Couldn't create the grace ledger --> {e}")
