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
        salary_basis: DF.Literal["Base", "Total"]
        attendance_penalty_policy: DF.Link | None
        auto_process_attendance_penalty: DF.Check
        auto_process_attendance_permission: DF.Check
        auto_submit_additional_salary: DF.Check
        cascade_cancel_attendance: DF.Check
        default_penalty_notification: DF.Link | None
        default_pending_notification: DF.Link | None
        extra_minutes_penalty_policy: DF.Link | None
        ignore_grace_ledger_duplicates: DF.Check
        month_days: DF.Int
        penalize_manual_attendance_permissions: DF.Check
        salary_component: DF.Link | None
        split_permissions_and_penalties: DF.Check
    # end: auto-generated types

    NOTIFICATION_FIELDS = ("default_pending_notification", "default_penalty_notification")

    def validate(self):
        self.validate_extra_minutes_penalty_policy()

    def on_update(self):
        self.toggle_notifications()

    def toggle_notifications(self):
        previous = self.get_doc_before_save()
        for field in self.NOTIFICATION_FIELDS:
            old_value = previous.get(field) if previous else None
            new_value = self.get(field)

            if old_value == new_value:
                continue

            if old_value:
                frappe.db.set_value("Notification", old_value, "enabled", 0)

            if new_value:
                frappe.db.set_value("Notification", new_value, "enabled", 1)

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
