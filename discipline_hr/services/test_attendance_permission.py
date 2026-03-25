# Copyright (c) 2026, Abdelrahman Elsayed and Contributors
# See license.txt

from typing import cast
from unittest import TestCase
from unittest.mock import MagicMock, call, patch

import frappe
from erpnext.setup.doctype.employee.test_employee import make_employee
from frappe.tests.utils import FrappeTestCase

from discipline_hr.discipline_hr.doctype.discipline_hr_settings.discipline_hr_settings import (
    DisciplineHRSettings,
)
from discipline_hr.events.attendance import cascade_cancel_attendance


class TestCascadeCancelAttendance(TestCase):
    """Tests for cascade_cancel_attendance — the on_cancel handler for Attendance."""

    def _make_attendance_doc(self, name="ATT-0001"):
        doc = MagicMock()
        doc.name = name
        return doc

    def _enable_cascade(self, mock_frappe):
        """Configure the mock so the cascade_cancel_attendance setting is enabled."""
        config = MagicMock()
        config.cascade_cancel_attendance = 1
        mock_frappe.get_cached_doc.return_value = config

    @patch("discipline_hr.events.attendance.frappe")
    def test_cascade_cancel_deletes_all_downstream_docs(self, mock_frappe):
        """Normal path: permission + ledger + penalty + additional salary all deleted."""
        self._enable_cascade(mock_frappe)
        doc = self._make_attendance_doc()

        # Build additional salary mock with docstatus=0 (draft)
        sal_mock = MagicMock()
        sal_mock.name = "SAL-001"
        sal_mock.docstatus = 0
        mock_frappe.get_all.side_effect = [
            ["PEN-001"],  # penalties
            [sal_mock],  # additional salaries
            ["LED-001", "LED-002"],  # ledgers
            ["PRM-001"],  # permissions
        ]

        cascade_cancel_attendance(doc)

        # Verify delete_doc calls (leaf-first order)
        delete_calls = mock_frappe.delete_doc.call_args_list
        # Additional Salary
        self.assertEqual(
            delete_calls[0], call("Additional Salary", "SAL-001", force=True, ignore_permissions=True)
        )
        # Discipline Penalty
        self.assertEqual(
            delete_calls[1], call("Discipline Penalty", "PEN-001", force=True, ignore_permissions=True)
        )
        # Grace Ledgers
        self.assertEqual(
            delete_calls[2], call("Employee Grace Ledger", "LED-001", force=True, ignore_permissions=True)
        )
        self.assertEqual(
            delete_calls[3], call("Employee Grace Ledger", "LED-002", force=True, ignore_permissions=True)
        )
        # Attendance Permission
        self.assertEqual(
            delete_calls[4], call("Attendance Permissions", "PRM-001", force=True, ignore_permissions=True)
        )

    @patch("discipline_hr.events.attendance.frappe")
    def test_cascade_cancel_cancels_submitted_additional_salary(self, mock_frappe):
        """Submitted Additional Salary (docstatus=1) is cancelled before deletion."""
        self._enable_cascade(mock_frappe)
        doc = self._make_attendance_doc()

        sal_mock = MagicMock()
        sal_mock.name = "SAL-001"
        sal_mock.docstatus = 1

        sal_doc = MagicMock()

        mock_frappe.get_all.side_effect = [
            ["PEN-001"],  # penalties
            [sal_mock],  # additional salaries
            [],  # ledgers
            [],  # permissions
        ]
        mock_frappe.get_doc.return_value = sal_doc

        cascade_cancel_attendance(doc)

        # Should fetch the doc and call cancel()
        mock_frappe.get_doc.assert_called_once_with("Additional Salary", "SAL-001")
        sal_doc.cancel.assert_called_once()
        # Then delete
        self.assertIn(
            call("Additional Salary", "SAL-001", force=True, ignore_permissions=True),
            mock_frappe.delete_doc.call_args_list,
        )

    @patch("discipline_hr.events.attendance.frappe")
    def test_cascade_cancel_no_downstream_docs(self, mock_frappe):
        """No downstream docs — function completes without errors or deletions."""
        self._enable_cascade(mock_frappe)
        doc = self._make_attendance_doc()

        mock_frappe.get_all.side_effect = [
            [],  # no penalties
            [],  # no ledgers
            [],  # no permissions
        ]

        cascade_cancel_attendance(doc)

        mock_frappe.delete_doc.assert_not_called()
        mock_frappe.get_doc.assert_not_called()

    @patch("discipline_hr.events.attendance.frappe")
    def test_cascade_cancel_only_deletes_auto_created_permissions(self, mock_frappe):
        """Only auto_created=1 permissions are queried for deletion."""
        self._enable_cascade(mock_frappe)
        doc = self._make_attendance_doc()

        mock_frappe.get_all.side_effect = [
            [],  # no penalties
            [],  # no ledgers
            ["PRM-AUTO"],  # auto-created permission
        ]

        cascade_cancel_attendance(doc)

        # Check the permissions query used auto_created=1 filter
        permissions_call = mock_frappe.get_all.call_args_list[2]
        self.assertEqual(permissions_call[0][0], "Attendance Permissions")
        self.assertEqual(permissions_call[1]["filters"]["auto_created"], 1)

    @patch("discipline_hr.events.attendance.frappe")
    def test_cascade_cancel_multiple_penalties(self, mock_frappe):
        """Multiple penalties per attendance — all are deleted along with their Additional Salaries."""
        self._enable_cascade(mock_frappe)
        doc = self._make_attendance_doc()

        sal1 = MagicMock()
        sal1.name = "SAL-001"
        sal1.docstatus = 0
        sal2 = MagicMock()
        sal2.name = "SAL-002"
        sal2.docstatus = 0

        mock_frappe.get_all.side_effect = [
            ["PEN-001", "PEN-002"],  # two penalties
            [sal1, sal2],  # two additional salaries
            [],  # no ledgers
            [],  # no permissions
        ]

        cascade_cancel_attendance(doc)

        # Both penalties deleted
        self.assertIn(
            call("Discipline Penalty", "PEN-001", force=True, ignore_permissions=True),
            mock_frappe.delete_doc.call_args_list,
        )
        self.assertIn(
            call("Discipline Penalty", "PEN-002", force=True, ignore_permissions=True),
            mock_frappe.delete_doc.call_args_list,
        )
        # Both additional salaries deleted
        self.assertIn(
            call("Additional Salary", "SAL-001", force=True, ignore_permissions=True),
            mock_frappe.delete_doc.call_args_list,
        )
        self.assertIn(
            call("Additional Salary", "SAL-002", force=True, ignore_permissions=True),
            mock_frappe.delete_doc.call_args_list,
        )

    @patch("discipline_hr.events.attendance.frappe")
    def test_cascade_cancel_disabled_skips_deletion(self, mock_frappe):
        """When cascade_cancel_attendance is disabled in settings, nothing is deleted."""
        config = MagicMock()
        config.cascade_cancel_attendance = 0
        mock_frappe.get_cached_doc.return_value = config
        doc = self._make_attendance_doc()

        cascade_cancel_attendance(doc)

        mock_frappe.get_all.assert_not_called()
        mock_frappe.delete_doc.assert_not_called()


class TestAttendancePenaltyWiring(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Employee
        cls.employee = make_employee("_test_employee_@test.com")

        # Attendance Penalty Policy
        cls.policy = frappe.get_doc(
            {"doctype": "Attendance Penalty Policy", "penalty_type": "Fixed Per Hour", "rate_per_hour": 60}
        ).insert(ignore_permissions=True)

        # Salary Component
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

        # Discipline Hr Settings
        settings = frappe.get_single("Discipline HR Settings")
        settings.attendance_penalty_policy = cls.policy.name
        settings.salary_component = cls.salary_component.name
        settings.auto_process_attendance_penalty = 1
        settings.ignore_grace_ledger_duplicates = 0
        settings.flags.ignore_validate = True
        settings.flags.ignore_links = True
        settings.save(ignore_permissions=True)

        # Shift Type
        if not frappe.db.exists("Shift Type", "_Test Discipline Shift"):
            cls.shift_type = frappe.get_doc(
                {
                    "doctype": "Shift Type",
                    "name": "_Test Discipline Shift",
                    "start_time": "08:00:00",
                    "end_time": "17:00:00",
                    "late_entry_grace_period": 5,
                    "early_exit_grace_period": 5,
                    "custom_period_start_date": "2026-01-01",
                    "custom_period_end_date": "2026-12-31",
                    "custom_total_allowed_grace_minutes": 60,
                    "custom_minimum_grace_minutes": 5,
                    "custom_salary_component": cls.salary_component.name,
                    "custom_attendance_penalty_policy": cls.policy.name,
                }
            ).insert(ignore_permissions=True)
        else:
            cls.shift_type = frappe.get_doc("Shift Type", "_Test Discipline Shift")

        # Attendance (40 min late, 10 min early exit — insert only, tests decide when to submit)
        cls.attendance = frappe.get_doc(
            {
                "doctype": "Attendance",
                "employee": cls.employee,
                "attendance_date": "2026-06-15",
                "status": "Present",
                "shift": cls.shift_type.name,
                "in_time": "2026-06-15 08:40:00",
                "out_time": "2026-06-15 16:50:00",
            }
        ).insert(ignore_permissions=True, ignore_if_duplicate=True)

    def test_auto_processed_permission_creates_ledger_and_penalty(self):
        """
        Test valid Attendance Permission -> Employee Grace Ledger -> Discipline Penalty
        """
        permission = frappe.get_doc(
            {
                "doctype": "Attendance Permissions",
                "employee": self.employee,
                "attendance": self.attendance.name,
                "shift_type": self.shift_type.name,
                "date": "2026-06-15",
                "minutes": 90,  # exceeds 60 grace → 30 penalty minutes
                "status": "Auto Processed",
            }
        ).insert(ignore_permissions=True)

        # Assert — Grace Ledger was created
        ledger = frappe.db.get_value(
            "Employee Grace Ledger",
            {"attendance_permission": permission.name},
            ["name", "penalty_minutes", "consumed_minutes"],
            as_dict=True,
        )
        self.assertIsNotNone(ledger, "Grace Ledger not created")
        self.assertEqual(ledger.consumed_minutes, 90)
        self.assertEqual(ledger.penalty_minutes, 30)

        # Assert — Discipline Penalty was created
        self.assertTrue(frappe.db.exists("Discipline Penalty", {"employee_grace_ledger": ledger.name}))

    def test_attendance_permission_pending_status(self):
        """Test pending Attendance Permission will break the workflow"""
        permission = frappe.get_doc(
            {
                "doctype": "Attendance Permissions",
                "employee": self.employee,
                "attendance": self.attendance.name,
                "shift_type": self.shift_type.name,
                "date": "2026-06-15",
                "minutes": 90,
                "status": "Pending",
            }
        ).insert(ignore_permissions=True)

        # Assert — Grace Ledger was never created
        ledger = frappe.db.get_value(
            "Employee Grace Ledger",
            {"attendance_permission": permission.name},
        )
        self.assertIsNone(ledger, "Employee Grace Ledger Created even when ATP status is Pending")

    def test_attendance_permission_with_zero_minutes(self):
        """Test if minutes <= 0  in attendance permission, break the workflow"""
        permission = frappe.get_doc(
            {
                "doctype": "Attendance Permissions",
                "employee": self.employee,
                "attendance": self.attendance.name,
                "shift_type": self.shift_type.name,
                "date": "2026-06-15",
                "minutes": 0,
                "status": "Auto Processed",
            }
        ).insert(ignore_permissions=True)

        # Assert — Grace Ledger was never created
        ledger = frappe.db.get_value(
            "Employee Grace Ledger",
            {"attendance_permission": permission.name},
        )
        self.assertIsNone(ledger, "Employee Grace Ledger Created even when ATP minutes == 0 ")

    def test_ignore_grace_ledger_duplicate(self):
        """Test ignore_grace_ledger_duplicates == 1: two permissions create only one grace-consumption ledger."""
        settings = cast(DisciplineHRSettings, frappe.get_single("Discipline HR Settings"))
        settings.ignore_grace_ledger_duplicates = 1
        settings.split_permissions_and_penalties = 0
        settings.save(ignore_permissions=True)

        employee = make_employee("_test_duplicate@test.com")
        attendance = frappe.get_doc(
            {
                "doctype": "Attendance",
                "employee": employee,
                "attendance_date": "2026-06-15",
                "status": "Present",
                "shift": self.shift_type.name,
                "in_time": "2026-06-15 08:40:00",
                "out_time": "2026-06-15 16:50:00",
            }
        ).insert(ignore_permissions=True, ignore_if_duplicate=True)

        # Clean up stale data from previous test runs
        frappe.db.delete("Employee Grace Ledger", {"attendance": attendance.name, "employee": employee})

        frappe.get_doc(
            {
                "doctype": "Attendance Permissions",
                "employee": employee,
                "attendance": attendance.name,
                "shift_type": self.shift_type.name,
                "date": "2026-06-15",
                "minutes": 120,
                "status": "Auto Processed",
            }
        ).insert(ignore_permissions=True)

        frappe.get_doc(
            {
                "doctype": "Attendance Permissions",
                "employee": employee,
                "attendance": attendance.name,
                "shift_type": self.shift_type.name,
                "date": "2026-06-15",
                "minutes": 120,
                "status": "Auto Processed",
            }
        ).insert(ignore_permissions=True)

        # Filter for grace-consumption ledgers only (discipline_penalty is unset).
        # Penalty-reversal ledgers (created by DisciplinePenalty.after_insert) have
        # discipline_penalty set, so they are excluded.
        grace_ledgers = frappe.get_all(
            "Employee Grace Ledger",
            filters={
                "attendance": attendance.name,
                "employee": employee,
                "discipline_penalty": ("is", "not set"),
            },
        )
        self.assertEqual(len(grace_ledgers), 1, "Duplicate grace-consumption ledger was created")

    # def test_consumed_so_far(self):
    #     """Test create multiple ledgers for same employee will calculate the consumed minutes (0 + 30 + 30)"""

    # def test_custom_minimum_grace_minutes(self):
    #     """Test create penalty_minutes less than custom_minimum_grace_minutes"""

    # def test_create_discipline_penalty_with_zero_minutes(self):
    #     """Test penalty minutes == 0 should not insert the discipline penalty"""

    # def test_violation_number_increment(self):
    #     """Test the violation number for the same (employee, start, end, status) is incremented (1, 2)"""

    # def test_adding_shift_penalty_policy(self):
    #     """Test penlaty policy is fetched from the Shift Type"""

    # def test_adding_config_penalty_policy(self):
    #     """Test Penalty Policy is fetched from config if it's not definted at Shift Type"""

    # def test_adding_shift_salary_component(self):
    #     """Test Salary Component is fetched from the Shift Type"""

    # def test_adding_config_salary_component(self):
    #     """Test Salary Component is fetched from config if it's not definted at Shift Type"""

    # def test_auto_process_config(self):
    #     """Test Discipline Penalty status == Auto Processed if config.auto_process_attendance_penalty == 1"""

    # def test_none_auto_process_config(self):
    #     """Test `Discipline Penalty` status == `Pending` if `config.auto_process_attendance_penalty` == 0"""
