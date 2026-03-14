# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class DisciplineHRSettings(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        absence_penalty_policy: DF.Link | None
        attendance_penalty_policy: DF.Link | None
        auto_process_attendance_penalty: DF.Check
        auto_process_attendance_permission: DF.Check
        auto_submit_additional_salary: DF.Check
        default_penalty_notification: DF.Link | None
        default_pending_notification: DF.Link | None
        extra_minutes_penalty_policy: DF.Link | None
        ignore_grace_ledger_duplicates: DF.Check
        salary_component: DF.Link | None
        split_permissions_and_penalties: DF.Check
    # end: auto-generated types

    def validate(self):
        self.validate_extra_minutes_penalty_policy()

    def validate_extra_minutes_penalty_policy(self):
        if not self.extra_minutes_penalty_policy:
            return
        penalty_type = frappe.db.get_value(
            "Attendance Penalty Policy", self.extra_minutes_penalty_policy, "penalty_type"
        )
        if penalty_type not in ("Factor", "Fixed Per Hour"):
            frappe.throw(
                frappe._(
                    "Extra Minutes Penalty Policy must be of type Factor or Fixed Per Hour, not {0}."
                ).format(penalty_type)
            )
