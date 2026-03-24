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

    Runs on ``Attendance.before_submit``. Writes late/early custom fields
    Skips non-Present records and attendances outside the shift period.

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
        logger.error("Attendance missing Shift Type")
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
    """Create an Attendance Permission or directly process a penalty for a submitted Attendance.

    When ``split_permissions_and_penalties`` is enabled in Discipline HR Settings,
    penalties are created directly without an intermediate Attendance Permission record.
    Otherwise, an Attendance Permission is created (which in turn triggers the grace
    ledger and penalty pipeline via its ``after_insert`` hook).

    Only acts when ``doc.custom_penalty_minutes`` is non-zero (standard path).

    Args:
        doc: The ``Attendance`` document that was just submitted.
        method: Unused; required by Frappe hook signature.
    """
    config = frappe.get_cached_doc("Discipline HR Settings")
    if cint(config.split_permissions_and_penalties) == 1:
        from discipline_hr.services.attendance_permission import process_attendance_without_permission

        logger.debug("Creating Penalty without permission | split_permissions_and_penalties == 1")
        process_attendance_without_permission(doc)
        return
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
                "Couldn't create attendance permission | queue: %s | employee: %s", doc, doc.employee
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


def create_absence_penalty(doc, method=None):
    """Create an Attendance Penalty for an absent employee on Attendance submit.

    Reads the Absence Penalty Policy from the Shift Type or Discipline HR Settings,
    counts existing violations in the same period, and inserts a new penalty record.
    """
    if doc.status != "Absent":
        return

    logger.info(
        "Creating absence penalty | Attendance: %s | Employee: %s",
        doc.name,
        doc.employee,
    )
    shift_doc = frappe.get_cached_doc("Shift Type", doc.shift)
    config = frappe.get_cached_doc("Discipline HR Settings")

    if not _should_create_absence_penalty(shift_doc, config):
        return

    penalty = frappe.new_doc("Attendance Penalty")
    penalty.employee = doc.employee
    penalty.attendance = doc.name
    penalty.violation_date = doc.attendance_date
    penalty.start_period = shift_doc.custom_period_start_date
    penalty.end_period = shift_doc.custom_period_end_date
    penalty.absence_penalty_policy = shift_doc.custom_absence_penalty_policy or config.absence_penalty_policy
    penalty.salary_component = shift_doc.custom_salary_component or config.salary_component or ""
    penalty.penalty_status = doc.status
    penalty.violation_number = 1 + frappe.db.count(
        "Attendance Penalty",
        {
            "employee": doc.employee,
            "start_period": shift_doc.custom_period_start_date,
            "end_period": shift_doc.custom_period_end_date,
            "penalty_status": doc.status,
        },
    )
    penalty.status = "Auto Processed" if cint(config.auto_process_attendance_penalty) else "Pending"
    penalty.insert(ignore_if_duplicate=True, ignore_permissions=True)
    logger.info(
        "Absence penalty created | Penalty: %s | Employee: %s | Violation #%s",
        penalty.name,
        doc.employee,
        penalty.violation_number,
    )


def _should_create_absence_penalty(shift_doc, config):
    """Return True if absence penalties should be created for this shift.

    Returns False when:
    - Auto Attendance is disabled on the shift
    - No grace period start date is configured on the shift
    - No Absence Penalty Policy is set on either the shift or Discipline HR Settings
    """
    if not shift_doc.enable_auto_attendance or not shift_doc.custom_period_start_date:
        logger.info(
            "Absence Penalty is not applicable for this shift | Shift: %s",
            shift_doc.name,
        )
        return False

    if not shift_doc.custom_absence_penalty_policy and not config.absence_penalty_policy:
        logger.info(
            "Absence Penalty policy not configured | Shift: %s",
            shift_doc.name,
        )
        return False

    return True


def cascade_cancel_attendance(doc, method=None):
    """Hard-delete all downstream discipline_hr docs when an Attendance is cancelled.

    Deletion order (leaf-first to respect link references):
      1. Additional Salary  (cancel if submitted, then delete)
      2. Attendance Penalty
      3. Employee Grace Ledger  (both permission-flow and penalty-flow entries)
      4. Attendance Permissions  (only auto_created=1)

    Args:
        doc: The ``Attendance`` document being cancelled.
        method: Unused; required by Frappe hook signature.
    """
    config = frappe.get_cached_doc("Discipline HR Settings")
    if not cint(config.cascade_cancel_attendance):
        logger.info("Cascade cancel skipped for %s: disabled in Discipline HR Settings", doc.name)
        return

    attendance_name = doc.name

    # Step 1: Collect penalties linked to this attendance
    penalty_names = frappe.get_all(
        "Attendance Penalty",
        filters={"attendance": attendance_name},
        pluck="name",
    )

    # Step 2: Delete Additional Salaries linked to those penalties
    if penalty_names:
        additional_salaries = frappe.get_all(
            "Additional Salary",
            filters={"custom_attendance_penalty": ("in", penalty_names)},
            fields=["name", "docstatus"],
        )
        for sal in additional_salaries:
            if sal.docstatus == 1:
                sal_doc = frappe.get_doc("Additional Salary", sal.name)
                sal_doc.cancel()
            frappe.delete_doc("Additional Salary", sal.name, force=True, ignore_permissions=True)
            logger.info(
                "Cascade cancel: deleted Additional Salary %s (Attendance %s)", sal.name, attendance_name
            )

    # Step 3: Delete Attendance Penalties
    for penalty_name in penalty_names:
        frappe.delete_doc("Attendance Penalty", penalty_name, force=True, ignore_permissions=True)
        logger.info(
            "Cascade cancel: deleted Attendance Penalty %s (Attendance %s)", penalty_name, attendance_name
        )

    # Step 4: Delete all Employee Grace Ledger entries (permission-flow + penalty-flow)
    ledger_names = frappe.get_all(
        "Employee Grace Ledger",
        filters={"attendance": attendance_name},
        pluck="name",
    )
    for ledger_name in ledger_names:
        frappe.delete_doc("Employee Grace Ledger", ledger_name, force=True, ignore_permissions=True)
        logger.info(
            "Cascade cancel: deleted Employee Grace Ledger %s (Attendance %s)", ledger_name, attendance_name
        )

    # Step 5: Delete auto-created Attendance Permissions only
    permission_names = frappe.get_all(
        "Attendance Permissions",
        filters={"attendance": attendance_name, "auto_created": 1},
        pluck="name",
    )
    for perm_name in permission_names:
        frappe.delete_doc("Attendance Permissions", perm_name, force=True, ignore_permissions=True)
        logger.info(
            "Cascade cancel: deleted Attendance Permissions %s (Attendance %s)", perm_name, attendance_name
        )

    total = len(penalty_names) + len(ledger_names) + len(permission_names)
    if total:
        logger.info(
            "Cascade cancel complete for Attendance %s: %d penalties, %d ledgers, %d permissions deleted",
            attendance_name,
            len(penalty_names),
            len(ledger_names),
            len(permission_names),
        )
