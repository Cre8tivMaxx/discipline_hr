import frappe

PENDING_NOTIFICATION_NAME = "Attendance Permission Pending Review"
PENALTY_NOTIFICATION_NAME = "Discipline Penalty Pending Review"


def after_install():
    _create_discipline_deduction_salary_component()
    _create_pending_attendance_permission_notification()
    _create_pending_attendance_penalty_notification()


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


def _create_pending_attendance_permission_notification():
    if frappe.db.exists("Notification", PENDING_NOTIFICATION_NAME):
        return

    notification = frappe.new_doc("Notification")
    notification.name = PENDING_NOTIFICATION_NAME
    notification.subject = "Attendance Permission Pending: {{ doc.employee_name or doc.employee }}"
    notification.document_type = "Attendance Permissions"
    notification.event = "New"
    notification.channel = "Email"
    notification.condition = 'doc.status == "Pending"'
    notification.send_system_notification = 1
    notification.message = """<h3>Attendance Permission Needs Review</h3>

<p><b>Employee:</b> {{ doc.employee_name or doc.employee }}</p>
<p><b>Date:</b> {{ doc.date }}</p>
<p><b>Penalty Minutes:</b> {{ doc.minutes }}</p>
<p><b>Shift:</b> {{ doc.shift_type }}</p>

<p>Please review and take action.</p>"""
    notification.append("recipients", {"receiver_by_role": "HR Manager"})
    notification.enabled = 1
    notification.insert(ignore_permissions=True)

    settings = frappe.get_single("Discipline HR Settings")
    if not settings.default_pending_notification:
        settings.default_pending_notification = PENDING_NOTIFICATION_NAME
        settings.save(ignore_permissions=True)


def _create_pending_attendance_penalty_notification():
    if frappe.db.exists("Notification", PENALTY_NOTIFICATION_NAME):
        return

    notification = frappe.new_doc("Notification")
    notification.name = PENALTY_NOTIFICATION_NAME
    notification.subject = "Discipline Penalty Pending: {{ doc.employee_name or doc.employee }}"
    notification.document_type = "Discipline Penalty"
    notification.event = "New"
    notification.channel = "Email"
    notification.condition = 'doc.status == "Pending"'
    notification.send_system_notification = 1
    notification.message = """<h3>Discipline Penalty Needs Review</h3>

<p><b>Employee:</b> {{ doc.employee_name or doc.employee }}</p>
<p><b>Violation Date:</b> {{ doc.violation_date }}</p>
<p><b>Penalty Minutes:</b> {{ doc.penalty_minutes }}</p>
<p><b>Penalty Amount:</b> {{ doc.penalty_amount }}</p>

<p>Please review and take action.</p>"""
    notification.append("recipients", {"receiver_by_role": "HR Manager"})
    notification.enabled = 1
    notification.insert(ignore_permissions=True)

    settings = frappe.get_single("Discipline HR Settings")
    if not settings.default_penalty_notification:
        settings.default_penalty_notification = PENALTY_NOTIFICATION_NAME
        settings.save(ignore_permissions=True)
