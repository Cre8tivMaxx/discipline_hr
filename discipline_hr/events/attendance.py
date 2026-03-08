from typing import cast

import frappe
from frappe.utils import (
    cint,
    get_datetime,
    getdate,
    time_diff_in_seconds,
    today,
)
from hrms.hr.doctype.shift_assignment.shift_assignment import (
    get_actual_start_end_datetime_of_shift,
)

from discipline_hr.discipline_hr.doctype.attendance_permissions.attendance_permissions import (
    AttendancePermissions,
)
from discipline_hr.services.grace import get_grace_minutes
from discipline_hr.services.utils import logger


def calculate_attendance_penalty_minutes(doc, method=None):
    """Calculate penalty minutes for a submitted Attendance record.

    Runs on ``Attendance.before_submit``. Writes late/early custom fields and
    enqueues :func:`create_attendance_permissions` if penalisable minutes remain
    after grace. Skips non-Present records and attendances outside the shift period.

    Args:
        doc: The ``Attendance`` document being submitted.
        method: Unused; required by Frappe hook signature.
    """
    # Only calculate for Present records
    if doc.status != "Present":
        return

    if not doc.in_time or not doc.out_time:
        return

    shift_details = get_actual_start_end_datetime_of_shift(doc.employee, get_datetime(doc.in_time))

    if not shift_details:
        logger.error(f"Shift details missing for {doc.employee} on {doc.attendance_date}")
        return

    start_datetime = shift_details["start_datetime"]
    end_datetime = shift_details["end_datetime"]

    # Calculate Raw Late / Early
    late_minutes = max(0, time_diff_in_seconds(doc.in_time, start_datetime)) / 60

    early_minutes = max(0, time_diff_in_seconds(end_datetime, doc.out_time)) / 60

    doc.custom_late_entry_minutes = cint(late_minutes)
    doc.custom_early_exist_minutes = cint(early_minutes)

    # Fetch Grace Directly From Shift
    if not doc.shift:
        logger.error("Attendance missing for Shift Type")
        return

    shift_doc = frappe.get_cached_doc("Shift Type", doc.shift)

    # Guard to start, end period
    if not shift_doc.custom_period_start_date or not shift_doc.custom_period_end_date:
        logger.info(
            f"Penalty Skipped for {doc.name}, because shift {doc.shift} doesn't have Period Start/End Date"
        )
        return

    if getdate(doc.attendance_date) < getdate(shift_doc.custom_period_start_date) or getdate(
        doc.attendance_date
    ) > getdate(shift_doc.custom_period_end_date):
        logger.info(
            f"Penalty skipped for Attendance {doc.name}: "
            f"date {doc.attendance_date} is outside shift period "
            f"({shift_doc.custom_period_start_date} → "
            f"{shift_doc.custom_period_end_date})"
        )
        return

    if not shift_doc.enable_auto_attendance:
        logger.info(
            f"Penalty skipped for {doc.name} because Auto Attendance is disabled for shift {doc.shift}"
        )
        return

    late_grace, early_grace = get_grace_minutes(shift_doc)

    doc.custom_late_after_grace_minutes = cint(max(0, doc.custom_late_entry_minutes - late_grace))

    doc.custom_early_after_grace_minutes = cint(max(0, doc.custom_early_exist_minutes - early_grace))

    doc.custom_penalty_minutes = doc.custom_late_after_grace_minutes + doc.custom_early_after_grace_minutes


def trigger_create_attendance_permission(doc, method=None):
    shift_doc = frappe.get_cached_doc("Shift Type", doc.shift)
    if doc.custom_penalty_minutes:
        try:
            at = create_attendance_permissions(
                doc.employee, doc.name, doc.custom_penalty_minutes, shift_doc.name, doc.attendance_date
            )

            logger.info(
                "Successfull create attendance permission | queue: %s | employee: %s", at, doc.employee
            )
        except Exception:
            logger.exception(
                "Couldn't create attendance permission | queue: %s | employee: %s", at, doc.employee
            )


def create_attendance_permissions(employee, attendance, minutes, shift_name, date=""):
    """Create an Attendance Permissions record. Intended to run as a background job.

    Status is set to ``"Pending"`` when the shift requires HR approval, otherwise
    ``"Auto Processed"``. Silently returns if ``employee`` is empty.

    Args:
        employee: Employee docname.
        attendance: Attendance docname linked to this permission.
        minutes: Penalty minutes (floored to shift minimum grace).
        shift_name: Shift Type docname used to resolve config.
        date: Violation date; defaults to today if omitted.
    """
    shift_doc = frappe.get_cached_doc("Shift Type", shift_name)
    doc = cast(AttendancePermissions, frappe.new_doc("Attendance Permissions"))
    if not employee:
        return

    doc.employee = employee
    doc.attendance = attendance
    doc.minutes = max(cint(shift_doc.custom_minimum_grace_minutes), minutes)
    doc.status = _get_attendance_permission_status() or "Auto Processed"
    doc.date = date or today()
    doc.auto_created = 1
    doc.shift_type = shift_doc.name
    doc.insert(ignore_if_duplicate=True, ignore_permissions=True)


def _get_attendance_permission_status():
    """Return the initial status for an auto-created Attendance Permission.

    Returns:
        ``"Pending"`` if HR approval is required, ``"Auto Processed"`` otherwise.
    """
    config = frappe.get_cached_doc("Discipline HR Settings")
    if cint(config.auto_process_attendance_permission) == 1:
        return "Auto Processed"
    return "Pending"
