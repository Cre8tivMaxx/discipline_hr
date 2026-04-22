# Copyright (c) 2026, Abdelrahman Elsayed and Contributors
# See license.txt

from typing import cast
from unittest import TestCase
from unittest.mock import MagicMock, call, patch

import frappe
from erpnext.setup.doctype.employee.test_employee import make_employee
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from discipline_hr.discipline_hr.doctype.discipline_hr_settings.discipline_hr_settings import (
    DisciplineHRSettings,
)
from discipline_hr.discipline_hr.doctype.discipline_penalty.discipline_penalty import DisciplinePenalty
from discipline_hr.events.attendance import cascade_cancel_attendance, create_attendance_permissions
from discipline_hr.services.attendance_permission import (
    _context_from_attendance,
    _create_attendance_penalty,
    _create_grace_ledger,
    retry_discipline_penalty,
)
from discipline_hr.tests.fixtures import delete_fiscal_year, ensure_fiscal_year


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
        cls._created_fy_2026 = ensure_fiscal_year(2026)
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
        settings.penalize_manual_attendance_permissions = 0
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
                    "custom_minimum_grace_minutes": 0,
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

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "_created_fy_2026", False):
            delete_fiscal_year(2026)
        super().tearDownClass()

    def test_auto_processed_permission_creates_ledger_and_penalty(self):
        """
        Test valid Attendance Permission -> Employee Grace Ledger -> Discipline Penalty
        """

        permission = create_attendance_permission(self, minutes=90, date="2026-06-15")

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
        employee, attendance = make_employee_with_attendance(
            self.shift_type, "test_attendance_permission@status.st"
        )
        permission = create_attendance_permission(
            self, employee=employee, minutes=90, status="Pending", attendance=attendance
        )
        # Assert — Grace Ledger was never created
        ledger = frappe.db.get_value(
            "Employee Grace Ledger",
            {"attendance_permission": permission.name},
        )
        self.assertIsNone(ledger, "Employee Grace Ledger Created even when ATP status is Pending")

    def test_attendance_permission_with_zero_minutes(self):
        """Test if minutes <= 0  in attendance permission, break the workflow"""
        permission = create_attendance_permission(self, minutes=0, date="2026-06-15")

        # Assert — Grace Ledger was never created
        ledger = frappe.db.get_value(
            "Employee Grace Ledger",
            {"attendance_permission": permission.name},
        )
        self.assertIsNone(ledger, "Employee Grace Ledger Created even when ATP minutes == 0 ")

    def test_ignore_grace_ledger_duplicate(self):
        """Two permissions for the same attendance create only one grace-consumption ledger."""
        settings = cast(DisciplineHRSettings, frappe.get_single("Discipline HR Settings"))
        settings.split_permissions_and_penalties = 0
        settings.save(ignore_permissions=True)

        employee, attendance = make_employee_with_attendance(
            self.shift_type, "_test_duplicate@test.com", date="2026-06-15"
        )

        create_attendance_permission(
            self, employee=employee, minutes=120, date="2026-06-15", attendance=attendance
        )
        create_attendance_permission(
            self, employee=employee, minutes=120, date="2026-06-15", attendance=attendance
        )

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

    def test_consumed_so_far(self):
        """Test create multiple ledgers for same employee will calculate the consumed minutes (0 + 30 + 30)"""
        employee, attendance = make_employee_with_attendance(
            self.shift_type, "test_consumed_so_far@c.com", "2026-04-12"
        )
        attendance2 = make_attendance(employee, self.shift_type, date="2026-04-13")

        _p1 = create_attendance_permission(self, employee, 20, attendance=attendance, date="2026-04-12")
        _p2 = create_attendance_permission(self, employee, 25, attendance=attendance2, date="2026-04-13")

        ledger2 = frappe.get_value(
            "Employee Grace Ledger",
            filters={"attendance_permission": _p2.name},
            fieldname=["remaining_minutes_before_consume", "consumed_minutes"],
            as_dict=True,
        )

        self.assertEqual(
            ledger2.remaining_minutes_before_consume,
            40,
            "Ledger Calculated attendance_permission wrongly, it should be 60 - 20 = 40",
        )
        self.assertEqual(
            ledger2.consumed_minutes,
            25,
            "Ledger used consumed_minutes wrongly, it should be 25",
        )

    def test_create_discipline_penalty_with_zero_minutes(self):
        """Test penalty minutes == 0 should not insert the Additional Salary"""
        penalty = cast(DisciplinePenalty, frappe.new_doc("Discipline Penalty"))
        penalty.violation_date = today()
        penalty.penalty_amount = 0
        penalty.employee = self.employee
        penalty.insert(ignore_permissions=True)

        additional_salary = frappe.get_value(
            "Additional Salary", filters={"custom_discipline_penalty": penalty.name}
        )
        self.assertIsNone(additional_salary, "Additional Salary created even with 0 penalty amount")

    def test_violation_number_increment(self):
        """Test the violation number for the same (employee, start, end, status) is incremented (1, 2)"""
        employee, attendance = make_employee_with_attendance(
            self.shift_type, "test_violation_number@test.co", date="2025-09-25"
        )
        attendance2 = make_attendance(employee, self.shift_type, date="2025-09-26")
        attendance3 = make_attendance(employee, self.shift_type, date="2025-09-27")
        # Create Attendance Permissions -> Auto Processed -> Employee GL -> Discipline Penalty
        _p1 = create_attendance_permission(self, employee, 90, attendance=attendance, date="2025-09-25")
        _p2 = create_attendance_permission(self, employee, 90, attendance=attendance2, date="2025-09-26")
        _p3 = create_attendance_permission(self, employee, 90, attendance=attendance3, date="2025-09-27")

        # Get the violation number for the last GL
        violation_number = frappe.get_value(
            "Discipline Penalty",
            filters={"attendance_permission": _p3.name},
            fieldname="violation_number",
        )

        self.assertEqual(
            violation_number,
            3,
            "Violation Number is not counted correctly.",
        )

    def test_penalty_inherits_policy_from_shift(self):
        """Test penalty policy is fetched from the Shift Type"""
        employee, attendance = make_employee_with_attendance(
            self.shift_type, "test_penalty_inherits_policy@ema.com"
        )
        p = create_attendance_permission(self, minutes=3000, employee=employee, attendance=attendance)
        penalty_policy = frappe.get_value(
            "Discipline Penalty",
            filters={"attendance_permission": p.name},
            fieldname="attendance_penalty_policy",
        )
        self.assertEqual(penalty_policy, self.shift_type.custom_attendance_penalty_policy)

    def test_attendance_retry_happy_path(self):
        """Retry creates an attendance permission and clears custom_error_log."""
        from discipline_hr.events.attendance import retry_attendance_permission

        settings = cast(DisciplineHRSettings, frappe.get_single("Discipline HR Settings"))
        settings.split_permissions_and_penalties = 0
        settings.save(ignore_permissions=True)

        # Arrange
        employee, attendance = make_employee_with_attendance(
            self.shift_type, email="test_att_retry_happy@happy.path", date="2026-10-01"
        )
        attendance.db_set("custom_penalty_minutes", 60, update_modified=False)
        attendance.db_set("custom_error_log", "some old error", update_modified=False)

        # Act
        retry_attendance_permission(attendance.name)

        # Assert: an Attendance Permission exists
        atp = frappe.get_value("Attendance Permissions", {"attendance": attendance.name}, "name")
        self.assertIsNotNone(atp, "Expected an Attendance Permission to be created")

        # Assert: custom_error_log cleared
        attendance.reload()
        self.assertIsNone(attendance.custom_error_log, "Expected custom_error_log to be cleared")

    def test_attendance_retry_duplicate_guard(self):
        """Duplicate retry should not create duplicate permissions."""
        from discipline_hr.events.attendance import retry_attendance_permission

        settings = cast(DisciplineHRSettings, frappe.get_single("Discipline HR Settings"))
        settings.split_permissions_and_penalties = 0
        settings.save(ignore_permissions=True)

        # Arrange
        employee, attendance = make_employee_with_attendance(
            self.shift_type, email="test_att_retry_duplicate@duplicate.path", date="2026-10-02"
        )
        attendance.db_set("custom_penalty_minutes", 60, update_modified=False)

        # Act
        retry_attendance_permission(attendance.name)
        retry_attendance_permission(attendance.name)

        # Assert: only ONE permission exists
        atps = frappe.get_all("Attendance Permissions", filters={"attendance": attendance.name})
        self.assertEqual(len(atps), 1, "Expected exactly one Attendance Permission")


def make_employee_with_attendance(shift_type, email, date="2026-06-25"):
    """Create a test employee and a matching Attendance record.

    Returns:
        Tuple of (employee ID, Attendance doc).
    """
    employee = make_employee(email)
    attendance = make_attendance(employee, shift_type, date)
    return employee, attendance


def make_attendance(employee, shift_type, date="2026-06-25"):
    attendance = frappe.get_doc(
        {
            "doctype": "Attendance",
            "employee": employee,
            "attendance_date": date,
            "status": "Present",
            "shift": shift_type.name,
            "in_time": f"{date} 08:40:00",
            "out_time": f"{date} 16:50:00",
        }
    ).insert(ignore_permissions=True, ignore_if_duplicate=True)
    return attendance


def create_attendance_permission(
    ctx,
    employee=None,
    minutes=30,
    shift_type=None,
    status="Auto Processed",
    date="2026-06-25",
    auto_created=1,
    attendance=None,
):
    if shift_type is None:
        shift_type = ctx.shift_type

    if employee is None:
        employee = ctx.employee

    if attendance is None:
        attendance = ctx.attendance

    permission = frappe.get_doc(
        {
            "doctype": "Attendance Permissions",
            "employee": employee,
            "attendance": attendance.name,
            "shift_type": shift_type.name,
            "date": date,
            "minutes": minutes,
            "status": status,
            "auto_created": auto_created,
        }
    ).insert(ignore_permissions=True)
    return permission


class TestAttendancePermissions(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._created_fy_2026 = ensure_fiscal_year(2026)

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

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "_created_fy_2026", False):
            delete_fiscal_year(2026)
        super().tearDownClass()

    def test_manual_created_attendance_permission_create_gl_without_penalty(self):
        """Manual Created Attendance Permission, should create EGL and not a penalty"""
        settings = cast(DisciplineHRSettings, frappe.get_single("Discipline HR Settings"))
        settings.penalize_manual_attendance_permissions = 0
        settings.save(ignore_permissions=True)

        employee, attendance = make_employee_with_attendance(
            self.shift_type, "_test_atp_manual@email.com", date="2026-07-01"
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
            self.shift_type, "_test_penalize_manual@email.com", date="2026-07-02"
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

    @patch("discipline_hr.services.attendance_permission.frappe.logger")
    def test_gl_succeeds_when_dp_fails(self, mock_logger):
        _, attendance = make_employee_with_attendance(
            self.shift_type, "test_dp_failure@email.com", date="2026-08-05"
        )
        ctx = _context_from_attendance(attendance)

        with patch(
            "discipline_hr.services.attendance_permission._create_attendance_penalty",
            side_effect=Exception("Simulated DP failure"),
        ):
            _create_grace_ledger(ctx)

        # Assert GL exists
        self.assertTrue(frappe.db.exists("Employee Grace Ledger", {"attendance": ctx.attendance}))
        # Assert DP does not exist
        self.assertFalse(frappe.db.exists("Discipline Penalty", {"attendance": ctx.attendance}))

        # Assert the exception raised and logger called with structured JSON
        import json

        expected_payload = json.dumps(
            {
                "event": "discipline_penalty_creation_failed",
                "employee": ctx.employee,
                "attendance": ctx.attendance,
                "permission": ctx.attendance_permission or "",
                "date": ctx.date,
                "minutes": ctx.minutes,
            },
            default=str,
        )
        mock_logger.return_value.exception.assert_called_with(expected_payload)

    def test_duplicate_attendance_one_attendance_permission(self):
        """
        Submit Attendance with penalty, AP created. Cancel Attendance,
        resubmit — assert only ONE AP exists for that attendance.
        """
        settings = cast(DisciplineHRSettings, frappe.get_single("Discipline HR Settings"))
        settings.split_permissions_and_penalties = 0
        settings.save(ignore_permissions=True)

        employee, attendance = make_employee_with_attendance(
            self.shift_type, "unique_test_duplicate_atp@status.st", "2026-06-26"
        )
        create_attendance_permissions(employee, attendance, 200, self.shift_type.name, date="2026-06-26")
        create_attendance_permissions(employee, attendance, 200, self.shift_type.name, date="2026-06-26")

        atp = frappe.get_all("Attendance Permissions", filters={"employee": employee, "date": "2026-06-26"})

        self.assertEqual(len(atp), 1, "ATP duplicated")

    def test_duplicate_discipline_penalty(self):
        """Two consecutive _create_attendance_penalty calls for the same attendance insert only one Discipline Penalty."""
        settings = cast(DisciplineHRSettings, frappe.get_single("Discipline HR Settings"))
        settings.split_permissions_and_penalties = 0
        settings.auto_process_attendance_penalty = 1
        settings.auto_process_attendance_permission = 1
        settings.save(ignore_permissions=True)

        employee, attendance = make_employee_with_attendance(
            self.shift_type, "test_duplicate_dp@status.st", "2026-06-27"
        )
        attendance2 = make_attendance(employee, self.shift_type, date="2026-06-28")
        attendance2.custom_penalty_minutes = 120
        ctx = _context_from_attendance(attendance2)
        ledger = _create_grace_ledger(ctx)

        _create_attendance_penalty(ctx, ledger, settings)
        _create_attendance_penalty(ctx, ledger, settings)

        atp = frappe.get_all("Discipline Penalty", filters={"attendance": attendance2.name})

        self.assertEqual(len(atp), 1, "Discipline Penalty is duplicated")

    def test_discipline_penalty_retry_happy_path(self):
        """Retry creates a discipline penalty clears the stale error_log."""
        # Arrange
        employee, attendance = make_employee_with_attendance(
            self.shift_type, email="test_dp_retry_happy@happy.path", date="2026-11-01"
        )
        settings = cast(DisciplineHRSettings, frappe.get_single("Discipline HR Settings"))
        settings.penalize_manual_attendance_permissions = 1
        settings.save()

        attendance.db_set("custom_penalty_minutes", 90, update_modified=False)
        ctx = _context_from_attendance(attendance)
        ledger = _create_grace_ledger(ctx)
        ledger.db_set("error_log", "some old error", update_modified=False)

        # Act
        retry_discipline_penalty(ledger)

        # Assert: a Discipline Penalty was created
        dp_name = frappe.get_value("Discipline Penalty", {"employee_grace_ledger": ledger.name}, "name")
        self.assertIsNotNone(dp_name, "Expected a Discipline Penalty to be created")

        # Assert: the stale error was cleared, and nothing set a non-None error
        ledger.reload()
        self.assertIsNone(ledger.error_log, "Expected error_log to be cleared after successful retry")

    @patch("discipline_hr.services.attendance_permission._log")
    def test_discipline_penalty_retry_duplicate_guard(self, mock_logger):
        """If a Discipline Penalty already exists, retry logs the duplicate and skips creation."""
        # Arrange
        employee, attendance = make_employee_with_attendance(
            self.shift_type, email="test_dp_retry_duplicate@duplicate.path", date="2026-11-02"
        )
        settings = cast(DisciplineHRSettings, frappe.get_single("Discipline HR Settings"))
        settings.penalize_manual_attendance_permissions = 1
        settings.save()

        attendance.db_set("custom_penalty_minutes", 90, update_modified=False)
        ctx = _context_from_attendance(attendance)
        ledger = _create_grace_ledger(ctx)

        # Act
        retry_discipline_penalty(ledger)
        retry_discipline_penalty(ledger)

        # Assert
        mock_logger.assert_called_with(
            "info",
            "duplicate_discipline_penalty",
            employee=ctx.employee,
            date=ctx.date,
            attendance=ctx.attendance,
        )

    def test_attendance_permission_retry_happy_path(self):
        """Retry creates a grace ledger and clears the stale error_log."""
        # Arrange
        employee, attendance = make_employee_with_attendance(
            self.shift_type, email="test_atp_retry_happy@happy.path", date="2026-12-01"
        )
        permission = create_attendance_permission(self, employee=employee, attendance=attendance, minutes=60)
        permission.db_set("error_log", "some old error", update_modified=False)

        # Act
        permission.retry()

        # Assert: a Grace Ledger exists
        ledger_name = frappe.get_value(
            "Employee Grace Ledger", {"attendance_permission": permission.name}, "name"
        )
        self.assertIsNotNone(ledger_name, "Expected an Employee Grace Ledger to be created")

        # Assert: the stale error was cleared
        permission.reload()
        self.assertIsNone(permission.error_log, "Expected error_log to be cleared after successful retry")

    def test_attendance_permission_retry_duplicate_guard(self):
        """If a Grace Ledger already exists, retry clears the error and skips creation."""
        # Arrange
        employee, attendance = make_employee_with_attendance(
            self.shift_type, email="test_atp_retry_duplicate@duplicate.path", date="2026-12-02"
        )
        permission = create_attendance_permission(self, employee=employee, attendance=attendance, minutes=60)
        # First call creates the ledger
        permission.retry()
        permission.db_set("error_log", "some old error", update_modified=False)

        # Act - Second retry
        permission.retry()

        # Assert: only ONE ledger exists
        ledgers = frappe.get_all("Employee Grace Ledger", filters={"attendance_permission": permission.name})
        self.assertEqual(len(ledgers), 1, "Expected exactly one Grace Ledger to exist")

        # Assert: error_log cleared
        permission.reload()
        self.assertIsNone(permission.error_log, "Expected error_log to be cleared even if duplicate")
