from frappe.utils import cint


def get_grace_minutes(shift_doc):
    """Return the late-entry and early-exit grace minutes from a Shift Type.

    Args:
        shift_doc: A ``Shift Type`` document.

    Returns:
        Tuple of ``(late_grace, early_grace)`` in minutes.
    """
    late_grace = shift_doc.late_entry_grace_period or 0
    early_grace = shift_doc.early_exit_grace_period or 0
    return late_grace, early_grace


def calculate_consumed_grace_minutes(late_entry_minutes, early_exit_minutes, shift_doc) -> int:
    """Calculate how many grace minutes are consumed by a single attendance event.

    Each direction (late/early) is capped at its own grace limit so that excess
    minutes beyond the limit are not counted as consumed grace.

    Args:
        late_entry_minutes: Raw late-entry minutes for this attendance.
        early_exit_minutes: Raw early-exit minutes for this attendance.
        shift_doc: A ``Shift Type`` document providing grace limits.

    Returns:
        Total consumed grace minutes (int).
    """
    late_grace, early_grace = get_grace_minutes(shift_doc)
    late_consumed = min(cint(late_entry_minutes), late_grace)
    early_consumed = min(cint(early_exit_minutes), early_grace)
    return cint(late_consumed + early_consumed)


def get_employee_grace_details(employee):
    """Return grace details for an employee. Not yet implemented."""
    pass
