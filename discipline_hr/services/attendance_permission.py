import frappe
from frappe.utils import cint

from discipline_hr.services.grace import calculate_consumed_grace_minutes


def process_submitted_attendance_permission(doc):
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
	ledger = frappe.new_doc("Employee Grace Ledger")
	ledger.employee = permission_doc.employee
	ledger.period_start = permission_doc.date
	ledger.period_end = permission_doc.date
	ledger.consumed_minutes = permission_doc.minutes
	ledger.insert(ignore_permissions=True)
