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
