from typing import cast

import frappe
from frappe.utils import cint, get_datetime, time_diff_in_seconds
from hrms.hr.doctype.attendance.attendance import Attendance
from hrms.hr.doctype.shift_assignment.shift_assignment import (
	get_actual_start_end_datetime_of_shift,
)


def get_grace_details(doc, method=None):
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

	late_grace = shift_doc.late_entry_grace_period or 0
	early_grace = shift_doc.early_exit_grace_period or 0

	doc.custom_late_after_grace_minutes = cint(max(0, doc.custom_late_entry_minutes - late_grace))

	doc.custom_early_after_grace_minutes = cint(max(0, doc.custom_early_exist_minutes - early_grace))

	doc.custom_penalty_minutes = doc.custom_late_after_grace_minutes + doc.custom_early_after_grace_minutes
