# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class PenaltyMatrix(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        description: DF.Data | None
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        percentage: DF.Float
        violation_number: DF.Int
    # end: auto-generated types
    pass
