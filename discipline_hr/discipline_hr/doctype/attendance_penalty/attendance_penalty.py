# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt
from typing import cast

import frappe
from frappe.model.document import Document
from frappe.utils import flt

from discipline_hr.discipline_hr.doctype.attendance_penalty_policy.attendance_penalty_policy import (
    AttendancePenaltyPolicy,
)
from discipline_hr.services.utils import logger


class AttendancePenalty(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        attendance: DF.Link
        attendance_penalty_policy: DF.Link | None
        attendance_permission: DF.Link | None
        auto_create_salary: DF.Check
        deviation_minutes: DF.Int
        employee: DF.Link
        employee_grace_ledger: DF.Link | None
        end_period: DF.Date | None
        final_penalty_type: DF.Literal["Factor", "Fixed Per Hour", "Penalty Matrix"]
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

    # def after_insert(self):
    #     pass

    def validate(self):
        self.penalty_amount = self.get_penalty_amount()

    # def fixed_price_penalty(self):
    #     pass

    def create_additional_salary(self):
        # additional_salary = frappe.get_doc(
        #     {
        #         "doctype": "Additional Salary",
        #         "employee": self.employee,
        #         "salary_component": self.salary_component,
        #         "amount": "",
        #     }
        # )
        pass

    def _get_employee_daily_rate(self):
        """Get Employee Base from salary structure assignment to compute daily rate"""
        try:
            assignment = frappe.db.get_value(
                "Salary Structure Assignment",
                {"employee": self.employee, "docstatus": 1},
                "base",
                order_by="from_date desc",
            )
            logger.debug(
                "Found structure assignment | Employee %s | Assignment %s", self.employee, assignment
            )
            if assignment:
                # TODO Add config to let the user set the count of days in month (30).

                daily_rate = flt(assignment) / 30.0
                logger.debug(
                    "Successfully Fetched Daily rate | Employee s% | Base %s | daily_rate %s",
                    self.employee,
                    assignment,
                    daily_rate,
                )
                return daily_rate

        except Exception as e:
            logger.error(
                "Failed to get employee Salary Structure Assignment | Employee %s | Exception %s",
                self.employee,
                e,
            )
        return 0

    def get_penalty_amount(self):
        """Calculate Deduction amount based on Configuration"""
        penalty_type = frappe.get_value(
            "Attendance Penalty Policy", self.attendance_penalty_policy, "penalty_type"
        )

        logger.debug(
            "Found Penalty Type for | ATP: %s | Penalty Type: %s ",
            self.attendance_penalty_policy,
            penalty_type,
        )
        self.final_penalty_type = penalty_type

        if penalty_type == "Factor":
            pass

        if penalty_type == "Fixed Per Hour":
            return self._fixed_per_hour_deduction()

        if penalty_type == "Penalty Matrix":
            return self._penalty_matrix_deduction()

    def _penalty_matrix_deduction(self):
        at_pp = self._get_attendance_penalty_policy_doc()
        try:
            matrix = at_pp.penalty_matrix or []
            row = next(
                (r for r in matrix if r.idx == self.violation_number),
                None,
            )

            if not row and matrix:
                row = max(matrix, key=lambda r: r.idx)

            if not row:
                return 0

            percentage = flt(row.percentage)

            logger.debug(
                "Successfully fetched PM percentage | Attendance Penalty %s | PM %s | Percentage %s",
                self,
                at_pp,
                percentage,
            )

            return flt(self._get_employee_daily_rate() * percentage)
        except Exception as e:
            logger.warning(
                "Failed to fetch PM Percentage | Attendance Penalty %s | PM %s | Exception %s",
                self,
                at_pp,
                e,
            )
        return 0

    def _fixed_per_hour_deduction(self):
        at_pp = self._get_attendance_penalty_policy_doc()

        # Calculate rate per minute
        rate_per_minute = at_pp.rate_per_hour / 60
        logger.info(
            "Penalty Per minute | Employee: %s | APP: %s | Rate Per Hour: %s | Rate Per Minutes: %s",
            self.employee,
            at_pp,
            at_pp.rate_per_hour,
            rate_per_minute,
        )

        return self.penalty_minutes * rate_per_minute

    def _get_attendance_penalty_policy_doc(self):
        return cast(
            AttendancePenaltyPolicy,
            frappe.get_cached_doc("Attendance Penalty Policy", self.attendance_penalty_policy),
        )
