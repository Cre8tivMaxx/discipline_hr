# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt
import frappe
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

    def after_insert(self):
        process_submitted_attendance_permission(self)

    def validate(self):
        process_submitted_attendance_permission(self)
        self.validate_shift_minimum_grace()

    def validate_shift_minimum_grace(self):
        shift = frappe.get_value("Attendance", self.attendance, "shift")
        min_grace = frappe.get_value("Shift Type", shift, "custom_minimum_grace_minutes")
        if self.minutes:
            self.minutes = max(min_grace, self.minutes)
