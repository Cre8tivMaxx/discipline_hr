# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt
from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate

ACTIVE_STATES = ("Draft", "Pending Approval", "Approved")
ALLOWED_TRANSITIONS = {
    "Draft": {"Pending Approval", "Approved", "Rejected", "Expired"},
    "Pending Approval": {"Approved", "Rejected", "Expired"},
    "Approved": {"Consumed", "Expired"},
    "Consumed": set(),
    "Rejected": set(),
    "Expired": set(),
}


class AttendancePreAuthorization(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        attendance: DF.Link | None
        date: DF.Date
        employee: DF.Link
        employee_name: DF.Data | None
        kind: DF.Literal["Late", "Early", "Both"]
        minutes: DF.Int
        reason: DF.SmallText | None
        shift_type: DF.Link | None
        status: DF.Literal["", "Draft", "Pending Approval", "Approved", "Consumed", "Rejected", "Expired"]
    # end: auto-generated types

    def validate(self) -> None:
        if not self.shift_type:
            self.shift_type = self._resolve_shift_type()
        self.validate_status_transitions()
        self.validate_shift_minimum_grace()
        self.validate_no_overlapping_approved_preauth()

    def before_save(self) -> None:
        """If auto-approve is enabled, fast-track new Draft records to Approved."""
        if self.is_new() and self.status in ("Draft", None, ""):
            config = frappe.get_cached_doc("Discipline HR Settings")
            if cint(config.auto_approve_pre_authorization) == 1:
                self.status = "Approved"

    def _resolve_shift_type(self) -> str | None:
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

    def validate_shift_minimum_grace(self) -> None:
        if not self.shift_type or not self.minutes:
            return
        min_grace = frappe.get_value("Shift Type", self.shift_type, "custom_minimum_grace_minutes")
        self.minutes = max(cint(min_grace), cint(self.minutes))

    def validate_no_overlapping_approved_preauth(self) -> None:
        """Reject a second active pre-auth for the same (employee, date, slice).

        Any active state (Draft / Pending Approval / Approved) blocks another
        active record for the same slot — a Draft is a pending claim and should
        not silently coexist with an existing Approved.

        ``kind=Both`` conflicts with both ``Late`` and ``Early``.
        """
        if self.status not in ACTIVE_STATES:
            return

        conflicting_kinds = {"Both", self.kind}
        if self.kind == "Both":
            conflicting_kinds |= {"Late", "Early"}

        existing = frappe.db.exists(
            "Attendance Pre-Authorization",
            {
                "name": ("!=", self.name or ""),
                "employee": self.employee,
                "date": self.date,
                "kind": ("in", list(conflicting_kinds)),
                "status": ("in", ACTIVE_STATES),
            },
        )
        if existing:
            frappe.throw(
                _("An active Pre-Authorization ({0}) already covers this employee, date, and slice.").format(
                    existing
                )
            )

    def validate_status_transitions(self) -> None:
        if self.is_new() or not self.has_value_changed("status"):
            return
        previous_status = (self.get_doc_before_save() or {}).get("status")
        if self.status not in ALLOWED_TRANSITIONS.get(previous_status, set()):
            frappe.throw(
                _("Cannot move Pre-Authorization from {0} to {1}.").format(previous_status, self.status)
            )
