# Copyright (c) 2026, Abdelrahman Elsayed and Contributors
# See license.txt

from unittest import TestCase
from unittest.mock import MagicMock, patch

from discipline_hr.discipline_hr.doctype.absence_penalty_policy.absence_penalty_policy import (
    AbsencePenaltyPolicy,
)
from discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty import AttendancePenalty
from discipline_hr.discipline_hr.doctype.attendance_penalty_policy.attendance_penalty_policy import (
    AttendancePenaltyPolicy,
)


class TestAttendancePenalty(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.attendance_policy = AttendancePenaltyPolicy({"doctype": "Attendance Penalty Policy"})
        cls.attendance_policy.append("penalty_matrix", {"violation_number": 1, "percentage": 0.25})
        cls.attendance_policy.append("penalty_matrix", {"violation_number": 2, "percentage": 0.50})
        cls.attendance_policy.append("penalty_matrix", {"violation_number": 3, "percentage": 1})

        cls.absence_policy = AbsencePenaltyPolicy({"doctype": "Absence Penalty Policy"})
        cls.absence_policy.append("penalty_matrix", {"violation_number": 1, "percentage": 0.25})
        cls.absence_policy.append("penalty_matrix", {"violation_number": 2, "percentage": 0.50})
        cls.absence_policy.append("penalty_matrix", {"violation_number": 3, "percentage": 1})

    def setUp(self):
        self.penalty = AttendancePenalty({"doctype": "Attendance Penalty", "attendance": "Fake Att"})

    def test_fixed_per_hour_penalty(self):
        """Test fixed per hour deduction normal case (30min, rate=60 → 30.0)"""
        # Arrange
        self.penalty.penalty_minutes = 30
        mock_policy = MagicMock()
        mock_policy.rate_per_hour = 60

        # Act
        with patch.object(self.penalty, "_get_attendance_penalty_policy_doc", return_value=mock_policy):
            result = self.penalty._fixed_per_hour_deduction()

        # Assert
        self.assertEqual(result, 30.0, "Fixed per hour should result 30.0")

    def test_fixed_per_hour_zero_minutes(self):
        """Test fixed per hour deduction zero penalty_minutes (30min, rate=0 → 0.0)"""
        # Arrange
        self.penalty.penalty_minutes = 0
        mock_policy = MagicMock()
        mock_policy.rate_per_hour = 100

        # Act
        with patch.object(self.penalty, "_get_attendance_penalty_policy_doc", return_value=mock_policy):
            result = self.penalty._fixed_per_hour_deduction()

        # Assert
        self.assertEqual(result, 0.0, "Fixed per hour should result 30")

    @patch(
        "discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.AttendancePenalty._get_attendance_penalty_policy_doc"
    )
    @patch(
        "discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.AttendancePenalty._get_minute_rate"
    )
    def test_valid_factor_deduction(self, mock_minute_rate, mock_policy):
        """Test normal case 5mins * factor=5 * rate=5 = 125"""
        # Arrange
        self.penalty.penalty_minutes = 5
        mock_policy.return_value.deducted_minutes_factor = 5
        mock_minute_rate.return_value = 5

        # Act
        result = self.penalty._factor_deduction()

        # Assert
        self.assertEqual(result, 125.0, "Factor Deduction 5 * 5 * 5 failed")

    @patch(
        "discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.AttendancePenalty._get_attendance_penalty_policy_doc"
    )
    @patch(
        "discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.AttendancePenalty._get_minute_rate"
    )
    def test_factor_deduction_zero(self, mock_minute_rate, mock_policy):
        "Test minutes factor = 0, should result 0 penalty"
        # Arrange
        self.penalty.penalty_minutes = 100
        mock_minute_rate.return_value = 20
        mock_policy.return_value.deducted_minutes_factor = 0

        # Act
        result = self.penalty._factor_deduction()

        # Assert
        self.assertEqual(result, 0.0, "Factor Deduction  deducted_minutes_factor = 0 * n * n failed")

    @patch(
        "discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.AttendancePenalty._get_employee_daily_rate"
    )
    @patch(
        "discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.AttendancePenalty._get_attendance_penalty_policy_doc"
    )
    def test_attendance_penalty_matrix_overflow(self, mock_policy, mock_daily_rate):
        "Test penalty matrix valid maximum day"
        # Arrange
        self.penalty.violation_number = 4
        mock_policy.return_value = self.attendance_policy
        mock_daily_rate.return_value = 100

        # Act
        result = self.penalty._penalty_matrix_deduction()

        # Assert
        self.assertEqual(result, 100.0, "violation number=4 > Penalty Matrix=3 idx didn't pass")

    @patch(
        "discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.AttendancePenalty._get_employee_daily_rate"
    )
    @patch(
        "discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.AttendancePenalty._get_absence_penalty_policy_doc"
    )
    def test_absence_penalty_matrix_overflow(self, mock_policy, mock_daily_rate):
        "Test absence penalty matrix valid maximum day"
        # Arrange
        self.penalty.violation_number = 4
        mock_policy.return_value = self.absence_policy
        mock_daily_rate.return_value = 100

        # Act
        result = self.penalty._absence_penalty_matrix()

        # Assert
        self.assertEqual(result, 100.0, "violation number=4 > Penalty Matrix=3 idx didn't pass")

    @patch(
        "discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.AttendancePenalty._get_employee_daily_rate"
    )
    @patch(
        "discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.AttendancePenalty._get_attendance_penalty_policy_doc"
    )
    def test_attendance_penalty_matrix_exact_number(self, mock_policy, mock_daily_rate):
        "Test attendance penalty matrix valid exact number 2 -> 0.5 * daily_rate"
        # Arrange
        self.penalty.violation_number = 2
        mock_policy.return_value = self.attendance_policy
        mock_daily_rate.return_value = 100

        # Act
        result = self.penalty._penalty_matrix_deduction()

        # Assert
        self.assertEqual(result, 50.0, "violation number=2 > Penalty Matrix=2 should return 0.5 * 100 -> 50")

    @patch(
        "discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.AttendancePenalty._get_employee_daily_rate"
    )
    @patch(
        "discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.AttendancePenalty._get_absence_penalty_policy_doc"
    )
    def test_absence_penalty_matrix_exact_number(self, mock_policy, mock_daily_rate):
        "Test absence penalty matrix valid exact number 2 -> 0.5 * daily_rate"
        # Arrange
        self.penalty.violation_number = 2
        mock_policy.return_value = self.absence_policy
        mock_daily_rate.return_value = 100

        # Act
        result = self.penalty._absence_penalty_matrix()

        # Assert
        self.assertEqual(result, 50.0, "violation number=2 > Penalty Matrix=2 should return 0.5 * 100 -> 50")

    @patch(
        "discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.AttendancePenalty._get_attendance_penalty_policy_doc"
    )
    def test_penalty_matrix_deduction_empty_matrix(self, mock_policy):
        """Test empty matrix [] should return 0"""
        # Arrange
        self.penalty_matrix = []
        mock_policy.return_value.penalty_matrix = self.penalty_matrix

        # Act
        result = self.penalty._penalty_matrix_deduction()

        # Assert
        self.assertEqual(result, 0.0, "Empty Matrix should return 0 deduction")

    @patch(
        "discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.AttendancePenalty._get_absence_penalty_policy_doc"
    )
    def test_absence_penalty_matrix_empty_matrix(self, mock_policy):
        """Test empty matrix [] should return 0"""
        # Arrange
        self.penalty_matrix = []
        mock_policy.return_value.penalty_matrix = self.penalty_matrix

        # Act
        result = self.penalty._absence_penalty_matrix()

        # Assert
        self.assertEqual(result, 0.0, "Empty Matrix should return 0 deduction")

    @patch(
        "discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.frappe.db.get_single_value"
    )
    @patch("discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.frappe.db.get_value")
    def test_get_employee_daily_rate(self, mock_assignment, mock_single_value):
        """Test Daily rate for monthly 3000 / 30 -> 100"""
        # Arrange
        mock_assignment.return_value = 3000
        mock_single_value.return_value = 30

        # Act
        result = self.penalty._get_employee_daily_rate()

        # Assert
        self.assertEqual(result, 100, "Failed to get employee daily rate 3000 -> 100")

    @patch(
        "discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.frappe.db.get_single_value"
    )
    @patch("discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.frappe.db.get_value")
    def test_get_employee_daily_rate_custom_month_days(self, mock_assignment, mock_single_value):
        """Test Daily rate with custom month_days: 3000 / 26 ≈ 115.38"""
        # Arrange
        mock_assignment.return_value = 3000
        mock_single_value.return_value = 26

        # Act
        result = self.penalty._get_employee_daily_rate()

        # Assert
        self.assertAlmostEqual(result, 3000 / 26, places=2)

    @patch("discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.frappe.db.get_value")
    def test_get_employee_daily_rate_zero_assignment(self, mock_assignment):
        """Test Daily rate for Missing Salary Structure assignment or 0 -> 0"""
        # Arrange
        mock_assignment.return_value = 0

        # Act
        result = self.penalty._get_employee_daily_rate()

        # Assert
        self.assertEqual(result, 0, "Failed to get employee daily rate 0 -> 0")

    @patch("discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.frappe.db.get_value")
    def test_get_employee_daily_rate_none_assignment(self, mock_assignment):
        """Test Daily rate for Missing Salary Structure assignment or 0 -> 0"""
        # Arrange
        mock_assignment.return_value = None

        # Act
        result = self.penalty._get_employee_daily_rate()

        # Assert
        self.assertEqual(result, 0, "Failed to get employee daily rate 0 -> 0")

    @patch("discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.frappe.get_value")
    def test_get_penalty_amount_present_dispatches_attendance_handler(self, mock_get_value):
        """Test that penalty_status=Present dispatches to attendance handler"""
        # Arrange
        self.penalty.penalty_status = "Present"
        self.penalty.attendance_penalty_policy = "ATP-0001"
        mock_get_value.return_value = "Fixed Per Hour"

        # Act
        with patch.object(self.penalty, "_fixed_per_hour_deduction", return_value=50.0) as mock_handler:
            result = self.penalty.get_penalty_amount()

        # Assert
        mock_handler.assert_called_once()
        self.assertEqual(result, 50.0)

    @patch("discipline_hr.discipline_hr.doctype.attendance_penalty.attendance_penalty.frappe.get_value")
    def test_get_penalty_amount_absent_dispatches_absence_handler(self, mock_get_value):
        """Test that penalty_status=Absent dispatches to absence handler"""
        # Arrange
        self.penalty.penalty_status = "Absent"
        self.penalty.absence_penalty_policy = "ABP-0001"
        mock_get_value.return_value = "Penalty Matrix"

        # Act
        with patch.object(self.penalty, "_absence_penalty_matrix", return_value=100.0) as mock_handler:
            result = self.penalty.get_penalty_amount()

        # Assert
        mock_handler.assert_called_once()
        self.assertEqual(result, 100.0)

    def test_get_penalty_amount_missing_policy_returns_zero(self):
        """Test that missing policy link returns 0.0"""
        # Arrange
        self.penalty.penalty_status = "Present"
        self.penalty.attendance_penalty_policy = None

        # Act
        result = self.penalty.get_penalty_amount()

        # Assert
        self.assertEqual(result, 0.0)
