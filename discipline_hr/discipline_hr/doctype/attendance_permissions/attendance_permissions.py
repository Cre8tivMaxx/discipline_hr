# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from discipline_hr.services.attendance_permission import process_submitted_attendance_permission


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
		shift_type: DF.Link | None
		status: DF.Literal["Accepted", "Pending", "Rejected"]
	# end: auto-generated types

	def before_save(self):
		process_submitted_attendance_permission(self)
