frappe.ui.form.on("Attendance", {
    refresh(frm) {
        if (frm.doc.custom_error_log) {
            frm.add_custom_button(__("Retry"), () => {
                frappe.call({
                    method: "discipline_hr.events.attendance.retry_attendance_pipeline",
                    args: {
                        attendance_name: frm.doc.name,
                    },
                    callback: function (r) {
                        if (!r.exc) {
                            frm.reload_doc();
                        }
                    },
                });
            });
        }
        if (frm.doc.employee && frm.doc.shift) {
            frm.add_custom_button(__("View Ledger"), () => {
                frappe.set_route("query-report", "Employee Grace Ledger", {
                    employee: frm.doc.employee,
                    shift: frm.doc.shift,
                    attendance: frm.doc.name,
                });
            });
        }
        if (frm.doc.name && !frm.is_new()) {
            frappe.db
                .get_value(
                    "Discipline Penalty",
                    { attendance: frm.doc.name, docstatus: ["!=", 2] },
                    "name"
                )
                .then((r) => {
                    const penalty = (r.message || {}).name;
                    if (penalty) {
                        frm.add_custom_button(__("View Penalty"), () => {
                            frappe.set_route("Form", "Discipline Penalty", penalty);
                        });
                    }
                });
        }
    },
});
