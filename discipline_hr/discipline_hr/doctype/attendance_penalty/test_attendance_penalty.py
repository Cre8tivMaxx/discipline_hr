# Copyright (c) 2026, Abdelrahman Elsayed and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate


class TestAttendancePenalty(FrappeTestCase):
    def setUp(self):
        # Create Employee
        self.employee = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": "Test",
                "company": "_Test Company",
                "gender": "Male",
                "date_of_birth": getdate("2000-5-5"),
                "date_of_joining": getdate("2024-12-05"),
            }
        ).insert()

        # Create Salary Structure Assignment
        frappe.get_doc(
            {
                "doctype": "Salary Structure Assignment",
                "employee": self.employee.name,
                "base": 8000,
                "from_date": "2026-01-01",
                "docstatus": 1,
            }
        ).insert()

        # Create Attendance Penalty Policy
        self.policy = frappe.get_doc(
            {"doctype": "Attendance Penalty Policy", "penalty_type": "Fixed Per Hour", "rate_per_hour": 60}
        ).insert()

        self.penalty = frappe.get_doc(
            {
                "doctype": "Attendance Penalty",
                "employee": self.employee.name,
                "attendance_penalty_policy": self.policy.name,
                "penalty_minutes": 30,
            }
        ).insert()

    def tearDown(self):
        self.employee.remove()
        return super().tearDown()

    def test_fixed_per_hour_penalty(self):
        expected = 30  # 60 per hour
        self.assertEqual(self.penalty.penalty_minutes == expected)
