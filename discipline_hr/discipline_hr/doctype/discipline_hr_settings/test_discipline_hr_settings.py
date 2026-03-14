# Copyright (c) 2026, Abdelrahman Elsayed and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestDisciplineHRSettings(FrappeTestCase):
    def setUp(self):
        self.settings = frappe.get_single("Discipline HR Settings")
        self.original_pending = self.settings.default_pending_notification
        self.original_penalty = self.settings.default_penalty_notification

    def tearDown(self):
        self.settings.reload()
        self.settings.default_pending_notification = self.original_pending
        self.settings.default_penalty_notification = self.original_penalty
        self.settings.flags.ignore_validate = True
        self.settings.flags.ignore_links = True
        self.settings.save(ignore_permissions=True)

    @patch("frappe.db.set_value")
    def test_linking_notification_enables_it(self, mock_set_value):
        self.settings.default_pending_notification = None
        self.settings.flags.ignore_validate = True
        self.settings.flags.ignore_links = True
        self.settings.save(ignore_permissions=True)
        mock_set_value.reset_mock()

        self.settings.reload()
        self.settings.default_pending_notification = "Test Notification"
        self.settings.flags.ignore_validate = True
        self.settings.flags.ignore_links = True
        self.settings.save(ignore_permissions=True)

        mock_set_value.assert_any_call("Notification", "Test Notification", "enabled", 1)

    @patch("frappe.db.set_value")
    def test_unlinking_notification_disables_it(self, mock_set_value):
        self.settings.default_penalty_notification = "Test Notification"
        self.settings.flags.ignore_validate = True
        self.settings.flags.ignore_links = True
        self.settings.save(ignore_permissions=True)
        mock_set_value.reset_mock()

        self.settings.reload()
        self.settings.default_penalty_notification = None
        self.settings.flags.ignore_validate = True
        self.settings.flags.ignore_links = True
        self.settings.save(ignore_permissions=True)

        mock_set_value.assert_any_call("Notification", "Test Notification", "enabled", 0)

    @patch("frappe.db.set_value")
    def test_changing_notification_disables_old_enables_new(self, mock_set_value):
        self.settings.default_pending_notification = "Old Notification"
        self.settings.flags.ignore_validate = True
        self.settings.flags.ignore_links = True
        self.settings.save(ignore_permissions=True)
        mock_set_value.reset_mock()

        self.settings.reload()
        self.settings.default_pending_notification = "New Notification"
        self.settings.flags.ignore_validate = True
        self.settings.flags.ignore_links = True
        self.settings.save(ignore_permissions=True)

        mock_set_value.assert_any_call("Notification", "Old Notification", "enabled", 0)
        mock_set_value.assert_any_call("Notification", "New Notification", "enabled", 1)

    @patch("frappe.db.set_value")
    def test_no_change_does_not_toggle(self, mock_set_value):
        self.settings.default_pending_notification = "Same Notification"
        self.settings.flags.ignore_validate = True
        self.settings.flags.ignore_links = True
        self.settings.save(ignore_permissions=True)
        mock_set_value.reset_mock()

        self.settings.reload()
        self.settings.flags.ignore_validate = True
        self.settings.flags.ignore_links = True
        self.settings.save(ignore_permissions=True)

        for call in mock_set_value.call_args_list:
            self.assertNotEqual(call[0][0], "Notification")
