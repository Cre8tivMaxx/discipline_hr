from unittest import TestCase

import frappe
from frappe.utils import getdate

from discipline_hr.services.shift_type import _calculate_end_date


class TestCalculateEndDate(TestCase):
    def test_wrong_interval(self):
        """Test writing unsupported interval not in [week, month, year]"""
        # Arrange
        interval, n_interval, start_date = "Day", 12, getdate("2025-01-01")

        # Act
        with self.assertRaises(frappe.ValidationError) as context:
            _calculate_end_date(interval, n_interval, start_date)

        # Assert
        self.assertIn("Invalid interval", str(context.exception))

    def test_valid_week(self):
        """Test valid week 2026-03-10 + 2 weeks-> 2026-03-24"""
        # Arrange
        interval, n_interval, start_date = "Week", 2, getdate("2026-03-10")
        expected_output = getdate("2026-03-24")

        # Act
        end_date = _calculate_end_date(interval, n_interval, start_date)
        end_date = getdate(end_date)

        # Assert
        self.assertEqual(expected_output, end_date, "End Date for week interval have a problem")

    def test_month(self):
        """Test adding less than 30 days to be a month."""
        # Arrange
        interval, n_interval, start_date = "Month", 1, getdate("2026-01-31")
        expected_output = getdate("2026-02-28")

        # Act
        end_date = _calculate_end_date(interval, n_interval, start_date)
        end_date = getdate(end_date)

        # Assert
        self.assertEqual(
            expected_output,
            end_date,
            "End Date for Month interval have a problem | date: 2026-01-31 | Expected 2026-02-28",
        )
