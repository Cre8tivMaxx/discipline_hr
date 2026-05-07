# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt
from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class DisciplineHRSettings(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        absence_penalty_policy: DF.Link | None
        attendance_penalty_policy: DF.Link | None
        auto_approve_pre_authorization: DF.Check
        auto_process_attendance_penalty: DF.Check
        auto_submit_additional_salary: DF.Check
        month_days: DF.Int
        pre_authorization_expiry_days: DF.Int
        pre_authorization_surplus_policy: DF.Link | None
        salary_basis: DF.Literal["Base", "Total"]
        salary_component: DF.Link | None
    # end: auto-generated types

    def validate(self):
        self.validate_pre_authorization_surplus_policy()

    def validate_pre_authorization_surplus_policy(self):
        if not self.pre_authorization_surplus_policy:
            return
        penalty_type = frappe.db.get_value(
            "Attendance Penalty Policy", self.pre_authorization_surplus_policy, "penalty_type"
        )
        if penalty_type not in ("Factor", "Fixed Per Hour"):
            frappe.throw(
                _(
                    "Pre-Authorization Surplus Policy must be of type Factor or Fixed Per Hour, not {0}."
                ).format(penalty_type)
            )
