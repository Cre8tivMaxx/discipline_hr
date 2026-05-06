from __future__ import annotations

import frappe
from frappe.utils import (
    cint,
    get_datetime,
    getdate,
    time_diff_in_seconds,
)
from hrms.hr.doctype.shift_assignment.shift_assignment import (
    get_actual_start_end_datetime_of_shift,
)

from discipline_hr.services.grace import get_grace_minutes
from discipline_hr.services.pre_authorization import apply_pre_authorization_and_penalty
from discipline_hr.services.utils import _log, count_prior_violations

__all__ = [
    "apply_pre_authorization_and_penalty",
    "calculate_attendance_penalty_minutes",
    "cascade_cancel_attendance",
    "create_absence_penalty",
    "retry_attendance_pipeline",
]


def calculate_attendance_penalty_minutes(doc, method=None):
    """Compute late / early / penalty minutes for a submitted Attendance."""
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

    late_minutes = max(0, time_diff_in_seconds(doc.in_time, start_datetime)) / 60
    early_minutes = max(0, time_diff_in_seconds(end_datetime, doc.out_time)) / 60

    doc.custom_late_entry_minutes = cint(late_minutes)
    doc.custom_early_exist_minutes = cint(early_minutes)

    if not doc.shift:
        _log("error", "attendance_missing_shift_type", attendance=doc.name)
        return

    shift_doc = frappe.get_cached_doc("Shift Type", doc.shift)

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
def retry_attendance_pipeline(attendance_name: str) -> None:
    """Re-run the pre-authorization / penalty pipeline for an Attendance."""
    doc = frappe.get_doc("Attendance", attendance_name)
    if not doc.custom_penalty_minutes:
        frappe.throw(frappe._("This attendance has no penalty minutes - nothing to retry."))
    frappe.db.set_value("Attendance", attendance_name, "custom_error_log", None, update_modified=False)
    apply_pre_authorization_and_penalty(doc)


def create_absence_penalty(doc, method=None):
    """Create a Discipline Penalty for an absent employee on Attendance submit."""
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


def _should_create_absence_penalty(shift_doc, config) -> bool:
    if not shift_doc.enable_auto_attendance or not shift_doc.custom_period_start_date:
        _log("info", "absence_penalty_not_applicable", shift=shift_doc.name)
        return False

    if not shift_doc.custom_absence_penalty_policy and not config.absence_penalty_policy:
        _log("info", "absence_penalty_policy_not_configured", shift=shift_doc.name)
        return False

    return True


def cascade_cancel_attendance(doc, method=None):
    """Hard-delete all downstream discipline_hr docs when an Attendance is cancelled.

    Cancellation is the user-visible action that signals "remove the consequences
    of this Attendance." Consumed Pre-Authorizations are reverted to Approved so
    an amended re-submit can re-consume them (one consumption per submit cycle).

    Deletion order (leaf-first to respect link references):
      1. Additional Salary  (cancel if submitted, then delete)
      2. Discipline Penalty
      3. Employee Grace Ledger
      4. Attendance Pre-Authorization (revert Consumed → Approved)
      5. Dev Attendance Seeder  (dev-only; guarded for production)
    """
    attendance_name = doc.name

    penalty_names = frappe.get_all(
        "Discipline Penalty",
        filters={"attendance": attendance_name},
        pluck="name",
    )

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

    for penalty_name in penalty_names:
        frappe.delete_doc("Discipline Penalty", penalty_name, force=True, ignore_permissions=True)
        _log("info", "cascade_deleted_discipline_penalty", penalty=penalty_name, attendance=attendance_name)

    ledger_names = frappe.get_all(
        "Employee Grace Ledger",
        filters={"attendance": attendance_name},
        pluck="name",
    )
    for ledger_name in ledger_names:
        frappe.delete_doc("Employee Grace Ledger", ledger_name, force=True, ignore_permissions=True)
        _log("info", "cascade_deleted_grace_ledger", ledger=ledger_name, attendance=attendance_name)

    consumed_preauths = frappe.get_all(
        "Attendance Pre-Authorization",
        filters={"attendance": attendance_name, "status": "Consumed"},
        pluck="name",
    )
    for preauth_name in consumed_preauths:
        # Bypass the status-transition validator: this is a system-driven revert,
        # not a manual workflow move.
        frappe.db.sql(
            """
            UPDATE `tabAttendance Pre-Authorization`
            SET status = 'Approved', attendance = NULL, modified = NOW()
            WHERE name = %(name)s AND status = 'Consumed'
            """,
            {"name": preauth_name},
        )
        _log(
            "info",
            "cascade_reverted_pre_authorization",
            pre_authorization=preauth_name,
            attendance=attendance_name,
        )

    seeder_names: list[str] = []
    if frappe.db.exists("DocType", "Dev Attendance Seeder"):
        seeder_names = frappe.get_all(
            "Dev Attendance Seeder",
            filters={"created_attendance": attendance_name},
            pluck="name",
        )
        for seeder_name in seeder_names:
            frappe.delete_doc("Dev Attendance Seeder", seeder_name, force=True, ignore_permissions=True)
            _log(
                "info",
                "cascade_deleted_dev_seeder",
                seeder=seeder_name,
                attendance=attendance_name,
            )

    total = len(penalty_names) + len(ledger_names) + len(consumed_preauths) + len(seeder_names)
    if total:
        _log(
            "info",
            "cascade_cancel_complete",
            attendance=attendance_name,
            penalties=len(penalty_names),
            ledgers=len(ledger_names),
            pre_authorizations=len(consumed_preauths),
            seeders=len(seeder_names),
        )
