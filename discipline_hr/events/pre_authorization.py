"""Scheduler entry points for the Attendance Pre-Authorization model."""

from __future__ import annotations

import frappe
from frappe.utils import add_days, getdate, today

from discipline_hr.services.utils import _log

DEFAULT_EXPIRY_DAYS = 7


def _get_expiry_days() -> int:
    value = frappe.db.get_single_value("Discipline HR Settings", "pre_authorization_expiry_days")
    try:
        days = int(value) if value else 0
    except (TypeError, ValueError):
        days = 0
    return days if days > 0 else DEFAULT_EXPIRY_DAYS


def expire_stale_pre_authorizations() -> None:
    """Mark old unconsumed pre-authorizations as Expired.

    Runs daily. Any Draft / Pending Approval / Approved record whose date is
    older than ``today - pre_authorization_expiry_days`` (from Discipline HR
    Settings, falling back to ``DEFAULT_EXPIRY_DAYS``) is expired so it can no
    longer be consumed. The expiry uses ``db.sql`` to bypass the
    status-transition validator (which only allows specific manual transitions).
    """
    cutoff = add_days(getdate(today()), -_get_expiry_days())
    frappe.db.sql(
        """
        UPDATE `tabAttendance Pre-Authorization`
        SET status = 'Expired', modified = NOW()
        WHERE status IN ('Draft', 'Pending Approval', 'Approved')
          AND date < %(cutoff)s
        """,
        {"cutoff": cutoff},
    )
    rows = frappe.db._cursor.rowcount
    if rows:
        _log("info", "pre_authorizations_expired", cutoff=str(cutoff), count=rows)
    return rows
