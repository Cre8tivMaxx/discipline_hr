# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class AttendanceViolation(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        attendance: DF.Link
        deviation_minutes: DF.Int
        employee: DF.Link
        end_period: DF.Date | None
        final_penalty_type: DF.Literal["", "Minutes", "Percentage of Day", "Full Day", "Warning Only"]
        final_penalty_value: DF.Float
        grace_consumed: DF.Int
        penalty_minutes: DF.Int
        start_period: DF.Date | None
        status: DF.Literal["", "Graced", "Penalized", "Rejected", "Pending Approval"]
        violation_date: DF.Date
        violation_number: DF.Int
    # end: auto-generated types
    pass
