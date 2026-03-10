# Copyright (c) 2026, Abdelrahman Elsayed and Contributors
# See license.txt

from unittest.mock import MagicMock, patch

import frappe
from erpnext.setup.doctype.employee.test_employee import make_employee
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate, today
from hrms.payroll.doctype.salary_structure.test_salary_structure import (
    create_salary_structure_assignment,
    make_salary_structure,
)


class TestAttendancePenalty(FrappeTestCase):
    def setUp(self):
        # Create Employee
        self.employee = make_employee("test_employee_encashment@example.com", company="_Test Company")

        # Create Salary Structure
        salary_structure = make_salary_structure(
            "_Test Salary", "Monthly", self.employee, company="_Test Company"
        )

        # Create Salary Structure Assignment
        create_salary_structure_assignment(self.employee, salary_structure.name, company="_Test Company")

        # Create Attendance Penalty Policy
        self.policy = frappe.get_doc(
            {"doctype": "Attendance Penalty Policy", "penalty_type": "Fixed Per Hour", "rate_per_hour": 60}
        ).insert()

        self.penalty = frappe.get_doc(
            {
                "doctype": "Attendance Penalty",
                "employee": self.employee,
                "attendance_penalty_policy": self.policy.name,
                "violation_date": today(),
            }
        )
        self.penalty.flags.ignore_mandatory = True
        self.penalty.insert()

    def test_fixed_per_hour_penalty(self):
        self.penalty.penalty_minutes = 30

        mock_policy = MagicMock()
        mock_policy.rate_per_hour = 60

        with patch.object(self.penalty, "_get_attendance_penalty_policy_doc", return_value=mock_policy):
            result = self.penalty._fixed_per_hour_deduction()
        self.assertEqual(result, 30.0)
