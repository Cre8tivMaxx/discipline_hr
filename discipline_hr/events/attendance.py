from typing import cast

import frappe
from frappe.utils import cint, get_datetime, time_diff_in_seconds, today
from hrms.hr.doctype.attendance.attendance import Attendance
from hrms.hr.doctype.shift_assignment.shift_assignment import (
	get_actual_start_end_datetime_of_shift,
)

from discipline_hr.discipline_hr.doctype.attendance_permissions.attendance_permissions import (
	AttendancePermissions,
)
from discipline_hr.discipline_hr.doctype.attendance_violation.attendance_violation import (
	AttendanceViolation,
)


def calculate_attendance_penalty_minutes(doc, method=None):
	doc = cast(Attendance, doc)

	# Only calculate for Present records
	if doc.status != "Present":
		return

	if not doc.in_time or not doc.out_time:
		return

	shift_details = get_actual_start_end_datetime_of_shift(doc.employee, get_datetime(doc.in_time))

	if not shift_details:
		return

	start_datetime = shift_details["actual_start"]
	end_datetime = shift_details["actual_end"]

	# Calculate Raw Late / Early
	late_minutes = max(0, time_diff_in_seconds(doc.in_time, start_datetime)) / 60

	early_minutes = max(0, time_diff_in_seconds(end_datetime, doc.out_time)) / 60

	doc.custom_late_entry_minutes = cint(late_minutes)
	doc.custom_early_exist_minutes = cint(early_minutes)

	# Fetch Grace Directly From Shift
	if not doc.shift:
		return

	shift_doc = frappe.get_cached_doc("Shift Type", doc.shift)

	late_grace, early_grace = _get_grace_minutes(shift_doc)

	doc.custom_late_after_grace_minutes = cint(max(0, doc.custom_late_entry_minutes - late_grace))

	doc.custom_early_after_grace_minutes = cint(max(0, doc.custom_early_exist_minutes - early_grace))

	doc.custom_penalty_minutes = doc.custom_late_after_grace_minutes + doc.custom_early_after_grace_minutes

	# TODO enqueue this job or move it after_submit/on_submit
	if doc.custom_penalty_minutes:
		create_attendance_permissions(doc.employee, doc.name, doc.custom_penalty_minutes, doc.attendance_date)


def create_attendance_permissions(employee, attendance, minutes, date=""):
	doc = cast(AttendancePermissions, frappe.new_doc("Attendance Permissions"))
	if not employee:
		return
	doc.employee = employee
	doc.attendance = attendance
	doc.minutes = minutes
	doc.date = date or today()
	doc.auto_created = 1
	doc.insert(ignore_if_duplicate=True, ignore_permissions=True)


# def create_attendance_violation(doc: Attendance, method=None):
# 	if not doc.custom_penalty_minutes:
# 		return
# 	if not doc.shift:
# 		return

# 	violation = cast(AttendanceViolation, frappe.new_doc("Attendance Violation"))
# 	violation.employee = doc.employee
# 	violation.attendance = doc.name
# 	violation.violation_date = doc.attendance_date

# 	violation.deviation_minutes = doc.custom_late_entry_minutes + doc.custom_early_exist_minutes
# 	shift_doc = frappe.get_cached_doc("Shift Type", doc.shift)
# 	violation.grace_consumed = _calculate_consumed_grace_minutes(doc, shift_doc)
# 	violation.penalty_minutes = doc.custom_penalty_minutes

# 	violation.insert(ignore_if_duplicate=True, ignore_permissions=True)


def _get_grace_minutes(shift_doc):
	late_grace = shift_doc.late_entry_grace_period or 0
	early_grace = shift_doc.early_exit_grace_period or 0
	return late_grace, early_grace


def _calculate_consumed_grace_minutes(doc: Attendance, shift_doc) -> int:
	late_grace, early_grace = _get_grace_minutes(shift_doc)
	late_consumed = min(cint(doc.custom_late_entry_minutes), late_grace)
	early_consumed = min(cint(doc.custom_early_exist_minutes), early_grace)
	return cint(late_consumed + early_consumed)
