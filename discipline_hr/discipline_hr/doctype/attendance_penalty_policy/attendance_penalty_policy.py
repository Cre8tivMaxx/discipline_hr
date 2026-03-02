# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
from frappe.model.naming import make_autoname


class AttendancePenaltyPolicy(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        from discipline_hr.discipline_hr.doctype.penalty_matrix.penalty_matrix import PenaltyMatrix

        deducted_minutes_factor: DF.Float
        penalty_matrix: DF.Table[PenaltyMatrix]
        penalty_type: DF.Literal["", "Factor", "Fixed Per Hour", "Penalty Matrix"]
        rate_per_hour: DF.Currency
    # end: auto-generated types
    pass

    def autoname(self):
        if self.penalty_type in ["Fixed Per Hour", "Factor"]:
            self.name = f"{self.penalty_type}-{self.rate_per_hour or self.deducted_minutes_factor}"
        else:
            self.name = make_autoname(f"{self.penalty_type}-.##")
