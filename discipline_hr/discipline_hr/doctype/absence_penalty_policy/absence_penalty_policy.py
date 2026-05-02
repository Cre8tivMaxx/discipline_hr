# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname


class AbsencePenaltyPolicy(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        from discipline_hr.discipline_hr.doctype.penalty_matrix.penalty_matrix import PenaltyMatrix
        from discipline_hr.discipline_hr.doctype.special_days.special_days import SpecialDays

        penalty_matrix: DF.Table[PenaltyMatrix]
        penalty_type: DF.Literal["", "Penalty Matrix", "Special Days", "Matrix & Special Days"]
        special_days: DF.Table[SpecialDays]
    # end: auto-generated types

    def autoname(self):
        """Build the document name from the penalty type, matching Attendance Penalty Policy.

        Examples:
            ``Penalty Matrix-01``
            ``Special Days-01``
            ``Matrix & Special Days-01``
        """
        self.name = make_autoname(f"{self.penalty_type}-.##")

    def validate(self):
        seen = set()
        for row in self.special_days:
            if row.week_day in seen:
                frappe.throw(
                    _("Row {0}: Week Day {1} is already defined in Special Days").format(
                        row.idx, row.week_day
                    )
                )
            seen.add(row.week_day)
