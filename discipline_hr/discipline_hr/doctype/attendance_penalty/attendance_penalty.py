# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt
from typing import cast

import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt, today

from discipline_hr.discipline_hr.doctype.attendance_penalty_policy.attendance_penalty_policy import (
    AttendancePenaltyPolicy,
)
from discipline_hr.discipline_hr.doctype.discipline_hr_settings.discipline_hr_settings import (
    DisciplineHRSettings,
)
from discipline_hr.discipline_hr.doctype.employee_grace_ledger.employee_grace_ledger import (
    EmployeeGraceLedger,
)
from discipline_hr.services.utils import logger


class AttendancePenalty(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        absence_penalty_policy: DF.Link | None
        attendance: DF.Link
        attendance_penalty_policy: DF.Link | None
        attendance_permission: DF.Link | None
        auto_create_salary: DF.Check
        employee: DF.Link
        employee_grace_ledger: DF.Link | None
        end_period: DF.Date | None
        error: DF.SmallText | None
        final_penalty_type: DF.Literal["Factor", "Fixed Per Hour", "Penalty Matrix"]
        grace_consumed: DF.Int
        penalty_amount: DF.Currency
        penalty_minutes: DF.Int
        penalty_status: DF.Data | None
        salary_component: DF.Link | None
        start_period: DF.Date | None
        status: DF.Literal["", "Auto Processed", "Pending", "Processed", "Rejected"]
        violation_date: DF.Date
        violation_number: DF.Int
    # end: auto-generated types

    def after_insert(self):
        if self.status in ["Auto Processed", "Processed"]:
            self.create_grace_ledger_entry()
            self.create_additional_salary()

    def on_update(self):
        """Re-trigger workflow when HR changes status to 'Accepted'."""
        status_changed = self.has_value_changed("status")
        if status_changed and self.status in ["Auto Processed", "Processed"]:
            self.create_grace_ledger_entry()
            self.create_additional_salary()

    def create_grace_ledger_entry(self):
        if frappe.db.exists("Employee Grace Ledger", {"attendance_penalty": self.name}):
            return
        ledger = cast(EmployeeGraceLedger, frappe.new_doc("Employee Grace Ledger"))
        ledger.employee = self.employee
        ledger.attendance = self.attendance
        ledger.period_start = self.start_period
        ledger.period_end = self.end_period
        ledger.allowed_minutes = 0
        ledger.consumed_minutes = -self.penalty_minutes
        ledger.penalty_minutes = 0
        ledger.attendance_penalty = self.name
        ledger.insert(ignore_permissions=True)

    def validate(self):
        """Calculate and store the penalty amount before saving."""
        self.penalty_amount = self.get_penalty_amount()

    def create_additional_salary(self):
        # TODO If salary structure raise just log the error inside the attendance penalty
        if cint(self.penalty_amount) == 0:
            logger.info("Ignore Additional Salary due amount == 0 | ATP: %s | Penalty Amount: %s")
            return
        if not self.salary_component:
            logger.warning("Couldn't create Additional Salary Salary Component is None | Penalty %s", self)
        try:
            config = self._get_discipline_hr_settings()
            additional_salary = frappe.get_doc(
                {
                    "doctype": "Additional Salary",
                    "employee": self.employee,
                    "payroll_date": self.violation_date or today(),
                    "salary_component": self.salary_component,
                    "type": "Deduction",
                    "amount": self.penalty_amount,
                    "custom_attendance_penalty": self.name,
                }
            )
            logger.debug("Created Additional Salary: %s | Attendance Penalty %s", additional_salary, self)

            additional_salary.insert()
            if config.auto_submit_additional_salary == 1:
                additional_salary.submit()

        except Exception as e:
            logger.exception(
                "Couldn't create additional salary | Attendance Penalty: %s | Employee: %s ",
                self,
                self.employee,
            )
            self.error = str(e)

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
                    "Successfully Fetched Daily rate | Employee %s | Base %s | daily_rate %s",
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
        if not self.attendance_penalty_policy:
            logger.warning("Attendance Policy is not set. %s", self)
            return 0.0

        penalty_type = frappe.get_value(
            "Attendance Penalty Policy", self.attendance_penalty_policy, "penalty_type"
        )

        logger.debug(
            "Found Penalty Type for | ATP: %s | Penalty Type: %s ",
            self.attendance_penalty_policy,
            penalty_type,
        )
        self.final_penalty_type = penalty_type

        # Get Penalty
        handlers = {
            "Fixed Per Hour": self._fixed_per_hour_deduction,
            "Penalty Matrix": self._penalty_matrix_deduction,
            "Factor": self._factor_deduction,
        }
        handler = handlers.get(penalty_type)

        if not handler:
            logger.error("Unknown Penalty Type: %s", penalty_type)
            return 0.0

        return handler()

    def _penalty_matrix_deduction(self):
        """Calculate penalty using a violation-number lookup table.

        Finds the matrix row matching ``violation_number``; uses the last row
        if no exact match exists. Returns ``daily_rate * percentage``.

        Returns:
            Penalty amount as a float.
        """
        at_pp = self._get_attendance_penalty_policy_doc()
        try:
            matrix = at_pp.penalty_matrix or []
            row = next(
                (r for r in matrix if r.violation_number == self.violation_number),
                None,
            )

            if not row and matrix:
                row = max(matrix, key=lambda r: r.violation_number)

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
        """Calculate penalty as ``penalty_minutes * (rate_per_hour / 60)``.

        Returns:
            Penalty amount as a float.
        """
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
        """Fetch and return the linked ``AttendancePenaltyPolicy`` document."""
        return cast(
            AttendancePenaltyPolicy,
            frappe.get_doc("Attendance Penalty Policy", self.attendance_penalty_policy),
        )

    def _factor_deduction(self) -> float:
        at_pp = self._get_attendance_penalty_policy_doc()
        factor = flt(at_pp.deducted_minutes_factor)

        if not factor:
            logger.warning(
                "Factor deduction skipped: deducted_minutes_factor is 0 | Employee: %s | Policy: %s",
                self.employee,
                self.attendance_penalty_policy,
            )
            return 0.0

        minute_rate = self._get_minute_rate()
        if not minute_rate:
            return 0.0

        deduction = self.penalty_minutes * factor * minute_rate
        logger.debug(
            "Factor deduction | Employee: %s | Penalty Minutes: %s | Factor: %s | Minute Rate: %s | Deduction: %s",
            self.employee,
            self.penalty_minutes,
            factor,
            minute_rate,
            deduction,
        )
        return flt(deduction)

    def _get_minute_rate(self) -> float:
        """Daily rate divided by shift hours divided by 60"""
        from frappe.utils import time_diff_in_hours

        attendance = frappe.get_cached_doc("Attendance", self.attendance)

        if not attendance.shift:
            logger.error(
                "Cannot compute minute rate: no shift on attendance | Employee: %s | Attendance: %s",
                self.employee,
                self.attendance,
            )
            return 0.0

        shift = frappe.get_cached_doc("Shift Type", attendance.shift)
        shift_hours = time_diff_in_hours(shift.end_time, shift.start_time)

        if not shift_hours:
            logger.error("Cannot compute minute rate: shift_hours is 0 | Shift: %s", attendance.shift)
            return 0.0

        daily_rate = self._get_employee_daily_rate()
        return flt(daily_rate / shift_hours / 60)

    def _get_discipline_hr_settings(self) -> Document:
        try:
            settings_doctype = "Discipline HR Settings"
            config = frappe.get_cached_doc(settings_doctype)
            return cast(DisciplineHRSettings, config)
        except Exception:
            logger.exception("Cannot fetch %s DocType", settings_doctype)
