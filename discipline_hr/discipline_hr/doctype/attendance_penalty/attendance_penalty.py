# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class AttendancePenalty(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        attendance: DF.Link
        attendance_permission: DF.Link | None
        auto_create_salary: DF.Check
        deviation_minutes: DF.Int
        employee: DF.Link
        employee_grace_ledger: DF.Link | None
        end_period: DF.Date | None
        final_penalty_type: DF.Literal["", "Minutes", "Percentage of Day", "Full Day", "Warning Only"]
        final_penalty_value: DF.Float
        grace_consumed: DF.Int
        penalty_amount: DF.Currency
        penalty_minutes: DF.Int
        salary_component: DF.Link | None
        start_period: DF.Date | None
        status: DF.Literal["", "Pending", "Approved", "Rejected"]
        violation_date: DF.Date
        violation_number: DF.Int
    # end: auto-generated types
    pass
