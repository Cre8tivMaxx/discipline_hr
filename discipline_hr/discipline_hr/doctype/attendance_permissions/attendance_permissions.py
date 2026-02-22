# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt
from typing import cast

import frappe
from frappe.model.document import Document
from frappe.utils import cint

from discipline_hr.discipline_hr.doctype.attendance_violation.attendance_violation import (
	AttendanceViolation,
)
from discipline_hr.discipline_hr.doctype.employee_grace_ledger.employee_grace_ledger import (
	EmployeeGraceLedger,
)
from discipline_hr.events.attendance import _calculate_consumed_grace_minutes


class AttendancePermissions(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		attendance: DF.Link
		auto_created: DF.Check
		date: DF.Date | None
		employee: DF.Link
		minutes: DF.Int
		reason: DF.SmallText | None
		status: DF.Literal["Accepted", "Pending", "Rejected"]
	# end: auto-generated types

	def on_submit(self):
		self.process_submitted_attendance_permission

	def process_submitted_attendance_permission(self):
		if not self.employee or not self.attendance or not self.minutes:
			return

		attendance = frappe.get_doc("Attendance", self.attendance)
		self._create_attendance_violation(self, attendance)
		self._create_grace_ledger(self)

	def _create_attendance_violation(self, attendance):
		if not attendance.shift:
			return

		violation = cast(AttendanceViolation, frappe.new_doc("Attendance Violation"))
		violation.employee = self.employee
		violation.attendance = self.attendance
		violation.violation_date = self.date or attendance.attendance_date
		violation.deviation_minutes = cint(attendance.custom_late_entry_minutes) + cint(
			attendance.custom_early_exist_minutes
		)

		shift_doc = frappe.get_cached_doc("Shift Type", attendance.shift)
		violation.grace_consumed = _calculate_consumed_grace_minutes(attendance, shift_doc)
		violation.penalty_minutes = self.minutes
		violation.insert(ignore_if_duplicate=True, ignore_permissions=True)

	def _create_grace_ledger(self):
		ledger = cast(EmployeeGraceLedger, frappe.new_doc("Employee Grace Ledger"))
		ledger.employee = self.employee
		ledger.period_start = self.date
		ledger.period_end = self.date
		ledger.consumed_minutes = self.minutes
		ledger.insert(ignore_permissions=True)
