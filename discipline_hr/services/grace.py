from frappe.utils import cint


def get_grace_minutes(shift_doc):
	late_grace = shift_doc.late_entry_grace_period or 0
	early_grace = shift_doc.early_exit_grace_period or 0
	return late_grace, early_grace


def calculate_consumed_grace_minutes(late_entry_minutes, early_exit_minutes, shift_doc) -> int:
	late_grace, early_grace = get_grace_minutes(shift_doc)
	late_consumed = min(cint(late_entry_minutes), late_grace)
	early_consumed = min(cint(early_exit_minutes), early_grace)
	return cint(late_consumed + early_consumed)
