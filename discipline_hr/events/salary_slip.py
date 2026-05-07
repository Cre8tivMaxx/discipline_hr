import frappe
from frappe.utils import get_link_to_form


def _find_errored(doctype, date_field, error_field, employee, start_date, end_date):
    return frappe.get_all(
        doctype,
        filters={
            "employee": employee,
            error_field: ["is", "set"],
            date_field: ["between", (start_date, end_date)],
        },
        pluck="name",
    )


def _build_message(doctype, names, start_date, end_date, blocking):
    links = "<br>".join(get_link_to_form(doctype, n) for n in names)
    lead = (
        frappe._(
            "Cannot submit: {0} {1} record(s) still have unresolved errors between {2} and {3}. "
            "Please fix them before submitting:"
        )
        if blocking
        else frappe._(
            "{0} {1} record(s) with unresolved errors were found between {2} and {3}. "
            "Resolve them before submitting this Salary Slip:"
        )
    ).format(len(names), frappe.bold(doctype), frappe.bold(start_date), frappe.bold(end_date))
    return f"{lead}<br><br>{links}"


def _emit_guard_message(method, doctype, names, start_date, end_date):
    if method == "validate":
        frappe.msgprint(
            _build_message(doctype, names, start_date, end_date, blocking=False),
            title=frappe._("{0} needs attention").format(doctype),
            indicator="orange",
        )
    elif method == "before_submit":
        frappe.throw(
            _build_message(doctype, names, start_date, end_date, blocking=True),
            title=frappe._("Unresolved {0} errors").format(doctype),
        )


def guard_errored_discipline_penalties(doc, method=None):
    names = _find_errored(
        "Discipline Penalty",
        "violation_date",
        "error_log",
        doc.employee,
        doc.start_date,
        doc.end_date,
    )
    if names:
        _emit_guard_message(method, "Discipline Penalty", names, doc.start_date, doc.end_date)


def guard_errored_attendances(doc, method=None):
    names = _find_errored(
        "Attendance",
        "attendance_date",
        "custom_error_log",
        doc.employee,
        doc.start_date,
        doc.end_date,
    )
    if names:
        _emit_guard_message(method, "Attendance", names, doc.start_date, doc.end_date)


def guard_errored_grace_ledgers(doc, method=None):
    names = _find_errored(
        "Employee Grace Ledger",
        "date",
        "error_log",
        doc.employee,
        doc.start_date,
        doc.end_date,
    )
    if names:
        _emit_guard_message(method, "Employee Grace Ledger", names, doc.start_date, doc.end_date)
