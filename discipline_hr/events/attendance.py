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
from discipline_hr.services.utils import _log, count_prior_violations


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
        _log("error", "shift_details_missing", employee=doc.employee, date=str(doc.attendance_date))
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
        _log("error", "attendance_missing_shift_type", attendance=doc.name)
        return

    shift_doc = frappe.get_cached_doc("Shift Type", doc.shift)

    # Guard to start, end period
    if not shift_doc.custom_period_start_date or not shift_doc.custom_period_end_date:
        _log("info", "penalty_skipped_no_period", attendance=doc.name, shift=doc.shift)
        return

    if getdate(doc.attendance_date) < getdate(shift_doc.custom_period_start_date) or getdate(
        doc.attendance_date
    ) > getdate(shift_doc.custom_period_end_date):
        _log(
            "info",
            "penalty_skipped_outside_period",
            attendance=doc.name,
            date=str(doc.attendance_date),
            period_start=str(shift_doc.custom_period_start_date),
            period_end=str(shift_doc.custom_period_end_date),
        )
        return

    if not shift_doc.enable_auto_attendance:
        _log("info", "penalty_skipped_auto_attendance_disabled", attendance=doc.name, shift=doc.shift)
        return

    late_grace, early_grace = get_grace_minutes(shift_doc)

    doc.custom_late_after_grace_minutes = cint(max(0, doc.custom_late_entry_minutes - late_grace))

    doc.custom_early_after_grace_minutes = cint(max(0, doc.custom_early_exist_minutes - early_grace))

    doc.custom_penalty_minutes = doc.custom_late_after_grace_minutes + doc.custom_early_after_grace_minutes


@frappe.whitelist()
def retry_attendance_permission(attendance_name):
    """Manual retry for Attendance Permissions from the Attendance form.

    Args:
        attendance_name: The name of the Attendance record to retry.
    """
    doc = frappe.get_doc("Attendance", attendance_name)
    if not doc.custom_penalty_minutes:
        frappe.throw(frappe._("This attendance has no penalty minutes - nothing to retry."))
    # Pre-clear: the service writes a fresh traceback back on failure.
    frappe.db.set_value("Attendance", attendance_name, "custom_error_log", None, update_modified=False)
    create_attendance_permissions_for(doc)


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
    create_attendance_permissions_for(doc)


def create_attendance_permissions_for(doc):
    """Synchronous helper to create Attendance Permissions for an Attendance doc."""
    if not doc.custom_penalty_minutes:
        return

    config = frappe.get_cached_doc("Discipline HR Settings")
    try:
        if cint(config.split_permissions_and_penalties) == 1:
            from discipline_hr.services.attendance_permission import process_attendance_without_permission

            _log("debug", "creating_penalty_without_permission")
            process_attendance_without_permission(doc)
            return

        shift_doc = frappe.get_cached_doc("Shift Type", doc.shift)
        at = create_attendance_permissions(
            doc.employee, doc.name, doc.custom_penalty_minutes, shift_doc.name, doc.attendance_date
        )
        if at:
            _log("info", "attendance_permission_created", permission=str(at), employee=doc.employee)
    except Exception:
        _log(
            "exception",
            "attendance_permission_creation_failed",
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


def create_attendance_permissions(employee, attendance, minutes, shift_name, date=""):
    """Create an Attendance Permissions record.

    Status is set to ``"Pending"`` when the shift requires HR approval, otherwise
    ``"Auto Processed"``. Silently returns if ``employee`` is empty.

    Args:
        employee: Employee docname.
        attendance: Attendance docname (or object with .name) linked to this permission.
        minutes: Penalty minutes (floored to shift minimum grace).
        shift_name: Shift Type docname used to resolve config.
        date: Violation date; defaults to today if omitted.
    """
    if not employee:
        return

    attendance_name = getattr(attendance, "name", attendance)

    if frappe.db.exists("Attendance Permissions", {"attendance": attendance_name}):
        _log("info", "attendance_permission_skipped_duplicate", attendance=attendance_name)
        return
    shift_doc = frappe.get_cached_doc("Shift Type", shift_name)
    doc = cast(AttendancePermissions, frappe.new_doc("Attendance Permissions"))
    doc.employee = employee
    doc.attendance = attendance_name
    doc.minutes = max(cint(shift_doc.custom_minimum_grace_minutes), minutes)
    doc.status = _get_attendance_permission_status() or "Auto Processed"
    doc.date = date or today()
    doc.auto_created = 1
    doc.shift_type = shift_doc.name
    doc.insert(ignore_if_duplicate=True, ignore_permissions=True)
    return doc.name


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
    """Create a Discipline Penalty for an absent employee on Attendance submit.

    Reads the Absence Penalty Policy from the Shift Type or Discipline HR Settings,
    counts existing violations in the same period, and inserts a new penalty record.
    """
    if doc.status != "Absent":
        return

    _log("info", "creating_absence_penalty", attendance=doc.name, employee=doc.employee)
    shift_doc = frappe.get_cached_doc("Shift Type", doc.shift)
    config = frappe.get_cached_doc("Discipline HR Settings")

    if not _should_create_absence_penalty(shift_doc, config):
        return

    penalty = frappe.new_doc("Discipline Penalty")
    penalty.employee = doc.employee
    penalty.attendance = doc.name
    penalty.violation_date = doc.attendance_date
    penalty.start_period = shift_doc.custom_period_start_date
    penalty.end_period = shift_doc.custom_period_end_date
    penalty.absence_penalty_policy = shift_doc.custom_absence_penalty_policy or config.absence_penalty_policy
    penalty.salary_component = shift_doc.custom_salary_component or config.salary_component or ""
    penalty.penalty_status = doc.status
    penalty.violation_number = 1 + count_prior_violations(
        doc.employee,
        shift_doc.custom_period_start_date,
        shift_doc.custom_period_end_date,
        doc.status,
    )
    penalty.status = "Auto Processed" if cint(config.auto_process_attendance_penalty) else "Pending"
    penalty.insert(ignore_if_duplicate=True, ignore_permissions=True)
    _log(
        "info",
        "absence_penalty_created",
        penalty=penalty.name,
        employee=doc.employee,
        violation_number=penalty.violation_number,
    )


def _should_create_absence_penalty(shift_doc, config):
    """Return True if absence penalties should be created for this shift.

    Returns False when:
    - Auto Attendance is disabled on the shift
    - No grace period start date is configured on the shift
    - No Absence Penalty Policy is set on either the shift or Discipline HR Settings
    """
    if not shift_doc.enable_auto_attendance or not shift_doc.custom_period_start_date:
        _log("info", "absence_penalty_not_applicable", shift=shift_doc.name)
        return False

    if not shift_doc.custom_absence_penalty_policy and not config.absence_penalty_policy:
        _log("info", "absence_penalty_policy_not_configured", shift=shift_doc.name)
        return False

    return True


def cascade_cancel_attendance(doc, method=None):
    """Hard-delete all downstream discipline_hr docs when an Attendance is cancelled.

    Wired to ``on_cancel`` only (not ``on_trash``). Cancellation is the user-visible
    action that signals "remove the consequences of this Attendance" — running the
    cascade here means HR sees penalties disappear at cancel time without needing a
    follow-up delete. By the time ``on_trash`` would fire, every downstream record is
    already gone and the cascade would be a no-op duplicate.

    Deletion order (leaf-first to respect link references):
      1. Additional Salary  (cancel if submitted, then delete)
      2. Discipline Penalty
      3. Employee Grace Ledger  (both permission-flow and penalty-flow entries)
      4. Attendance Permissions  (only auto_created=1)

    Args:
        doc: The ``Attendance`` document being cancelled.
        method: Unused; required by Frappe hook signature.
    """
    attendance_name = doc.name

    # Step 1: Collect penalties linked to this attendance
    penalty_names = frappe.get_all(
        "Discipline Penalty",
        filters={"attendance": attendance_name},
        pluck="name",
    )

    # Step 2: Delete Additional Salaries linked to those penalties
    if penalty_names:
        additional_salaries = frappe.get_all(
            "Additional Salary",
            filters={"custom_discipline_penalty": ("in", penalty_names)},
            fields=["name", "docstatus"],
        )
        for sal in additional_salaries:
            if sal.docstatus == 1:
                sal_doc = frappe.get_doc("Additional Salary", sal.name)
                sal_doc.cancel()
            frappe.delete_doc("Additional Salary", sal.name, force=True, ignore_permissions=True)
            _log(
                "info",
                "cascade_deleted_additional_salary",
                additional_salary=sal.name,
                attendance=attendance_name,
            )

    # Step 3: Delete Discipline Penalties
    for penalty_name in penalty_names:
        frappe.delete_doc("Discipline Penalty", penalty_name, force=True, ignore_permissions=True)
        _log("info", "cascade_deleted_discipline_penalty", penalty=penalty_name, attendance=attendance_name)

    # Step 4: Delete all Employee Grace Ledger entries (permission-flow + penalty-flow)
    ledger_names = frappe.get_all(
        "Employee Grace Ledger",
        filters={"attendance": attendance_name},
        pluck="name",
    )
    for ledger_name in ledger_names:
        frappe.delete_doc("Employee Grace Ledger", ledger_name, force=True, ignore_permissions=True)
        _log("info", "cascade_deleted_grace_ledger", ledger=ledger_name, attendance=attendance_name)

    # Step 5: Delete auto-created Attendance Permissions only
    permission_names = frappe.get_all(
        "Attendance Permissions",
        filters={"attendance": attendance_name, "auto_created": 1},
        pluck="name",
    )
    for perm_name in permission_names:
        frappe.delete_doc("Attendance Permissions", perm_name, force=True, ignore_permissions=True)
        _log(
            "info", "cascade_deleted_attendance_permission", permission=perm_name, attendance=attendance_name
        )

    total = len(penalty_names) + len(ledger_names) + len(permission_names)
    if total:
        _log(
            "info",
            "cascade_cancel_complete",
            attendance=attendance_name,
            penalties=len(penalty_names),
            ledgers=len(ledger_names),
            permissions=len(permission_names),
        )
