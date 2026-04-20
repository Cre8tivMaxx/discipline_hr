frappe.ui.form.on("Attendance", {
    refresh(frm) {
        if (frm.doc.custom_error_log) {
            frm.add_custom_button(__("Retry"), () => {
                frappe.call({
                    method: "discipline_hr.events.attendance.retry_attendance_permission",
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
    },
});
