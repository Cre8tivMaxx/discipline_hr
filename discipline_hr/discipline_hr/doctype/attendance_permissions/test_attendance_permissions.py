# Copyright (c) 2026, Abdelrahman Elsayed and Contributors
# See license.txt
from typing import cast

import frappe
from frappe.tests.utils import FrappeTestCase

from discipline_hr.discipline_hr.doctype.discipline_hr_settings.discipline_hr_settings import (
    DisciplineHRSettings,
)
from discipline_hr.services.test_attendance_permission import (
    create_attendance_permission,
    make_employee_with_attendance,
)


class TestAttendancePermissions(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        if not frappe.db.exists("Attendance Penalty Policy", {"penalty_type": "Fixed Per Hour"}):
            cls.policy = frappe.get_doc(
                {
                    "doctype": "Attendance Penalty Policy",
                    "penalty_type": "Fixed Per Hour",
                    "rate_per_hour": 60,
                }
            ).insert(ignore_permissions=True)
        else:
            cls.policy = frappe.get_last_doc("Attendance Penalty Policy", {"penalty_type": "Fixed Per Hour"})

        if not frappe.db.exists("Salary Component", "_Test Discipline Deduction"):
            cls.salary_component = frappe.get_doc(
                {
                    "doctype": "Salary Component",
                    "salary_component": "_Test Discipline Deduction",
                    "salary_component_abbr": "tdd",
                    "type": "Deduction",
                }
            ).insert(ignore_permissions=True)
        else:
            cls.salary_component = frappe.get_doc("Salary Component", "_Test Discipline Deduction")

        settings = frappe.get_single("Discipline HR Settings")
        settings.attendance_penalty_policy = cls.policy.name
        settings.salary_component = cls.salary_component.name
        settings.auto_process_attendance_penalty = 1
        settings.ignore_grace_ledger_duplicates = 0
        settings.penalize_manual_attendance_permissions = 0
        settings.flags.ignore_validate = True
        settings.flags.ignore_links = True
        settings.save(ignore_permissions=True)

        if not frappe.db.exists("Shift Type", "_Test Manual ATP Shift"):
            cls.shift_type = frappe.get_doc(
                {
                    "doctype": "Shift Type",
                    "name": "_Test Manual ATP Shift",
                    "start_time": "08:00:00",
                    "end_time": "17:00:00",
                    "late_entry_grace_period": 5,
                    "early_exit_grace_period": 5,
                    "custom_period_start_date": "2026-01-01",
                    "custom_period_end_date": "2026-12-31",
                    "custom_total_allowed_grace_minutes": 60,
                    "custom_minimum_grace_minutes": 0,
                    "custom_salary_component": cls.salary_component.name,
                    "custom_attendance_penalty_policy": cls.policy.name,
                }
            ).insert(ignore_permissions=True)
        else:
            cls.shift_type = frappe.get_doc("Shift Type", "_Test Manual ATP Shift")

    def test_manual_created_attendance_permission_create_gl_without_penalty(self):
        """Manual Created Attendance Permission, should create EGL and not a penalty"""
        settings = cast(DisciplineHRSettings, frappe.get_single("Discipline HR Settings"))
        settings.penalize_manual_attendance_permissions = 0
        settings.save(ignore_permissions=True)

        employee, attendance = make_employee_with_attendance(
            self.shift_type, "_test_auto_created0@email.com", date="2026-07-01"
        )
        p = create_attendance_permission(self, employee, 100, auto_created=0, attendance=attendance)

        penalty = frappe.get_value(
            "Discipline Penalty",
            filters={"attendance_permission": p.name},
            fieldname="attendance_permission",
        )

        gl = frappe.get_value(
            "Employee Grace Ledger",
            filters={"attendance_permission": p.name},
            fieldname="attendance_permission",
        )
        self.assertIsNotNone(gl, "Employee Grace Ledger is not created!")
        self.assertIsNone(penalty, "Penalty should NOT be created for manual attendance permission")

    def test_penalize_manual_attendance_permissions(self):
        """if ``Penalize if Manually Created Permission`` == 1, a penalty should be created"""
        settings = cast(DisciplineHRSettings, frappe.get_single("Discipline HR Settings"))
        settings.penalize_manual_attendance_permissions = 1
        settings.save(ignore_permissions=True)

        employee, attendance = make_employee_with_attendance(
            self.shift_type, "_test_penalize_manual@email.com", date="2026-07-01"
        )
        p = create_attendance_permission(self, employee, 100, auto_created=0, attendance=attendance)

        penalty = frappe.get_value(
            "Discipline Penalty",
            filters={"attendance_permission": p.name},
            fieldname="attendance_permission",
        )

        gl = frappe.get_value(
            "Employee Grace Ledger",
            filters={"attendance_permission": p.name},
            fieldname="attendance_permission",
        )
        self.assertIsNotNone(gl, "Employee Grace Ledger is not created!")
        self.assertIsNotNone(
            penalty, "Penalty should be created for manually created permission when setting is enabled"
        )
