# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document
from frappe.utils import cint, getdate

from discipline_hr.services.attendance_permission import process_submitted_attendance_permission


class AttendancePermissions(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        attendance: DF.Link | None
        auto_created: DF.Check
        date: DF.Date
        employee: DF.Link
        employee_name: DF.Data | None
        error_log: DF.SmallText | None
        minutes: DF.Int
        reason: DF.SmallText | None
        shift_type: DF.Link | None
        status: DF.Literal["", "Auto Processed", "Processed", "Pending", "Rejected"]
    # end: auto-generated types

    @frappe.whitelist()
    def retry(self):
        # Pre-clear: _create_grace_ledger writes a fresh traceback back on failure.
        self.db_set("error_log", None, update_modified=False)
        process_submitted_attendance_permission(self)

    def after_insert(self):
        """Trigger permission workflow after the record is saved."""
        process_submitted_attendance_permission(self)

    def on_update(self):
        """Re-trigger workflow when HR changes status to 'Accepted'."""
        if self.has_value_changed("status") and self.status == "Processed":
            process_submitted_attendance_permission(self)

    def validate(self):
        """Run field validations before saving."""
        if not self.shift_type:
            self.shift_type = self._resolve_shift_type()
        self.validate_shift_minimum_grace()

    def _resolve_shift_type(self):
        """Resolve shift type from attendance, shift assignment, or employee default."""
        if self.attendance:
            return frappe.get_value("Attendance", self.attendance, "shift")

        if self.employee and self.date:
            from datetime import datetime, time

            from hrms.hr.doctype.shift_assignment.shift_assignment import get_shifts_for_date

            shifts = get_shifts_for_date(self.employee, datetime.combine(getdate(self.date), time(0, 0)))
            if shifts:
                return shifts[0].shift_type
            return frappe.db.get_value("Employee", self.employee, "default_shift")

        return None

    def validate_shift_minimum_grace(self):
        """Floor ``minutes`` to the shift's minimum grace setting."""
        shift = (
            frappe.get_value("Attendance", self.attendance, "shift") if self.attendance else self.shift_type
        )
        min_grace = frappe.get_value("Shift Type", shift, "custom_minimum_grace_minutes")
        if self.minutes:
            self.minutes = max(cint(min_grace), self.minutes)
