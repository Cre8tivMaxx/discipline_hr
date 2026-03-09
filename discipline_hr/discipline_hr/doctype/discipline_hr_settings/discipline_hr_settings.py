# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class DisciplineHRSettings(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        attendance_penalty_policy: DF.Link | None
        auto_process_attendance_penalty: DF.Check
        auto_process_attendance_permission: DF.Check
        auto_submit_additional_salary: DF.Check
        default_penalty_notification: DF.Link | None
        default_pending_notification: DF.Link | None
        ignore_grace_ledger_duplicates: DF.Check
        salary_component: DF.Link | None
    # end: auto-generated types
    pass
