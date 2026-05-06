from calendar import day_name
from typing import cast

import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, today

from discipline_hr.discipline_hr.doctype.absence_penalty_policy.absence_penalty_policy import (
    AbsencePenaltyPolicy,
)
from discipline_hr.discipline_hr.doctype.attendance_penalty_policy.attendance_penalty_policy import (
    AttendancePenaltyPolicy,
)
from discipline_hr.discipline_hr.doctype.discipline_hr_settings.discipline_hr_settings import (
    DisciplineHRSettings,
)
from discipline_hr.services.utils import _log


class DisciplinePenalty(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        absence_penalty_policy: DF.Link | None
        attendance: DF.Link | None
        attendance_penalty_policy: DF.Link | None
        attendance_pre_authorization: DF.Link | None
        description: DF.SmallText | None
        employee: DF.Link
        employee_grace_ledger: DF.Link | None
        employee_name: DF.Data | None
        end_period: DF.Date | None
        error_log: DF.SmallText | None
        grace_consumed: DF.Int
        penalty_amount: DF.Currency
        penalty_minutes: DF.Int
        penalty_status: DF.Literal["", "Present", "Absent"]
        salary_component: DF.Link | None
        start_period: DF.Date | None
        status: DF.Literal["", "Auto Processed", "Pending", "Processed", "Rejected"]
        violation_date: DF.Date
        violation_number: DF.Int
    # end: auto-generated types
    def after_insert(self):
        if self.status == "Auto Processed":
            self.create_additional_salary()

    def on_update(self):
        """Trigger workflow when HR moves the penalty to a processed status."""
        if not self.has_value_changed("status"):
            return

        if self.status == "Processed":
            self.create_additional_salary()

    def validate(self):
        """Calculate and store the penalty amount before saving."""
        self.description = ""
        self.penalty_amount = self.get_penalty_amount()

    def create_additional_salary(self):
        if not flt(self.penalty_amount):
            _log(
                "info",
                "additional_salary_skipped_zero_amount",
                penalty=self.name,
                penalty_amount=self.penalty_amount,
            )
            return
        if not self.salary_component:
            _log("warning", "additional_salary_skipped_no_component", penalty=str(self.name))
            return
        existing = frappe.db.get_value(
            "Additional Salary",
            {"custom_discipline_penalty": self.name, "docstatus": ("!=", 2)},
            ["name", "docstatus"],
        )
        if existing:
            existing_name, existing_docstatus = existing
            try:
                config = self._get_discipline_hr_settings()
                if existing_docstatus == 0 and config.auto_submit_additional_salary == 1:
                    frappe.get_doc("Additional Salary", existing_name).submit()
                self.db_set("error_log", None)
                _log("info", "additional_salary_exists", penalty=self.name, additional_salary=existing_name)
            except Exception as e:
                _log(
                    "exception",
                    "additional_salary_retry_submit_failed",
                    penalty=self.name,
                    additional_salary=existing_name,
                )
                self.db_set("error_log", str(e))
            return
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
                    "custom_discipline_penalty": self.name,
                    "custom_penalty_description": self.description,
                    "overwrite_salary_structure_amount": 0,
                }
            )
            _log(
                "debug",
                "additional_salary_created",
                additional_salary=str(additional_salary),
                penalty=self.name,
            )

            additional_salary.insert()
            if config.auto_submit_additional_salary == 1:
                additional_salary.submit()

            self.db_set("error_log", None)

        except Exception as e:
            _log("exception", "additional_salary_creation_failed", penalty=self.name, employee=self.employee)
            self.error_log = str(e)
            self.db_set("error_log", self.error_log)

    @frappe.whitelist()
    def retry(self):
        """Retry creating the additional salary if it previously failed."""
        self.create_additional_salary()

    def _get_employee_daily_rate(self):
        """Get employee daily rate from Salary Structure Assignment.

        Filters by ``from_date <= violation_date`` and picks the latest such
        assignment, so retroactive raises do not silently rewrite the amount of
        a historical penalty.

        Uses `salary_basis` setting to determine whether the rate
        is computed from base salary only or total (base + variable).
        """
        assignment = frappe.db.get_value(
            "Salary Structure Assignment",
            {
                "employee": self.employee,
                "docstatus": 1,
                "from_date": ("<=", self.violation_date or today()),
            },
            ["base", "variable"],
            order_by="from_date desc",
        )
        _log("debug", "salary_structure_assignment_found", employee=self.employee, assignment=str(assignment))
        if assignment:
            config = frappe.get_cached_doc("Discipline HR Settings")
            base, variable = assignment
            month_days = cint(config.month_days) or 30
            deduction_type = frappe.scrub(config.salary_basis)

            if deduction_type == "total":
                daily_rate = (base + variable) / month_days
            else:
                daily_rate = base / month_days
            _log(
                "debug",
                "daily_rate_fetched",
                employee=self.employee,
                base=str(assignment),
                daily_rate=daily_rate,
            )
            return daily_rate
        frappe.throw(
            f"No active Salary Structure Assignment found for {self.employee}. Cannot calculate penalty."
        )

    def get_penalty_amount(self):
        """Calculate Deduction amount based on Configuration"""
        if self.penalty_status == "Present":
            if not self.attendance_penalty_policy:
                _log("warning", "attendance_penalty_policy_not_set", penalty=self.name)
                return 0.0

            penalty_type = frappe.get_value(
                "Attendance Penalty Policy", self.attendance_penalty_policy, "penalty_type"
            )
            penalty_type = f"Attendance {penalty_type}"

            _log(
                "debug",
                "penalty_type_found",
                policy=self.attendance_penalty_policy,
                penalty_type=penalty_type,
            )
        elif self.penalty_status == "Absent":
            if not self.absence_penalty_policy:
                _log("warning", "absence_penalty_policy_not_set", penalty=self.name)
                return 0.0

            penalty_type = frappe.get_value(
                "Absence Penalty Policy", self.absence_penalty_policy, "penalty_type"
            )
            penalty_type = f"Absence {penalty_type}"

            _log("debug", "penalty_type_found", policy=self.absence_penalty_policy, penalty_type=penalty_type)
        else:
            _log("warning", "penalty_policy_not_set", penalty=self.name)
            return 0.0

        # Get Penalty
        handlers = {
            "Attendance Fixed Per Hour": self._fixed_per_hour_deduction,
            "Attendance Penalty Matrix": self._penalty_matrix_deduction,
            "Attendance Factor": self._factor_deduction,
            "Absence Penalty Matrix": self._absence_penalty_matrix,
            "Absence Special Days": self._special_day_deduction,
            "Absence Matrix & Special Days": self._matrix_and_special_days,
        }
        handler = handlers.get(penalty_type)

        if not handler:
            _log("error", "unknown_penalty_type", penalty_type=penalty_type)
            return 0.0

        return handler()

    def _matrix_deduction_from_policy(self, policy_doc: Document, label: str) -> float:
        """Calculate penalty using a violation-number lookup table.

        Finds the matrix row matching ``violation_number``; uses the last row
        if no exact match exists. Returns ``daily_rate * percentage``.

        Args:
            policy_doc: The penalty policy document containing ``penalty_matrix``.
            label: Human-readable label for log messages (e.g. "Discipline Penalty").

        Returns:
            Penalty amount as a float.
        """
        matrix = policy_doc.penalty_matrix or []
        row = next(
            (r for r in matrix if r.violation_number == self.violation_number),
            None,
        )

        if not row and matrix:
            row = max(matrix, key=lambda r: r.violation_number)

        if not row:
            _log("warning", "penalty_matrix_empty", policy=policy_doc.name)
            return 0

        self.description = row.description or ""
        percentage = flt(row.percentage)

        _log(
            "debug",
            "matrix_percentage_fetched",
            label=label,
            penalty=self.name,
            policy=policy_doc.name,
            percentage=percentage,
        )

        return flt(self._get_employee_daily_rate() * percentage)

    def _special_day_deduction(self):
        """Calculate penalty as ``daily_rate * percentage_of_daily_rate`` for the violation weekday.

        Looks up the violation date's weekday in the policy's ``special_days``
        table. Returns 0 if the weekday has no entry.

        Returns:
            Penalty amount as a float.
        """
        policy_doc = self._get_absence_penalty_policy_doc()
        violation_day = day_name[getdate(self.violation_date).weekday()]
        special_days = policy_doc.special_days or []
        row = next((r for r in special_days if r.week_day == violation_day), None)

        if not row:
            _log("info", "no_special_day_entry", day=violation_day, policy=policy_doc.name)
            return 0

        self.description = row.description or ""
        percentage = flt(row.percentage_of_daily_rate)

        _log(
            "debug",
            "special_day_percentage_fetched",
            day=violation_day,
            penalty=self.name,
            policy=policy_doc.name,
            percentage=percentage,
        )
        return flt(self._get_employee_daily_rate() * percentage)

    def _matrix_and_special_days(self):
        special_amount = self._special_day_deduction()
        special_desc = self.description or ""
        matrix_amount = self._absence_penalty_matrix()
        matrix_desc = self.description or ""
        self.description = "\n".join(filter(None, [special_desc, matrix_desc]))
        return special_amount + matrix_amount

    def _penalty_matrix_deduction(self):
        return self._matrix_deduction_from_policy(
            self._get_attendance_penalty_policy_doc(), "Discipline Penalty"
        )

    def _absence_penalty_matrix(self) -> float:
        return self._matrix_deduction_from_policy(self._get_absence_penalty_policy_doc(), "Absence Penalty")

    def _fixed_per_hour_deduction(self):
        """Calculate penalty as ``penalty_minutes * (rate_per_hour / 60)``.

        Returns:
            Penalty amount as a float.
        """
        at_pp = self._get_attendance_penalty_policy_doc()

        # Calculate rate per minute
        rate_per_minute = at_pp.rate_per_hour / 60
        _log(
            "info",
            "fixed_per_hour_rate",
            employee=self.employee,
            policy=at_pp.name,
            rate_per_hour=at_pp.rate_per_hour,
            rate_per_minute=rate_per_minute,
        )

        return self.penalty_minutes * rate_per_minute

    def _get_absence_penalty_policy_doc(self):
        """Fetch and return the linked ``AbsencePenaltyPolicy`` document."""
        return cast(
            AbsencePenaltyPolicy,
            frappe.get_cached_doc("Absence Penalty Policy", self.absence_penalty_policy),
        )

    def _get_attendance_penalty_policy_doc(self):
        """Fetch and return the linked ``AttendancePenaltyPolicy`` document."""
        return cast(
            AttendancePenaltyPolicy,
            frappe.get_cached_doc("Attendance Penalty Policy", self.attendance_penalty_policy),
        )

    def _factor_deduction(self) -> float:
        at_pp = self._get_attendance_penalty_policy_doc()
        factor = flt(at_pp.deducted_minutes_factor)

        if not factor:
            _log(
                "warning",
                "factor_deduction_skipped_zero_factor",
                employee=self.employee,
                policy=self.attendance_penalty_policy,
            )
            return 0.0

        minute_rate = self._get_minute_rate()
        if not minute_rate:
            return 0.0

        deduction = self.penalty_minutes * factor * minute_rate
        _log(
            "debug",
            "factor_deduction_calculated",
            employee=self.employee,
            penalty_minutes=self.penalty_minutes,
            factor=factor,
            minute_rate=minute_rate,
            deduction=deduction,
        )
        return flt(deduction)

    def _get_minute_rate(self) -> float:
        """Daily rate divided by shift hours divided by 60"""
        from frappe.utils import time_diff_in_hours

        attendance = frappe.get_cached_doc("Attendance", self.attendance)

        if not attendance.shift:
            _log("error", "minute_rate_no_shift", employee=self.employee, attendance=self.attendance)
            return 0.0

        shift = frappe.get_cached_doc("Shift Type", attendance.shift)
        shift_hours = time_diff_in_hours(shift.end_time, shift.start_time)

        if not shift_hours:
            _log("error", "minute_rate_zero_shift_hours", shift=attendance.shift)
            return 0.0

        daily_rate = self._get_employee_daily_rate()
        return flt(daily_rate / shift_hours / 60)

    def _get_discipline_hr_settings(self) -> Document:
        try:
            settings_doctype = "Discipline HR Settings"
            config = frappe.get_cached_doc(settings_doctype)
            return cast(DisciplineHRSettings, config)
        except Exception:
            _log("exception", "discipline_hr_settings_fetch_failed", doctype=settings_doctype)
