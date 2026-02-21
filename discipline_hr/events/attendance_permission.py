from typing import cast

import frappe
from frappe.utils import cint

from discipline_hr.discipline_hr.doctype.attendance_permissions.attendance_permissions import (
	AttendancePermissions,
)
from discipline_hr.discipline_hr.doctype.attendance_violation.attendance_violation import (
	AttendanceViolation,
)
from discipline_hr.discipline_hr.doctype.employee_grace_ledger.employee_grace_ledger import (
	EmployeeGraceLedger,
)
from discipline_hr.events.attendance import _calculate_consumed_grace_minutes


def create_violation_and_grace_ledger_from_permission(doc, method=None):
	doc = cast(AttendancePermissions, doc)

	if not doc.employee or not doc.attendance or not doc.minutes:
		return

	attendance = frappe.get_doc("Attendance", doc.attendance)
	_create_attendance_violation(doc, attendance)
	_create_grace_ledger(doc)


def _create_attendance_violation(permission_doc: AttendancePermissions, attendance):
	if not attendance.shift:
		return

	violation = cast(AttendanceViolation, frappe.new_doc("Attendance Violation"))
	violation.employee = permission_doc.employee
	violation.attendance = permission_doc.attendance
	violation.violation_date = permission_doc.date or attendance.attendance_date
	violation.deviation_minutes = cint(attendance.custom_late_entry_minutes) + cint(
		attendance.custom_early_exist_minutes
	)

	shift_doc = frappe.get_cached_doc("Shift Type", attendance.shift)
	violation.grace_consumed = _calculate_consumed_grace_minutes(attendance, shift_doc)
	violation.penalty_minutes = permission_doc.minutes
	violation.insert(ignore_if_duplicate=True, ignore_permissions=True)


def _create_grace_ledger(permission_doc: AttendancePermissions):
	ledger = cast(EmployeeGraceLedger, frappe.new_doc("Employee Grace Ledger"))
	ledger.employee = permission_doc.employee
	ledger.period_start = permission_doc.date
	ledger.period_end = permission_doc.date
	ledger.consumed_minutes = permission_doc.minutes
	ledger.insert(ignore_permissions=True)
