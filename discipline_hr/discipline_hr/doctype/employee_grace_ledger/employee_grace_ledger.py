# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class EmployeeGraceLedger(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        allowed_minutes: DF.Int
        attendance: DF.Link | None
        attendance_permission: DF.Link | None
        consumed_minutes: DF.Int
        date: DF.Date | None
        discipline_penalty: DF.Link | None
        employee: DF.Link | None
        employee_name: DF.Data | None
        error_log: DF.SmallText | None
        penalty_minutes: DF.Int
        period_end: DF.Date | None
        period_start: DF.Date | None
        remaining_minutes: DF.Int
        remaining_minutes_before_consume: DF.Int
        remarks: DF.SmallText | None
    # end: auto-generated types

    @frappe.whitelist()
    def retry(self):
        from discipline_hr.services.attendance_permission import retry_discipline_penalty

        retry_discipline_penalty(self)
