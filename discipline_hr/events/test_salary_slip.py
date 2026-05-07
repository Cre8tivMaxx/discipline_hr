# Copyright (c) 2026, Abdelrahman Elsayed and Contributors
# See license.txt
from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from discipline_hr.events.salary_slip import (
    guard_errored_attendances,
    guard_errored_discipline_penalties,
    guard_errored_grace_ledgers,
)

MODULE = "discipline_hr.events.salary_slip"


def _make_salary_slip(employee: str = "EMP-0001") -> SimpleNamespace:
    """Minimal Salary Slip stand-in exposing only the attributes the guards read."""
    return SimpleNamespace(
        doctype="Salary Slip",
        employee=employee,
        start_date="2026-04-01",
        end_date="2026-04-30",
    )


class TestGuardErroredDisciplinePenalties(TestCase):
    @patch(f"{MODULE}.frappe.msgprint")
    @patch(f"{MODULE}.frappe.get_all")
    def test_validate_msgprints_when_errored_records_exist(self, mock_get_all, mock_msgprint):
        mock_get_all.return_value = ["DP-0001"]
        slip = _make_salary_slip(employee="EMP-0001")

        guard_errored_discipline_penalties(slip, method="validate")

        mock_get_all.assert_called_once_with(
            "Discipline Penalty",
            filters={
                "employee": "EMP-0001",
                "error_log": ["is", "set"],
                "violation_date": ["between", (slip.start_date, slip.end_date)],
            },
            pluck="name",
        )
        mock_msgprint.assert_called_once()
        self.assertIn("DP-0001", mock_msgprint.call_args[0][0])

    @patch(f"{MODULE}.frappe.msgprint")
    @patch(f"{MODULE}.frappe.get_all")
    def test_validate_is_noop_when_no_errored_records(self, mock_get_all, mock_msgprint):
        mock_get_all.return_value = []
        slip = _make_salary_slip(employee="EMP-0001")

        result = guard_errored_discipline_penalties(slip, method="validate")

        self.assertIsNone(result)
        mock_msgprint.assert_not_called()

    @patch(f"{MODULE}.frappe.get_all")
    def test_before_submit_throws_when_errored_records_exist(self, mock_get_all):
        mock_get_all.return_value = ["DP-0001"]
        slip = _make_salary_slip()

        with self.assertRaises(frappe.exceptions.ValidationError):
            guard_errored_discipline_penalties(slip, method="before_submit")


class TestGuardErroredAttendances(TestCase):
    @patch(f"{MODULE}.frappe.msgprint")
    @patch(f"{MODULE}.frappe.get_all")
    def test_validate_msgprints_when_errored_records_exist(self, mock_get_all, mock_msgprint):
        mock_get_all.return_value = ["ATT-0001"]
        slip = _make_salary_slip(employee="EMP-0004")

        guard_errored_attendances(slip, method="validate")

        mock_get_all.assert_called_once_with(
            "Attendance",
            filters={
                "employee": "EMP-0004",
                "custom_error_log": ["is", "set"],
                "attendance_date": ["between", (slip.start_date, slip.end_date)],
            },
            pluck="name",
        )
        mock_msgprint.assert_called_once()
        self.assertIn("ATT-0001", mock_msgprint.call_args[0][0])

    @patch(f"{MODULE}.frappe.msgprint")
    @patch(f"{MODULE}.frappe.get_all")
    def test_validate_is_noop_when_no_errored_records(self, mock_get_all, mock_msgprint):
        mock_get_all.return_value = []
        slip = _make_salary_slip(employee="EMP-0004")

        result = guard_errored_attendances(slip, method="validate")

        self.assertIsNone(result)
        mock_msgprint.assert_not_called()

    @patch(f"{MODULE}.frappe.get_all")
    def test_before_submit_throws_when_errored_records_exist(self, mock_get_all):
        mock_get_all.return_value = ["ATT-0001"]
        slip = _make_salary_slip()

        with self.assertRaises(frappe.exceptions.ValidationError):
            guard_errored_attendances(slip, method="before_submit")


class TestGuardErroredGraceLedgers(TestCase):
    @patch(f"{MODULE}.frappe.msgprint")
    @patch(f"{MODULE}.frappe.get_all")
    def test_validate_msgprints_when_errored_records_exist(self, mock_get_all, mock_msgprint):
        mock_get_all.return_value = ["EGL-0002"]
        slip = _make_salary_slip(employee="EMP-0002")

        guard_errored_grace_ledgers(slip, method="validate")

        mock_get_all.assert_called_once_with(
            "Employee Grace Ledger",
            filters={
                "employee": "EMP-0002",
                "error_log": ["is", "set"],
                "date": ["between", (slip.start_date, slip.end_date)],
            },
            pluck="name",
        )
        mock_msgprint.assert_called_once()
        self.assertIn("EGL-0002", mock_msgprint.call_args[0][0])

    @patch(f"{MODULE}.frappe.msgprint")
    @patch(f"{MODULE}.frappe.get_all")
    def test_validate_is_noop_when_no_errored_records(self, mock_get_all, mock_msgprint):
        mock_get_all.return_value = []
        slip = _make_salary_slip(employee="EMP-0002")

        result = guard_errored_grace_ledgers(slip, method="validate")

        self.assertIsNone(result)
        mock_msgprint.assert_not_called()

    @patch(f"{MODULE}.frappe.get_all")
    def test_before_submit_throws_when_errored_records_exist(self, mock_get_all):
        mock_get_all.return_value = ["EGL-0001"]
        slip = _make_salary_slip()

        with self.assertRaises(frappe.exceptions.ValidationError):
            guard_errored_grace_ledgers(slip, method="before_submit")
