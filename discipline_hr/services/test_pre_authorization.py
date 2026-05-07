# Copyright (c) 2026, Abdelrahman Elsayed and Contributors
# See license.txt
from __future__ import annotations

from typing import cast

import frappe
from frappe.tests.utils import FrappeTestCase

from discipline_hr.discipline_hr.doctype.discipline_hr_settings.discipline_hr_settings import (
    DisciplineHRSettings,
)
from discipline_hr.events.attendance import apply_pre_authorization_and_penalty
from discipline_hr.events.pre_authorization import expire_stale_pre_authorizations
from discipline_hr.services.pre_authorization import (
    _apply_preauth_and_compute_remainder,
    _consume_pre_authorization,
    _find_active_pre_authorization,
)
from discipline_hr.tests.fixtures import delete_fiscal_year, ensure_fiscal_year, make_employee

SHIFT_NAME = "_Test PreAuth Shift"
MAIN_POLICY_RATE = 60
SURPLUS_POLICY_RATE = 90
SALARY_COMPONENT = "_Test Discipline Deduction"


def _ensure_salary_component() -> str:
    if not frappe.db.exists("Salary Component", SALARY_COMPONENT):
        frappe.get_doc(
            {
                "doctype": "Salary Component",
                "salary_component": SALARY_COMPONENT,
                "salary_component_abbr": "tdd",
                "type": "Deduction",
            }
        ).insert(ignore_permissions=True)
    return SALARY_COMPONENT


def _ensure_policy(rate_per_hour: int) -> str:
    """Insert a Fixed Per Hour policy. Doctype autonames as ``Fixed Per Hour-<rate>``."""
    name = f"Fixed Per Hour-{rate_per_hour}"
    if frappe.db.exists("Attendance Penalty Policy", name):
        return name
    frappe.get_doc(
        {
            "doctype": "Attendance Penalty Policy",
            "penalty_type": "Fixed Per Hour",
            "rate_per_hour": rate_per_hour,
        }
    ).insert(ignore_permissions=True)
    return name


def _ensure_shift(salary_component: str, main_policy: str) -> str:
    if frappe.db.exists("Shift Type", SHIFT_NAME):
        return SHIFT_NAME
    frappe.get_doc(
        {
            "doctype": "Shift Type",
            "name": SHIFT_NAME,
            "start_time": "08:00:00",
            "end_time": "17:00:00",
            "late_entry_grace_period": 5,
            "early_exit_grace_period": 5,
            "custom_period_start_date": "2026-01-01",
            "custom_period_end_date": "2026-12-31",
            "custom_total_allowed_grace_minutes": 60,
            "custom_minimum_grace_minutes": 0,
            "custom_salary_component": salary_component,
            "custom_attendance_penalty_policy": main_policy,
            "enable_auto_attendance": 1,
        }
    ).insert(ignore_permissions=True)
    return SHIFT_NAME


def _make_attendance(employee: str, shift: str, date: str, late: int = 0, early: int = 0):
    """Insert (not submit) an Attendance with pre-computed late/early/penalty fields."""
    doc = frappe.get_doc(
        {
            "doctype": "Attendance",
            "employee": employee,
            "attendance_date": date,
            "status": "Present",
            "shift": shift,
            "in_time": f"{date} 08:00:00",
            "out_time": f"{date} 17:00:00",
        }
    ).insert(ignore_permissions=True, ignore_if_duplicate=True)
    doc.db_set("custom_late_after_grace_minutes", late, update_modified=False)
    doc.db_set("custom_early_after_grace_minutes", early, update_modified=False)
    doc.db_set("custom_penalty_minutes", late + early, update_modified=False)
    doc.reload()
    return doc


def _make_preauth(
    employee: str, date: str, kind: str, minutes: int, status: str = "Approved", shift: str = SHIFT_NAME
):
    """Insert a pre-auth bypassing the auto-approve hook so we control status."""
    doc = frappe.get_doc(
        {
            "doctype": "Attendance Pre-Authorization",
            "employee": employee,
            "date": date,
            "kind": kind,
            "minutes": minutes,
            "shift_type": shift,
            "reason": "test",
        }
    ).insert(ignore_permissions=True)
    if doc.status != status:
        frappe.db.set_value("Attendance Pre-Authorization", doc.name, "status", status)
    doc.reload()
    return doc


class TestPreAuthorizationFlow(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._created_fy_name = ensure_fiscal_year(2026)
        cls.salary_component = _ensure_salary_component()
        cls.main_policy = _ensure_policy(MAIN_POLICY_RATE)
        cls.surplus_policy = _ensure_policy(SURPLUS_POLICY_RATE)
        cls.shift = _ensure_shift(cls.salary_component, cls.main_policy)

        settings = cast(DisciplineHRSettings, frappe.get_single("Discipline HR Settings"))
        settings.attendance_penalty_policy = cls.main_policy
        settings.pre_authorization_surplus_policy = cls.surplus_policy
        settings.salary_component = cls.salary_component
        settings.auto_process_attendance_penalty = 1
        settings.auto_approve_pre_authorization = 0
        settings.flags.ignore_validate = True
        settings.flags.ignore_links = True
        settings.save(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        delete_fiscal_year(getattr(cls, "_created_fy_name", None))
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        # Each test isolates by employee email, so no global cleanup needed.

    def test_grace_ledger_when_no_preauth(self):
        emp = make_employee("preauth_no_match@test.com")
        att = _make_attendance(emp, self.shift, "2026-04-01", late=120)

        apply_pre_authorization_and_penalty(att)

        ledger = frappe.db.exists("Employee Grace Ledger", {"attendance": att.name})
        self.assertIsNotNone(ledger, "Grace ledger should be created when no pre-auth matches")

    def test_approved_late_preauth_covers_all_minutes(self):
        emp = make_employee("preauth_full_cover@test.com")
        date = "2026-04-02"
        preauth = _make_preauth(emp, date, "Late", minutes=20)
        att = _make_attendance(emp, self.shift, date, late=15)

        apply_pre_authorization_and_penalty(att)

        preauth.reload()
        self.assertEqual(preauth.status, "Consumed")
        self.assertEqual(preauth.attendance, att.name)
        self.assertFalse(frappe.db.exists("Discipline Penalty", {"attendance": att.name}))
        self.assertFalse(frappe.db.exists("Employee Grace Ledger", {"attendance": att.name}))

    def test_approved_late_preauth_partial_creates_surplus_penalty(self):
        emp = make_employee("preauth_partial@test.com")
        date = "2026-04-03"
        preauth = _make_preauth(emp, date, "Late", minutes=20)
        att = _make_attendance(emp, self.shift, date, late=60)

        apply_pre_authorization_and_penalty(att)

        preauth.reload()
        self.assertEqual(preauth.status, "Consumed")

        penalty = frappe.db.get_value(
            "Discipline Penalty",
            {"attendance": att.name},
            ["penalty_minutes", "attendance_penalty_policy", "attendance_pre_authorization"],
            as_dict=True,
        )
        self.assertIsNotNone(penalty)
        self.assertEqual(penalty.penalty_minutes, 40)
        self.assertEqual(penalty.attendance_penalty_policy, self.surplus_policy)
        self.assertEqual(penalty.attendance_pre_authorization, preauth.name)
        # Surplus path must not consume the grace pool. A penalty-marker ledger
        # row (with discipline_penalty set) is allowed and intentionally excluded
        # from pool sums; a consumption row (discipline_penalty unset) is not.
        consumption_row = frappe.db.exists(
            "Employee Grace Ledger",
            {"attendance": att.name, "discipline_penalty": ("is", "not set")},
        )
        self.assertFalse(consumption_row)

    def test_pending_preauth_falls_through_to_grace_ledger(self):
        emp = make_employee("preauth_pending@test.com")
        date = "2026-04-04"
        _make_preauth(emp, date, "Late", minutes=20, status="Pending Approval")
        att = _make_attendance(emp, self.shift, date, late=15)

        apply_pre_authorization_and_penalty(att)

        self.assertTrue(frappe.db.exists("Employee Grace Ledger", {"attendance": att.name}))

    def test_late_preauth_does_not_match_early_only_event(self):
        emp = make_employee("preauth_kind_mismatch@test.com")
        date = "2026-04-05"
        preauth = _make_preauth(emp, date, "Late", minutes=30)
        att = _make_attendance(emp, self.shift, date, early=20)

        apply_pre_authorization_and_penalty(att)

        preauth.reload()
        self.assertEqual(preauth.status, "Approved")
        self.assertTrue(frappe.db.exists("Employee Grace Ledger", {"attendance": att.name}))

    def test_kind_both_covers_combined_late_and_early(self):
        emp = make_employee("preauth_both@test.com")
        date = "2026-04-06"
        preauth = _make_preauth(emp, date, "Both", minutes=30)
        att = _make_attendance(emp, self.shift, date, late=20, early=20)

        apply_pre_authorization_and_penalty(att)

        preauth.reload()
        self.assertEqual(preauth.status, "Consumed")
        penalty = frappe.db.get_value(
            "Discipline Penalty",
            {"attendance": att.name},
            ["penalty_minutes"],
            as_dict=True,
        )
        self.assertIsNotNone(penalty)
        self.assertEqual(penalty.penalty_minutes, 10)

    def test_atomic_consumption_prevents_double_spend(self):
        emp = make_employee("preauth_race@test.com")
        date = "2026-04-07"
        preauth = _make_preauth(emp, date, "Late", minutes=30)

        # First caller wins, second caller sees status != Approved.
        first = _consume_pre_authorization(preauth.name, "ATT-RACE-1")
        second = _consume_pre_authorization(preauth.name, "ATT-RACE-2")

        self.assertTrue(first)
        self.assertFalse(second)
        preauth.reload()
        self.assertEqual(preauth.status, "Consumed")
        self.assertEqual(preauth.attendance, "ATT-RACE-1")

    def test_auto_approve_pre_authorization_setting(self):
        settings = cast(DisciplineHRSettings, frappe.get_single("Discipline HR Settings"))
        settings.auto_approve_pre_authorization = 1
        settings.save(ignore_permissions=True)
        try:
            emp = make_employee("preauth_auto@test.com")
            doc = frappe.get_doc(
                {
                    "doctype": "Attendance Pre-Authorization",
                    "employee": emp,
                    "date": "2026-04-08",
                    "kind": "Late",
                    "minutes": 15,
                    "shift_type": self.shift,
                    "reason": "auto-test",
                }
            ).insert(ignore_permissions=True)
            self.assertEqual(doc.status, "Approved")
        finally:
            settings.auto_approve_pre_authorization = 0
            settings.save(ignore_permissions=True)

    def test_overlapping_approved_preauth_rejected(self):
        emp = make_employee("preauth_overlap@test.com")
        date = "2026-04-09"
        _make_preauth(emp, date, "Late", minutes=20)
        with self.assertRaises(frappe.exceptions.ValidationError):
            _make_preauth(emp, date, "Late", minutes=30)

    def test_invalid_status_transition_rejected(self):
        emp = make_employee("preauth_transition@test.com")
        preauth = _make_preauth(emp, "2026-04-10", "Late", minutes=20)
        # Approved → Pending Approval is not allowed.
        preauth.status = "Pending Approval"
        with self.assertRaises(frappe.exceptions.ValidationError):
            preauth.save(ignore_permissions=True)

    def test_expire_stale_pre_authorizations(self):
        emp = make_employee("preauth_expire@test.com")
        old = _make_preauth(emp, "2026-01-15", "Late", minutes=20)
        recent = _make_preauth(emp, frappe.utils.today(), "Late", minutes=20)

        expire_stale_pre_authorizations()

        old.reload()
        recent.reload()
        self.assertEqual(old.status, "Expired")
        self.assertEqual(recent.status, "Approved")

    def test_apply_preauth_helper_returns_consumed_names(self):
        emp = make_employee("preauth_helper@test.com")
        date = "2026-04-11"
        preauth = _make_preauth(emp, date, "Late", minutes=10)
        att = _make_attendance(emp, self.shift, date, late=25)

        surplus_late, surplus_early, consumed = _apply_preauth_and_compute_remainder(att, 25, 0)

        self.assertEqual(surplus_late, 15)
        self.assertEqual(surplus_early, 0)
        self.assertEqual(consumed, [preauth.name])

    def test_find_active_pre_authorization(self):
        emp = make_employee("preauth_find@test.com")
        date = "2026-04-12"
        preauth = _make_preauth(emp, date, "Late", minutes=10)

        self.assertEqual(_find_active_pre_authorization(emp, date, "Late"), preauth.name)
        self.assertIsNone(_find_active_pre_authorization(emp, date, "Early"))
