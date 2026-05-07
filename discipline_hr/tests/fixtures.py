# Copyright (c) 2026, Abdelrahman Elsayed and Contributors
# See license.txt

import atexit

import erpnext
import frappe

_overlap_patch_installed = False


def prepare_test_environment() -> None:
    """``before_tests`` hook: stop ERPNext's calendar-year Fiscal Year bootstrap from
    colliding with the site's existing non-calendar Fiscal Year(s).

    ``erpnext.tests.utils`` runs ``BootStrapTestData()`` at module-import time
    (the import is triggered indirectly by Frappe's test-record preloader walking
    DocType link graphs). It tries to insert one Jan-Dec Fiscal Year per year
    from 2012 through ``now+25``. Any pre-existing non-calendar FY on the site
    (e.g. ``2025-2026`` running ``Jul 1 - Jun 30``) makes those inserts fail
    with ``frappe.NameError`` and aborts test discovery.

    We can't disable the offending FY because ``FiscalYear.validate_overlap``
    does not filter on ``disabled`` — it inspects every row. Instead, we
    monkey-patch ``validate_overlap`` to skip overlap checks for FYs whose name
    starts with ``_Test``. The patch is installed exactly once and is reverted on
    process exit so the live fiscal calendar's integrity is preserved outside of
    the test process.
    """
    global _overlap_patch_installed
    if _overlap_patch_installed:
        return

    _stub_erpnext_test_bootstrap()
    _disable_test_record_preloader()

    from erpnext.accounts.doctype.fiscal_year.fiscal_year import FiscalYear

    original_validate_overlap = FiscalYear.validate_overlap

    def patched_validate_overlap(self):  # type: ignore[no-untyped-def]
        if (self.name or "").startswith("_Test"):
            return
        return original_validate_overlap(self)

    FiscalYear.validate_overlap = patched_validate_overlap
    _overlap_patch_installed = True

    def _restore() -> None:
        FiscalYear.validate_overlap = original_validate_overlap

    atexit.register(_restore)


def _stub_erpnext_test_bootstrap() -> None:
    """Pre-register a stub ``erpnext.tests.utils`` module to suppress its
    import-time ``BootStrapTestData()`` call.

    ``compat_preload_test_records_upfront`` walks DocType link graphs and
    imports each dependency's ``test_<doctype>.py``; many of those modules do
    ``from erpnext.tests.utils import ERPNextTestSuite``, which executes
    ``BootStrapTestData()`` at module-load time. That bootstrap creates company,
    fiscal year, and country fixture data that conflicts with this site's
    pre-existing setup (custom FY range, missing HRMS regional doctypes, etc.).

    We never use ``ERPNextTestSuite`` ourselves, so a stub class with the same
    name is enough to satisfy the import. Must run before any other code touches
    ``erpnext.tests.utils``."""
    import sys
    import types

    if "erpnext.tests.utils" in sys.modules:
        return

    import contextlib
    import unittest

    stub = types.ModuleType("erpnext.tests.utils")

    class ERPNextTestSuite(unittest.TestCase):
        """Stub of ``erpnext.tests.utils.ERPNextTestSuite``. Provides just the
        attributes other erpnext test modules touch at import time
        (``change_settings``, ``set_user``, ``registerAs``). The real class
        runs heavy bootstrap fixtures at module load — we replace it because
        nothing in our test suite actually needs its behavior."""

        @classmethod
        @contextlib.contextmanager
        def change_settings(cls, *args, **kwargs):  # type: ignore[no-untyped-def]
            yield

        @classmethod
        @contextlib.contextmanager
        def set_user(cls, *args, **kwargs):  # type: ignore[no-untyped-def]
            yield

        @classmethod
        def registerAs(cls, _as):  # type: ignore[no-untyped-def]
            def decorator(fn):
                setattr(cls, fn.__name__, _as(fn))
                return fn

            return decorator

    stub.ERPNextTestSuite = ERPNextTestSuite  # type: ignore[attr-defined]
    sys.modules["erpnext.tests.utils"] = stub

    # HRMS has its own equivalent ``BootStrapTestData`` in ``hrms.tests.utils``
    # that fails on this site (its leave-block-list seeds reference users that
    # don't exist). Stub it for the same reason.
    hrms_stub = types.ModuleType("hrms.tests.utils")

    class HRMSTestSuite(ERPNextTestSuite):
        pass

    hrms_stub.HRMSTestSuite = HRMSTestSuite  # type: ignore[attr-defined]
    sys.modules["hrms.tests.utils"] = hrms_stub


def _disable_test_record_preloader() -> None:
    """Neutralize Frappe's deprecated ``compat_preload_test_records_upfront``.

    On legacy ``FrappeTestCase`` runs, Frappe walks every link from every
    DocType referenced by our tests and tries to load fixture JSON for each.
    The walk surfaces DocTypes left over from ERPNext modules that are no
    longer installed (e.g. ``Payment Gateway``) and aborts the test run.

    Our test classes seed all the data they need via fixture helpers, so the
    legacy preloader provides no value. Patch it to a no-op."""
    from frappe import deprecation_dumpster

    deprecation_dumpster.compat_preload_test_records_upfront = lambda *_args, **_kwargs: None


def make_employee(user: str, company: str | None = None, **kwargs) -> str:
    """Local employee factory that does NOT import from ``erpnext.tests.utils``.

    Importing erpnext's ``test_employee.make_employee`` transitively loads
    ``erpnext.tests.utils``, which executes ``BootStrapTestData()`` at module
    import time. Keeping the factory local avoids re-triggering that bootstrap
    inside our own test classes.
    """
    if not frappe.db.exists("User", user):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": user,
                "first_name": user,
                "send_welcome_email": 0,
                "roles": [{"doctype": "Has Role", "role": "Employee"}],
            }
        ).insert(ignore_permissions=True)

    existing = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if existing:
        emp = frappe.get_doc("Employee", existing)
        emp.update(kwargs)
        emp.status = "Active"
        emp.save(ignore_permissions=True)
        return emp.name

    department = frappe.db.get_value("Department", {}, "name")
    emp = frappe.get_doc(
        {
            "doctype": "Employee",
            "naming_series": "EMP-",
            "first_name": user,
            "company": company or erpnext.get_default_company(),
            "user_id": user,
            "date_of_birth": "1990-05-08",
            "date_of_joining": "2013-01-01",
            "department": department,
            "gender": "Female",
            "company_email": user,
            "prefered_contact_email": "Company Email",
            "prefered_email": user,
            "status": "Active",
            "employment_type": "Intern",
        }
    )
    if kwargs:
        emp.update(kwargs)
    emp.insert(ignore_permissions=True)
    return emp.name


# --- Legacy API kept for backward compatibility with existing tests ---
def ensure_fiscal_year(year: int) -> None:
    """No-op shim. The ``before_tests`` hook (``prepare_test_environment``)
    now handles FY conflicts globally, so individual tests no longer need to
    create their own Fiscal Year records."""
    return None


def delete_fiscal_year(name: str | None) -> None:
    """No-op shim paired with :func:`ensure_fiscal_year`."""
    return None
