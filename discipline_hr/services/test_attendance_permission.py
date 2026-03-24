# Copyright (c) 2026, Abdelrahman Elsayed and Contributors
# See license.txt

from unittest import TestCase
from unittest.mock import MagicMock, call, patch

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
        # Attendance Penalty
        self.assertEqual(
            delete_calls[1], call("Attendance Penalty", "PEN-001", force=True, ignore_permissions=True)
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
            call("Attendance Penalty", "PEN-001", force=True, ignore_permissions=True),
            mock_frappe.delete_doc.call_args_list,
        )
        self.assertIn(
            call("Attendance Penalty", "PEN-002", force=True, ignore_permissions=True),
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
