import frappe


def after_install():
    _create_discipline_deduction_salary_component()


def _create_discipline_deduction_salary_component():
    if not frappe.db.exists("Salary Component", "Discipline Deduction"):
        frappe.get_doc(
            {
                "doctype": "Salary Component",
                "salary_component": "Discipline Deduction",
                "salary_component_abbr": "dd",
                "type": "Deduction",
                "depends_on_payment_days": 1,
                "remove_if_zero_valued": 1,
            }
        ).insert(ignore_permissions=True)

    settings = frappe.get_single("Discipline HR Settings")
    if not settings.salary_component:
        settings.salary_component = "Discipline Deduction"
        settings.save(ignore_permissions=True)
